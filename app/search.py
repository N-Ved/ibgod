"""Library queries: full-text search and the curated resource lists used by subject pages and the planner."""
from __future__ import annotations

import re
import sqlite3
from urllib.parse import quote

from . import catalog, config, db

_TOKEN = re.compile(r"[^\W_]+(?:'[^\W_]+)?", re.UNICODE)
_STOP = {"the", "a", "an", "of", "and", "or", "to", "in", "on", "for", "is", "are", "how", "what", "why", "do", "does", "i", "my", "me", "with", "about", "it", "be", "can"}

RES_COLS = "r.id, r.path, r.ext, r.collection, r.kind, r.subject, r.level, r.title, r.year, r.session, r.paper, r.tz, r.lang, r.publisher, r.topic_code, r.unit_name, r.syllabus, r.note, r.pages, r.url_kind, r.pair_id, r.size"


def fts_query(text: str, mode: str = "and", prefix_last: bool = False) -> str:
    """Build a safe FTS5 expression from free text. Every token is quoted, so user input can never inject operators."""
    toks = [t for t in _TOKEN.findall(text.lower()) if len(t) > 1][:16]
    if mode == "and":
        keep = [t for t in toks if t not in _STOP] or toks
    else:
        keep = [t for t in toks if t not in _STOP]
    if not keep:
        return ""
    parts = [f'"{t}"' for t in keep]
    if prefix_last and len(keep[-1]) >= 3:
        parts[-1] = f'"{keep[-1]}"*'
    return (" AND " if mode == "and" else " OR ").join(parts)


def phrase_query(phrases: list[str]) -> str:
    """OR of exact phrases (used for syllabus keywords)."""
    out = []
    for p in phrases:
        toks = _TOKEN.findall(p.lower())
        if toks:
            out.append('"' + " ".join(toks) + '"')
    return " OR ".join(out[:14])


def public(r: dict) -> dict:
    """Shape a resource row for the browser. Paths on disk are never exposed, only ids."""
    out = {k: r.get(k) for k in ("id", "ext", "collection", "kind", "subject", "level", "title", "year", "session", "paper", "tz", "lang", "publisher", "topic_code",
                                 "unit_name", "syllabus", "note", "pages", "pair_id", "size")}
    out["url"] = f"/api/files/{r['id']}/open"
    out["folder"] = "/".join(r["path"].split("/")[:-1])
    for k in ("page", "snippet", "pair_title", "mark", "attempts"):
        if k in r:
            out[k] = r[k]
    if r.get("page"):
        out["url"] += f"#page={r['page']}"
    return out


def external_url(r: dict) -> str | None:
    if r["url_kind"] == "view":
        top = r["path"].split("/", 1)[0]
        if top in config.VIEW_FOLDERS:
            return f"{config.VIEW_BASE}/{quote(r['path'])}"
    return None


def _filters(subject_tags: list[str] | None, collections: list[str] | None, kinds: list[str] | None, level: str | None, year_from: int | None,
             year_to: int | None, english_only: bool, syllabus: str | None) -> tuple[str, list]:
    where, params = [], []
    if subject_tags:
        where.append(f"r.subject IN ({','.join('?' * len(subject_tags))})")
        params += subject_tags
    if collections:
        where.append(f"r.collection IN ({','.join('?' * len(collections))})")
        params += collections
    if kinds:
        where.append(f"r.kind IN ({','.join('?' * len(kinds))})")
        params += kinds
    if level in ("HL", "SL"):
        where.append("(r.level IS NULL OR r.level IN (?, 'HLSL'))")
        params.append(level)
    if year_from:
        where.append("r.year>=?")
        params.append(year_from)
    if year_to:
        where.append("r.year<=?")
        params.append(year_to)
    if english_only:
        where.append("(r.lang IS NULL OR r.lang='en')")
    if syllabus == "current":
        where.append("COALESCE(r.syllabus,'current')='current'")
    return (" AND " + " AND ".join(where)) if where else "", params


