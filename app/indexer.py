"""Library indexer: walks the read-only drive, classifies files, and extracts searchable text.

Runs in one background thread. Text extraction is CPU-heavy, so it uses a small worker pool at low
priority and can be interrupted and resumed at any point (state lives in the database).
"""
from __future__ import annotations

import html
import logging
import os
import re
import subprocess
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import catalog, config, db

log = logging.getLogger("ibgod.indexer")

_state_lock = threading.Lock()
_state: dict = {"phase": "idle", "scanned": 0, "text_total": 0, "text_done": 0, "started": None, "finished": None, "error": None}
_thread: threading.Thread | None = None
_stop = threading.Event()
_wake = threading.Event()

MAX_PAGE_CHARS = 12000
MAX_PAGES = 2000
MAX_HTML_BYTES = 3_000_000
PDF_TIMEOUT = 240

_TAG_BLOCK = re.compile(r"(?is)<(script|style|noscript|svg|head)\b.*?</\1>")
_TAG = re.compile(r"(?s)<[^>]+>")
_WS = re.compile(r"\s+")
_TITLE = re.compile(r"(?is)<title[^>]*>(.*?)</title>")
_H1 = re.compile(r"(?is)<h1[^>]*>(.*?)</h1>")
_QCODE = re.compile(r"\b\d{2}[MN]\.\d[A-Za-z]?\.[A-Za-z]{2,3}\.")


def status() -> dict:
    with _state_lock:
        return dict(_state)


def _set(**kw) -> None:
    with _state_lock:
        _state.update(kw)


def _clean(s: str) -> str:
    return _WS.sub(" ", s.replace("\x00", " ")).strip()


def html_to_text(raw: str) -> tuple[str, str, str]:
    """Return (title, h1, body text) of an HTML document without executing or trusting any of it."""
    t = _TITLE.search(raw)
    h = _H1.search(raw)
    body = _TAG.sub(" ", _TAG_BLOCK.sub(" ", raw))
    return (_clean(html.unescape(_TAG.sub(" ", t.group(1)))) if t else "", _clean(html.unescape(_TAG.sub(" ", h.group(1)))) if h else "", _clean(html.unescape(body)))


def _low_priority() -> None:
    try:
        os.nice(12)
    except OSError:
        pass


def extract_pdf(path: Path) -> list[tuple[int, str]]:
    proc = subprocess.run(["pdftotext", "-enc", "UTF-8", "-q", "-l", str(MAX_PAGES), str(path), "-"], capture_output=True, timeout=PDF_TIMEOUT, preexec_fn=_low_priority, check=False)
    if proc.returncode != 0 and not proc.stdout:
        raise RuntimeError(f"pdftotext exit {proc.returncode}")
    out = []
    for i, page in enumerate(proc.stdout.decode("utf-8", "replace").split("\f"), start=1):
        text = _clean(page)
        if len(text) >= 20:
            out.append((i, text[:MAX_PAGE_CHARS]))
    return out


