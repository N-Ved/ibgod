"""My works: the literary works a Language A / Language B student is studying, optionally with their own copy.

Each work is private to the person who added it. A work also becomes a checklist item ("Your works" unit, code
W<id>), so the planner schedules reading/annotation, writing practice and reviews for it, and is matched to the
study guides on the drive (LitCharts) by title.

Uploaded files are checked by content (not by name), stored under /data/works with random names, and served back
only to their owner: PDFs and plain text inline under a sandboxing policy, everything else as a download.
"""
from __future__ import annotations

import hashlib
import io
import os
import secrets
import sqlite3
import zipfile
from pathlib import Path

from . import catalog, config, db, search

FAMILIES = ("lang_a", "lang_b")
KINDS = {"novel": "Novel", "poetry": "Poetry", "drama": "Drama", "short_stories": "Short stories", "nonfiction": "Non-fiction / essays",
         "graphic": "Graphic novel", "film": "Film / screenplay", "nonliterary": "Non-literary body of work", "other": "Other"}
PARTS = {"paper2": "Paper 2 (comparative essay)", "oral": "Individual oral", "hl_essay": "HL essay", "class": "Studied in class", "undecided": "Not decided yet"}
MAX_BYTES = 24 * 1024 * 1024        # Caddy accepts 25 MB request bodies for this site
MAX_WORKS = 40
QUOTA_BYTES = 400 * 1024 * 1024
UNIT = {"code": "WK", "name": "Your works"}
INLINE = {"pdf": "application/pdf", "txt": "text/plain; charset=utf-8"}
DOWNLOAD = {"epub": "application/epub+zip", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}



def supports(subject_key: str) -> bool:
    s = catalog.get_subject(subject_key) or {}
    return s.get("family") in FAMILIES


def user_dir(username: str) -> Path:
    return config.DATA_DIR / "works" / hashlib.sha256(username.lower().encode()).hexdigest()[:20]


def sniff(data: bytes) -> str | None:
    """File type from its content. Returns pdf / epub / docx / txt, or None when it is none of these."""
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = set(z.namelist())
                if "mimetype" in names and z.read("mimetype")[:40].strip() == b"application/epub+zip":
                    return "epub"
                if "word/document.xml" in names:
                    return "docx"
        except (zipfile.BadZipFile, KeyError, OSError, RuntimeError):
            return None
        return None
    if b"\x00" in data[:65536]:
        return None
    try:
        data[:200000].decode("utf-8")
        return "txt"
    except UnicodeDecodeError:
        return None


def store(username: str, data: bytes, ext: str) -> str:
    d = user_dir(username)
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    name = f"{secrets.token_hex(16)}.{ext}"
    tmp = d / (name + ".part")
    with open(tmp, "wb") as f:
        f.write(data)
    os.chmod(tmp, 0o600)
    os.replace(tmp, d / name)
    return name


def remove_file(username: str, stored_name: str | None) -> None:
    if not stored_name:
        return
    p = (user_dir(username) / stored_name).resolve()
    if p.parent == user_dir(username).resolve():
        try:
            p.unlink()
        except FileNotFoundError:
            pass


def file_path(username: str, stored_name: str) -> Path | None:
    p = (user_dir(username) / stored_name).resolve()
    if p.parent != user_dir(username).resolve() or not p.is_file():
        return None
    return p


def used_bytes(con: sqlite3.Connection, username: str) -> int:
    return con.execute("SELECT COALESCE(SUM(file_size),0) FROM works WHERE username=?", (username,)).fetchone()[0]


def rows_for(con: sqlite3.Connection, username: str, subject: str | None = None) -> list[dict]:
    if subject:
        return db.rows(con, "SELECT * FROM works WHERE username=? AND subject=? ORDER BY id", (username, subject))
    return db.rows(con, "SELECT * FROM works WHERE username=? ORDER BY id", (username,))


def as_topics(rows: list[dict]) -> list[dict]:
    """Works in the same shape as catalogue topics, so the checklist and planner treat them alike."""
    n = len(rows)
    return [{"code": f"W{r['id']}", "name": r["title"], "kw": [r["title"]] + ([r["author"]] if r.get("author") else []), "hl_only": False, "optional": False,
             "default_on": True, "unit_code": UNIT["code"], "unit_name": UNIT["name"], "unit_hours": None, "unit_size": n, "work": True, "work_id": r["id"],
             "size_hint": 1.6} for r in rows]


def topics_for(con: sqlite3.Connection, username: str, key: str, level: str) -> list[dict]:
    """Catalogue topics plus this person's works (for language subjects)."""
    out = catalog.topics_for(key, level)
    if supports(key):
        out = out + as_topics(rows_for(con, username, key))
    return out


def guides(con: sqlite3.Connection, title: str, author: str | None = None, limit: int = 3) -> list[dict]:
    """Study guides on the drive for a work, best first (needs a connection bound with access.bind)."""
    expr = search.fts_query(title, "and")
    if not expr:
        return []
    try:
        rows = db.rows(con, f"""SELECT {search.RES_COLS} FROM res_fts JOIN resources r ON r.id=res_fts.rowid
                                WHERE res_fts MATCH ? AND r.kind='lit_guide' AND visible(r.path) ORDER BY bm25(res_fts, 8.0, 1.0) LIMIT ?""", (f"title:({expr})", limit * 3))
    except sqlite3.OperationalError:
        return []
    out, seen = [], set()
    want = set(catalog.norm(title).split())
    for r in rows:
        name = catalog.norm(r["title"].replace("(LitChart study guide)", ""))
        key = name.replace("litcharts ", "")
        if key in seen:
            continue
        # every significant word of the work's title must be in the guide's title (avoids "Hamlet" -> "The Hamlet")
        if not {w for w in want if len(w) > 2 and w not in ("the", "and")} <= set(key.split()):
            continue
        seen.add(key)
        out.append(search.public(r))
        if len(out) >= limit:
            break
    return out


def public(con: sqlite3.Connection, r: dict, with_guides: bool = True) -> dict:
    out = {k: r[k] for k in ("id", "subject", "title", "author", "kind", "part", "notes", "file_name", "file_ext", "file_size", "created_at")}
    out["code"] = f"W{r['id']}"
    out["file_url"] = f"/api/works/{r['id']}/file" if r["stored_name"] else None
    if with_guides:
        out["guides"] = guides(con, r["title"], r.get("author"))
    return out


def as_resource(r: dict) -> dict:
    """The student's own copy, shaped like a library resource for topic/task material lists."""
    return {"id": f"w{r['id']}", "title": f"Your copy: {r['title']}", "url": f"/api/works/{r['id']}/file", "kind": "your_copy", "ext": r["file_ext"], "collection": "works",
            "subject": r["subject"], "level": None, "year": None, "session": None, "paper": None, "tz": None, "lang": None, "publisher": None, "topic_code": None,
            "unit_name": None, "syllabus": None, "note": None, "pages": None, "pair_id": None, "size": r["file_size"], "folder": ""}