def search(con: sqlite3.Connection, q: str, *, subject_tags: list[str] | None = None, collections: list[str] | None = None, kinds: list[str] | None = None,
           level: str | None = None, year_from: int | None = None, year_to: int | None = None, english_only: bool = True, syllabus: str | None = None,
           limit: int = 30, offset: int = 0) -> dict:
    """Title matches first, then best page per file from the full text."""
    limit = max(1, min(limit, 60))
    fsql, fparams = _filters(subject_tags, collections, kinds, level, year_from, year_to, english_only, syllabus)
    results: list[dict] = []
    seen: set[int] = set()
    q_and = fts_query(q, "and", prefix_last=True)
    if not q_and:
        rows = db.rows(con, f"SELECT {RES_COLS} FROM resources r WHERE 1=1 {fsql} ORDER BY COALESCE(r.year,0) DESC, r.title LIMIT ? OFFSET ?", (*fparams, limit, offset))
        return {"results": [public(r) for r in rows], "query": ""}
    try:
        title_rows = db.rows(con, f"""SELECT {RES_COLS}, bm25(res_fts, 6.0, 1.0) AS score FROM res_fts JOIN resources r ON r.id=res_fts.rowid
                                      WHERE res_fts MATCH ? {fsql} ORDER BY score LIMIT ? OFFSET ?""", (q_and, *fparams, limit, offset))
    except sqlite3.OperationalError:
        title_rows = []
    for r in title_rows:
        seen.add(r["id"])
        results.append(public(r))
    need = limit - len(results)
    if need > 0:
        tagq = ""
        if subject_tags:
            tagq = "stag:(" + " OR ".join(catalog.stag(t) for t in subject_tags) + ") AND "
        if collections:
            tagq += "ctag:(" + " OR ".join(catalog.ctag(c) for c in collections) + ") AND "
        match = f"{tagq}text:({fts_query(q, 'and')})"
        try:
            rows = db.rows(con, f"""SELECT {RES_COLS}, c.page AS page, snippet(chunks, 0, '[[', ']]', ' … ', 18) AS snippet, c.rank AS score
                                    FROM chunks c JOIN resources r ON r.id=c.resource_id
                                    WHERE chunks MATCH ? {fsql} ORDER BY c.rank LIMIT ?""", (match, *fparams, (need + offset) * 6 + 30))
        except sqlite3.OperationalError:
            rows = []
        skipped = 0
        for r in rows:
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            if skipped < offset and not title_rows:
                skipped += 1
                continue
            results.append(public(r))
            if len(results) >= limit:
                break
    return {"results": results, "query": q}