def _zip_xml_texts(path: Path, pattern: str, limit: int = 400) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    with zipfile.ZipFile(path) as z:
        names = sorted((n for n in z.namelist() if re.search(pattern, n)), key=lambda n: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", n)])
        for i, name in enumerate(names[:limit], start=1):
            info = z.getinfo(name)
            if info.file_size > 8_000_000:
                continue
            raw = z.read(name).decode("utf-8", "replace")
            raw = re.sub(r"</(w:p|a:p|p|div|h\d|li|br)>", " \n", raw)
            text = _clean(html.unescape(_TAG.sub(" ", _TAG_BLOCK.sub(" ", raw))))
            if len(text) >= 20:
                out.append((i, text[:MAX_PAGE_CHARS]))
    return out


def extract_text(path: Path, ext: str, kind: str) -> tuple[list[tuple[int | None, str]], dict]:
    """Extract (page, text) rows plus metadata updates (title, pages) for one file."""
    extra: dict = {}
    if ext == "pdf":
        pages = extract_pdf(path)
        extra["pages"] = pages[-1][0] if pages else None
        return pages, extra
    if ext in ("html", "htm"):
        with open(path, "rb") as f:
            raw = f.read(MAX_HTML_BYTES).decode("utf-8", "replace")
        title, h1, body = html_to_text(raw)
        if kind in ("topic_questions", "markscheme") and "Path:" in body:
            m = re.search(r"Path:\s*(.*?)\s*(?:Description|Directly related questions|Sub sections and their related questions)", body)
            if m:
                crumbs = [c.strip() for c in m.group(1).split("»") if c.strip()]
                if crumbs:
                    extra["section"] = crumbs[-1][:160]
                    extra["crumbs"] = " › ".join(crumbs)[:300]
            body = body[body.index("Path:"):]
            extra["pages"] = len(set(_QCODE.findall(body))) or None
        else:
            name = re.sub(r"^(DP|IB)\s+[A-Za-z &:]+:\s*", "", title).strip() or h1
            if name and name.lower() not in ("ib questionbank", "index"):
                extra["title"] = name[:160]
        return ([(None, body[:60000])] if len(body) >= 40 else []), extra
    if ext == "docx":
        return _zip_xml_texts(path, r"^word/document\.xml$"), extra
    if ext == "pptx":
        rows = _zip_xml_texts(path, r"^ppt/slides/slide\d+\.xml$")
        extra["pages"] = len(rows) or None
        return rows, extra
    if ext == "epub":
        return _zip_xml_texts(path, r"\.(xhtml|html|htm)$"), extra
    if ext == "txt":
        with open(path, "rb") as f:
            text = _clean(f.read(500_000).decode("utf-8", "replace"))
        return ([(None, text[:60000])] if len(text) >= 20 else []), extra
    return [], extra


# ───────────────────────── scan ─────────────────────────
_COLS = ["size", "mtime", "ext", "collection", "kind", "subject", "level", "title", "year", "session", "paper", "tz", "lang", "publisher", "topic_code", "unit_name",
         "syllabus", "note", "url_kind", "pair_key"]


def scan() -> int:
    """Synchronise the resources table with the files on disk. Returns the number of indexed files."""
    root = config.LIBRARY_ROOT
    scan_id = int(time.time())
    _set(phase="scanning", scanned=0, error=None)
    with db.ro() as con:
        known = {r["path"]: (r["size"], r["mtime"], r["id"]) for r in con.execute("SELECT path,size,mtime,id FROM resources")}
        reclassify = db.get_meta(con, "classifier_version", 0) != catalog.CLASSIFIER_VERSION and bool(known)
    new_rows: list[tuple] = []
    changed: list[tuple] = []
    remeta: list[tuple] = []
    seen_ids: list[int] = []
    count = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        if dirpath == str(root):
            dirnames[:] = [d for d in dirnames if d not in config.EXCLUDE_TOP]
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        if _stop.is_set():
            return count
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            if os.sep != "/":
                rel = rel.replace(os.sep, "/")
            try:
                meta = catalog.classify(rel)
            except Exception:  # a single odd file name must never stop the scan
                log.exception("classify failed for %s", rel)
                meta = None
            if not meta:
                continue
            try:
                st = os.stat(full, follow_symlinks=False)
            except OSError:
                continue
            if not os.path.isfile(full) or os.path.islink(full):
                continue
            count += 1
            status_ = "pending" if meta.pop("text") else "skip"
            vals = (st.st_size, st.st_mtime, meta["ext"], meta["collection"], meta["kind"], meta["subject"], meta["level"], (meta["title"] or fn)[:240], meta["year"], meta["session"],
                    meta["paper"], meta["tz"], meta["lang"], meta["publisher"], meta["topic_code"], meta["unit_name"], meta["syllabus"], meta["note"], meta["url_kind"], meta["pair_key"])
            prev = known.get(rel)
            if prev is None:
                new_rows.append((rel, *vals, status_, scan_id))
            elif prev[0] != st.st_size or abs(prev[1] - st.st_mtime) > 1:
                changed.append((*vals, status_, scan_id, prev[2]))
            else:
                seen_ids.append(prev[2])
                if reclassify:
                    remeta.append((vals, prev[2]))
            if count % 2000 == 0:
                _set(scanned=count)
    _set(scanned=count)
    with db.tx() as con:
        con.executemany(f"INSERT INTO resources(path,{','.join(_COLS)},text_status,seen) VALUES({','.join('?' * (len(_COLS) + 3))})", new_rows)
        for row in changed:
            old = con.execute("SELECT chunk_lo, chunk_hi FROM resources WHERE id=?", (row[-1],)).fetchone()
            if old and old["chunk_lo"] is not None:
                con.execute("DELETE FROM chunks WHERE rowid BETWEEN ? AND ?", (old["chunk_lo"], old["chunk_hi"]))
            con.execute(f"UPDATE resources SET {','.join(c + '=?' for c in _COLS)}, text_status=?, seen=?, chunk_lo=NULL, chunk_hi=NULL, pages=NULL WHERE id=?", row)
        for i in range(0, len(seen_ids), 500):
            part = seen_ids[i:i + 500]
            con.execute(f"UPDATE resources SET seen=? WHERE id IN ({','.join('?' * len(part))})", (scan_id, *part))
        # The classifier changed: refresh metadata in place. Extracted text is kept; its subject/collection tags follow.
        for vals, rid in remeta:
            cur = con.execute("SELECT subject, collection, ext, title, unit_name, text_status, chunk_lo, chunk_hi FROM resources WHERE id=?", (rid,)).fetchone()
            v = dict(zip(_COLS, vals))
            if cur["ext"] in ("html", "htm") and cur["text_status"] == "done":
                v["title"], v["unit_name"] = cur["title"], cur["unit_name"]  # titles read from the page itself are better than file names
            cols = [c for c in _COLS if c not in ("size", "mtime")]
            con.execute(f"UPDATE resources SET {','.join(c + '=?' for c in cols)} WHERE id=?", (*[v[c] for c in cols], rid))
            if (cur["subject"], cur["collection"]) != (v["subject"], v["collection"]) and cur["chunk_lo"] is not None:
                con.execute("UPDATE chunks SET stag=?, ctag=? WHERE rowid BETWEEN ? AND ?", (catalog.stag(v["subject"]), catalog.ctag(v["collection"]), cur["chunk_lo"], cur["chunk_hi"]))
            if cur["title"] != v["title"] or cur["subject"] != v["subject"]:
                r = con.execute("SELECT id, path, title, subject, collection, kind FROM resources WHERE id=?", (rid,)).fetchone()
                con.execute("DELETE FROM res_fts WHERE rowid=?", (rid,))
                con.execute("INSERT INTO res_fts(rowid, title, words) VALUES(?,?,?)", (rid, r["title"], _path_words(r)))
        db.set_meta(con, "classifier_version", catalog.CLASSIFIER_VERSION)
        # Files that disappeared from the drive.
        for r in con.execute("SELECT id, chunk_lo, chunk_hi FROM resources WHERE seen<>?", (scan_id,)).fetchall():
            if r["chunk_lo"] is not None:
                con.execute("DELETE FROM chunks WHERE rowid BETWEEN ? AND ?", (r["chunk_lo"], r["chunk_hi"]))
            con.execute("DELETE FROM res_fts WHERE rowid=?", (r["id"],))
            con.execute("DELETE FROM resources WHERE id=?", (r["id"],))
        # Question paper ↔ markscheme pairs.
        con.execute("UPDATE resources SET pair_id=NULL WHERE pair_id IS NOT NULL")
        con.execute("""UPDATE resources SET pair_id=(SELECT r2.id FROM resources r2 WHERE r2.pair_key=resources.pair_key AND r2.kind='markscheme' AND r2.id<>resources.id
                         AND COALESCE(r2.lang,'')=COALESCE(resources.lang,'') LIMIT 1)
                       WHERE pair_key IS NOT NULL AND kind IN ('question_paper','topic_questions','worksheet')""")
        con.execute("""UPDATE resources SET pair_id=(SELECT r2.id FROM resources r2 WHERE r2.pair_key=resources.pair_key AND r2.kind IN ('question_paper','topic_questions','worksheet')
                         AND r2.id<>resources.id AND COALESCE(r2.lang,'')=COALESCE(resources.lang,'') LIMIT 1)
                       WHERE pair_key IS NOT NULL AND kind='markscheme'""")
        # Title index for everything that is new or changed.
        todo = con.execute("SELECT id, path, title, subject, collection, kind FROM resources WHERE seen=? AND id NOT IN (SELECT rowid FROM res_fts)", (scan_id,)).fetchall()
        for r in todo:
            con.execute("INSERT INTO res_fts(rowid, title, words) VALUES(?,?,?)", (r["id"], r["title"], _path_words(r)))
        for row in changed:
            r = con.execute("SELECT id, path, title, subject, collection, kind FROM resources WHERE id=?", (row[-1],)).fetchone()
            con.execute("DELETE FROM res_fts WHERE rowid=?", (r["id"],))
            con.execute("INSERT INTO res_fts(rowid, title, words) VALUES(?,?,?)", (r["id"], r["title"], _path_words(r)))
        db.set_meta(con, "last_scan", {"at": scan_id, "files": count, "new": len(new_rows), "changed": len(changed)})
    log.info("scan complete: %d files (%d new, %d changed)", count, len(new_rows), len(changed))
    return count


def _path_words(r) -> str:
    s = catalog.get_subject(r["subject"]) if r["subject"] else None
    words = [catalog.norm(r["path"].rsplit(".", 1)[0].replace("/", " ")), (s["name"] if s else ""), (r["collection"] or "").replace("_", " "), (r["kind"] or "").replace("_", " ")]
    return " ".join(w for w in words if w)[:1500]


# ───────────────────────── text extraction ─────────────────────────
_PRIORITY = """CASE
  WHEN collection='notes' THEN 0
  WHEN collection='official' THEN 1
  WHEN collection IN ('mocks','practice','videos','specimen') THEN 2
  WHEN collection='questionbank' THEN 3
  WHEN collection='books' AND COALESCE(syllabus,'current')='current' THEN 4
  WHEN collection='past_papers' AND year>=2021 THEN 5
  WHEN collection='site' THEN 6
  WHEN collection='past_papers' THEN 7
  ELSE 8 END"""


def _work(row: dict) -> tuple[dict, list, dict, str]:
    path = config.LIBRARY_ROOT / row["path"]
    try:
        rows, extra = extract_text(path, row["ext"], row["kind"])
        return row, rows, extra, ("done" if rows else "empty")
    except subprocess.TimeoutExpired:
        return row, [], {}, "error"
    except Exception as e:  # corrupt or unusual files are recorded and skipped
        log.debug("extract failed for %s: %r", row["path"], e)
        return row, [], {}, "error"


def extract_all() -> None:
    with db.ro() as con:
        total = con.execute("SELECT COUNT(*) FROM resources WHERE text_status<>'skip'").fetchone()[0]
        done = con.execute("SELECT COUNT(*) FROM resources WHERE text_status IN ('done','empty','error')").fetchone()[0]
    _set(phase="extracting", text_total=total, text_done=done)
    with ThreadPoolExecutor(max_workers=max(1, config.INDEX_WORKERS), thread_name_prefix="extract") as pool:
        while not _stop.is_set():
            with db.ro() as con:
                batch = db.rows(con, f"SELECT id, path, ext, kind, subject, collection, title FROM resources WHERE text_status='pending' ORDER BY {_PRIORITY}, year DESC, id LIMIT 48")
            if not batch:
                break
            results = list(pool.map(_work, batch))
            with db.tx() as con:
                for row, rows, extra, st in results:
                    lo = hi = None
                    st_tag, c_tag = catalog.stag(row["subject"]), catalog.ctag(row["collection"])
                    for page, text in rows:
                        cur = con.execute("INSERT INTO chunks(text, stag, ctag, resource_id, page) VALUES(?,?,?,?,?)", (text, st_tag, c_tag, row["id"], page))
                        lo = cur.lastrowid if lo is None else lo
                        hi = cur.lastrowid
                    sets, params = ["text_status=?", "chunk_lo=?", "chunk_hi=?"], [st, lo, hi]
                    if extra.get("pages") is not None:
                        sets.append("pages=?")
                        params.append(extra["pages"])
                    title = None
                    if extra.get("section"):
                        subj = catalog.get_subject(row["subject"]) if row["subject"] else None
                        title = f"{subj['short'] if subj else 'Questionbank'} questions · {extra['section']}"
                        sets.append("unit_name=?")
                        params.append(extra.get("crumbs"))
                    elif extra.get("title"):
                        title = extra["title"]
                    if title:
                        sets.append("title=?")
                        params.append(title[:240])
                        con.execute("UPDATE res_fts SET title=? WHERE rowid=?", (title[:240], row["id"]))
                    con.execute(f"UPDATE resources SET {','.join(sets)} WHERE id=?", (*params, row["id"]))
            done += len(batch)
            _set(text_done=done)
    if not _stop.is_set():
        with db.tx() as con:
            con.execute("INSERT INTO chunks(chunks) VALUES('optimize')")
            db.set_meta(con, "last_extract", int(time.time()))


def _run() -> None:
    while not _stop.is_set():
        try:
            _set(started=int(time.time()), finished=None)
            scan()
            if not _stop.is_set():
                extract_all()
            _set(phase="idle", finished=int(time.time()))
        except Exception as e:
            log.exception("indexer failed")
            _set(phase="error", error=repr(e)[:300])
        _wake.clear()
        # Re-scan daily, or immediately when an admin asks.
        _wake.wait(timeout=24 * 3600)


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_run, name="indexer", daemon=True)
    _thread.start()


def request_rescan() -> None:
    _wake.set()


def stop() -> None:
    _stop.set()
    _wake.set()