def passages(con: sqlite3.Connection, q: str, subject_tags: list[str] | None, collections: list[str] | None = None, limit: int = 4, max_chars: int = 900) -> list[dict]:
    """Short text passages for grounding the AI coach. OR-matching, best pages first, one per file."""
    expr = fts_query(q, "or")
    if not expr:
        return []
    tagq = ""
    if subject_tags:
        tagq = "stag:(" + " OR ".join(catalog.stag(t) for t in subject_tags) + ") AND "
    if collections:
        tagq += "ctag:(" + " OR ".join(catalog.ctag(c) for c in collections) + ") AND "
    try:
        rows = db.rows(con, f"""SELECT {RES_COLS}, c.page AS page, c.text AS text, c.rank AS score FROM chunks c JOIN resources r ON r.id=c.resource_id
                                WHERE chunks MATCH ? AND (r.lang IS NULL OR r.lang='en') ORDER BY c.rank LIMIT ?""", (f"{tagq}text:({expr})", limit * 5))
    except sqlite3.OperationalError:
        return []
    out, seen = [], set()
    terms = [t for t in _TOKEN.findall(q.lower()) if t not in _STOP and len(t) > 2]
    for r in rows:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        text = r.pop("text")
        low = text.lower()
        pos = min((low.find(t) for t in terms if low.find(t) >= 0), default=0)
        start = max(0, pos - max_chars // 3)
        pub = public(r)
        pub["text"] = ("…" if start else "") + text[start:start + max_chars].strip() + ("…" if start + max_chars < len(text) else "")
        out.append(pub)
        if len(out) >= limit:
            break
    return out


def topic_resources(con: sqlite3.Connection, subject_key: str, level: str, topic: dict, textbook_id: int | None = None, per_kind: int = 4) -> dict:
    """Everything in the library that helps with one syllabus topic, grouped by what it is for."""
    tags = catalog.subject_tags(subject_key)
    ph = ",".join("?" * len(tags))
    code = topic["code"]
    out: dict = {"notes": [], "videos": [], "questions": [], "textbook": [], "pages": []}
    lv = "(r.level IS NULL OR r.level IN (?, 'HLSL'))"
    # 1) Exact code matches (notes and videos carry syllabus codes in their names).
    code_variants = list({code, code.replace(".", ""), code.split(".")[0] + "." + code.split(".")[1] if "." in code else code})
    cph = ",".join("?" * len(code_variants))
    for coll, key in (("notes", "notes"), ("videos", "videos")):
        out[key] = [public(r) for r in db.rows(con, f"""SELECT {RES_COLS} FROM resources r WHERE r.subject IN ({ph}) AND r.collection=? AND r.topic_code IN ({cph}) AND {lv}
                                                         AND COALESCE(r.syllabus,'current')='current' ORDER BY (r.level=?) DESC, r.title LIMIT ?""",
                                                (*tags, coll, *code_variants, level, level, per_kind))]
    # 2) Keyword matches in titles and text.
    phrases = [topic["name"]] + topic.get("kw", [])
    title_expr = phrase_query(phrases)
    if title_expr:
        def by_title(collections: list[str], kinds: list[str] | None, n: int, cur_only: bool = True) -> list[dict]:
            cph_ = ",".join("?" * len(collections))
            ksql = f" AND r.kind IN ({','.join('?' * len(kinds))})" if kinds else ""
            cur = " AND COALESCE(r.syllabus,'current')='current'" if cur_only else ""
            try:
                return db.rows(con, f"""SELECT {RES_COLS} FROM res_fts JOIN resources r ON r.id=res_fts.rowid WHERE res_fts MATCH ? AND r.subject IN ({ph})
                                        AND r.collection IN ({cph_}){ksql}{cur} AND {lv} AND (r.lang IS NULL OR r.lang='en')
                                        ORDER BY bm25(res_fts, 8.0, 1.0) LIMIT ?""", (f"title:({title_expr})", *tags, *collections, *(kinds or []), level, n))
            except sqlite3.OperationalError:
                return []
        have = {r["id"] for r in out["notes"]}
        if len(out["notes"]) < per_kind:
            out["notes"] += [public(r) for r in by_title(["notes"], None, per_kind) if r["id"] not in have][:per_kind - len(out["notes"])]
        out["questions"] = [public(r) for r in by_title(["questionbank"], ["topic_questions"], per_kind)]
        if len(out["questions"]) < 2:
            out["questions"] += [public(r) for r in by_title(["questionbank"], ["topic_questions"], per_kind, cur_only=False) if r["id"] not in {x["id"] for x in out["questions"]}][:per_kind]
        out["pages"] = [public(r) for r in by_title(["site"], ["page"], per_kind)]
        # 3) Where the topic is covered in the student's textbook (or the best current one).
        stag_q = "stag:(" + " OR ".join(catalog.stag(t) for t in tags) + ")"
        text_expr = phrase_query(phrases)
        try:
            if textbook_id:
                rng = db.one(con, "SELECT chunk_lo, chunk_hi FROM resources WHERE id=?", (textbook_id,))
                if rng and rng["chunk_lo"] is not None:
                    rows = db.rows(con, f"""SELECT {RES_COLS}, c.page AS page, snippet(chunks, 0, '[[', ']]', ' … ', 14) AS snippet FROM chunks c JOIN resources r ON r.id=c.resource_id
                                            WHERE chunks MATCH ? AND c.rowid BETWEEN ? AND ? ORDER BY c.rank LIMIT 3""", (f"text:({text_expr})", rng["chunk_lo"], rng["chunk_hi"]))
                    out["textbook"] = [public(r) for r in sorted(rows, key=lambda x: x["page"] or 0)]
            if not out["textbook"]:
                rows = db.rows(con, f"""SELECT {RES_COLS}, c.page AS page, snippet(chunks, 0, '[[', ']]', ' … ', 14) AS snippet FROM chunks c JOIN resources r ON r.id=c.resource_id
                                        WHERE chunks MATCH ? AND r.kind IN ('textbook','revision_guide') AND COALESCE(r.syllabus,'current')='current' AND {lv}
                                        AND (r.lang IS NULL OR r.lang='en') ORDER BY c.rank LIMIT 12""", (f"{stag_q} AND ctag:cbooks AND text:({text_expr})", level))
                seen: set[int] = set()
                for r in rows:
                    if r["id"] not in seen:
                        seen.add(r["id"])
                        out["textbook"].append(public(r))
                    if len(out["textbook"]) >= 3:
                        break
        except sqlite3.OperationalError:
            pass
    return out


def past_papers(con: sqlite3.Connection, subject_key: str, level: str, username: str | None = None, include_legacy: bool = True, english_only: bool = True) -> list[dict]:
    """Question papers for a subject with their markschemes, newest first."""
    tags = catalog.subject_tags(subject_key)
    ph = ",".join("?" * len(tags))
    subj = catalog.get_subject(subject_key) or {}
    lang_sql = "" if (not english_only or subj.get("family") in ("lang_a", "lang_b")) else " AND (r.lang IS NULL OR r.lang='en')"
    leg = "" if include_legacy else " AND COALESCE(r.syllabus,'current')='current'"
    rows = db.rows(con, f"""SELECT {RES_COLS}, m.title AS pair_title FROM resources r LEFT JOIN resources m ON m.id=r.pair_id
                            WHERE r.subject IN ({ph}) AND r.collection IN ('past_papers','specimen','mocks') AND r.kind IN ('question_paper','booklet','audio')
                            AND (r.level IS NULL OR r.level IN (?, 'HLSL')){lang_sql}{leg}
                            ORDER BY CASE r.collection WHEN 'past_papers' THEN 0 WHEN 'mocks' THEN 1 ELSE 2 END, COALESCE(r.year, 0) DESC,
                                     CASE r.session WHEN 'November' THEN 0 WHEN 'May' THEN 1 ELSE 2 END, r.paper, r.tz, r.kind DESC, r.title""",
                   (*tags, level))
    attempts: dict[int, list] = {}
    if username:
        for a in db.rows(con, "SELECT resource_id, date, score, max_score, note, id FROM paper_attempts WHERE username=? ORDER BY date", (username,)):
            attempts.setdefault(a["resource_id"], []).append(a)
    out = []
    for r in rows:
        p = public(r)
        p["attempts"] = attempts.get(r["id"], [])
        out.append(p)
    return out


def subject_overview(con: sqlite3.Connection, subject_key: str, level: str) -> dict:
    """Counts and headline resources for a subject page."""
    tags = catalog.subject_tags(subject_key)
    ph = ",".join("?" * len(tags))
    counts = {f"{r['collection']}/{r['kind']}": r["n"] for r in db.rows(con, f"SELECT collection, kind, COUNT(*) n FROM resources r WHERE r.subject IN ({ph}) GROUP BY 1,2", tags)}

    def top(where: str, params: tuple = (), n: int = 12, order: str = "COALESCE(r.syllabus,'current')='current' DESC, COALESCE(r.year,0) DESC, r.title") -> list[dict]:
        return [public(r) for r in db.rows(con, f"SELECT {RES_COLS} FROM resources r WHERE r.subject IN ({ph}) AND {where} AND (r.lang IS NULL OR r.lang='en') ORDER BY {order} LIMIT ?",
                                           (*tags, *params, n))]
    lv = "(r.level IS NULL OR r.level IN (?, 'HLSL'))"
    return {
        "counts": counts,
        "guides": top("r.kind='subject_guide'", n=4),
        "booklets": top("r.kind IN ('data_booklet','text_types','case_study')", n=6),
        "textbooks": top(f"r.collection='books' AND r.kind='textbook' AND r.ext IN ('pdf','epub') AND {lv}", (level,), n=40),
        "revision_guides": top(f"r.collection='books' AND r.kind IN ('revision_guide','workbook','coursework_guide') AND {lv}", (level,), n=30),
        "answers": top(f"r.collection='books' AND r.kind='answers' AND {lv}", (level,), n=30),
        "question_banks": top("r.kind='qb_home'", n=6),
        "site_homes": top("r.kind='site_home'", n=6),
        "exemplars": top("r.collection='exemplars'", n=30),
        "mocks": top(f"r.collection IN ('mocks','practice') AND {lv}", (level,), n=40, order="r.title"),
    }


def general_docs(con: sqlite3.Connection) -> dict:
    """Programme-wide documents every student needs."""
    def q(kind: str, n: int = 6) -> list[dict]:
        return [public(r) for r in db.rows(con, f"SELECT {RES_COLS} FROM resources r WHERE r.kind=? AND (r.lang IS NULL OR r.lang='en') ORDER BY COALESCE(r.year,0) DESC, r.title LIMIT ?", (kind, n))]
    return {"grade_boundaries": q("grade_boundaries", 8), "exam_schedules": q("exam_schedule", 6), "grade_descriptors": q("grade_descriptors", 3),
            "calculator_rules": q("calculator_rules", 2), "exam_conduct": q("exam_conduct", 3)}
