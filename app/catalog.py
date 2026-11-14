"""Subject lookup plus the classifier that turns a library path into structured metadata."""
from __future__ import annotations

import re
from datetime import date
from pathlib import PurePosixPath

from .catalog_data import CORE, GROUP_NAMES, IA, P, SESSION_END, SESSION_START, SUBJECTS, U, language_subject

# A few subjects with papers on the drive but no built-in syllabus. Students get generic units they can rename.
_GENERIC = [
    ("anthropology", "Social and Cultural Anthropology", 3, ["HL", "SL"], ["social and cultural anthropology"], ["group 3 - individuals and societies/social and cultural anthropology"]),
    ("world_religions", "World Religions", 3, ["SL"], ["world religions"], []),
    ("latin", "Latin", 2, ["HL", "SL"], ["latin"], []),
    ("classical_greek", "Classical Greek", 2, ["HL", "SL"], ["classical greek"], []),
]


def _generic_units() -> list[dict]:
    return [U("G", "Course content", "G.1|Unit 1||", "G.2|Unit 2||", "G.3|Unit 3||", "G.4|Unit 4||"),
            U("X", "Exam skills", "X.1|Paper 1 technique||", "X.2|Paper 2 technique||")]


def _generic_assessment(levels: list[str]) -> dict:
    out = {}
    for lv in levels:
        out[lv] = [P("Paper 1", 90, 40, "Check your subject guide for the exact format"), P("Paper 2", 90, 35, "Check your subject guide for the exact format"), IA("Internal assessment", 25, "Check your subject guide")]
    return out


for _k, _n, _g, _lv, _pp, _bk in _GENERIC:
    SUBJECTS.append(dict(key=_k, name=_n, short=_n, group=_g, levels=_lv, syllabus_from=2000, family="humanities" if _g == 3 else "lang_b",
                         papers=_pp, books=_bk, qb=[], qb_paper=[], sme=[], sites=[], names=_pp, generic=True,
                         note="Topics for this subject are not built in. Rename the units on this page to match what you study.",
                         assessment=_generic_assessment(_lv), units=_generic_units()))

BY_KEY: dict[str, dict] = {s["key"]: s for s in SUBJECTS}
CORE_BY_KEY = {c["key"]: c for c in CORE}


LANG_PREFIXES = ("lang_a_ll", "lang_a_lit", "lang_b", "ab_initio")
_DYN: dict[str, dict] = {}


def _dynamic_language(prefix: str, lang: str) -> dict | None:
    """Language courses beyond the built-in list (the drive has papers for ~70 languages)."""
    key = f"{prefix}:{lang}"
    if key not in _DYN:
        s = language_subject(prefix, lang)
        if s:
            _DYN[key] = s
    return _DYN.get(key)


_LANG_SUFFIX = [(" a language and literature", "lang_a_ll"), (" a literature", "lang_a_lit"), (" ab initio", "ab_initio"), (" b", "lang_b")]


def _language_key_from_text(text: str) -> str | None:
    for suffix, prefix in _LANG_SUFFIX:
        if text.endswith(suffix):
            lang = text[: -len(suffix)].strip()
            if re.fullmatch(r"[a-z]+(?: [a-z]+)?", lang) and lang not in ("history route", "paper", "group"):
                return f"{prefix}:{lang.title()}"
    return None


def norm(s: str) -> str:
    s = s.lower().replace("_", " ").replace("-", " ")
    s = re.sub(r"[\[\]\(\)]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def get_subject(key: str) -> dict | None:
    """Catalogue entry for a key, synthesising one for student-defined `custom:` subjects."""
    if key in BY_KEY:
        return BY_KEY[key]
    if ":" in key and key.split(":", 1)[0] in LANG_PREFIXES:
        prefix, lang = key.split(":", 1)
        if re.fullmatch(r"[A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)?", lang):
            return _dynamic_language(prefix, lang)
        return None
    if key.startswith("custom:"):
        name = key.split(":", 1)[1][:60] or "Other subject"
        return dict(key=key, name=name, short=name, group=0, levels=["HL", "SL"], syllabus_from=2000, family="humanities", papers=[], books=[], qb=[], qb_paper=[],
                    sme=[], sites=[], names=[], generic=True, note="Custom subject: rename the units to match your course. Library matches come from search only.",
                    assessment=_generic_assessment(["HL", "SL"]), units=_generic_units())
    return None


def subject_tags(key: str) -> list[str]:
    """All resource tags that belong to a subject (its own plus shared pools)."""
    s = get_subject(key)
    if not s:
        return [key]
    tags = [key]
    fam = s.get("family")
    if key in ("math_aa", "math_ai"):
        tags.append("shared:math")
    if fam == "lang_a":
        tags.append("shared:lang_a")
        if s.get("language") == "English":
            tags.append("shared:english_a")
    if fam == "lang_b" and s.get("language"):
        tags.append("shared:lang_b")
    return tags


def stag(tag: str | None) -> str:
    """FTS-safe token for a subject tag."""
    return "s" + slug(tag) if tag else "snone"


def ctag(collection: str | None) -> str:
    return "c" + slug(collection or "other")


def topics_for(key: str, level: str) -> list[dict]:
    """Flat topic list for a subject at a level, each with its unit."""
    s = get_subject(key)
    out: list[dict] = []
    if not s:
        return out
    for u in s["units"]:
        n_topics = [t for t in u["topics"] if level == "HL" or not t["hl_only"]]
        for t in n_topics:
            out.append({**t, "unit_code": u["code"], "unit_name": u["name"],
                        "unit_hours": (u["hours"][1 if level == "HL" else 0] if u.get("hours") else None), "unit_size": len(n_topics)})
    return out


def public_subject(key: str) -> dict | None:
    s = get_subject(key)
    if not s:
        return None
    return {"key": s["key"], "name": s["name"], "short": s["short"], "group": s["group"], "group_name": GROUP_NAMES.get(s["group"], "Other"),
            "levels": s["levels"], "family": s.get("family"), "syllabus_from": s.get("syllabus_from"), "note": s.get("note"),
            "generic": bool(s.get("generic")), "assessment": s["assessment"],
            "units": [{"code": u["code"], "name": u["name"], "topics": u["topics"]} for u in s["units"]]}


def catalogue_summary() -> list[dict]:
    return [{"key": s["key"], "name": s["name"], "short": s["short"], "group": s["group"], "group_name": GROUP_NAMES.get(s["group"], "Other"),
             "levels": s["levels"], "family": s.get("family"), "language": s.get("language")} for s in SUBJECTS]


def exam_window(month: str, year: int) -> tuple[date, date]:
    m, d = SESSION_START.get(month, SESSION_START["May"])
    m2, d2 = SESSION_END.get(month, SESSION_END["May"])
    return date(year, m, d), date(year, m2, d2)


# ───────────────────────── classification ─────────────────────────
# Bump when classify() changes meaning: the indexer then refreshes metadata of every file without re-reading its text.
CLASSIFIER_VERSION = 2
PAPER_ALIAS: dict[str, tuple[str, str | None]] = {}
for _s in SUBJECTS:
    for _a in _s.get("papers", []):
        PAPER_ALIAS.setdefault(norm(_a), (_s["key"], None))
for _s in SUBJECTS:
    for _a, _note in _s.get("papers_legacy", []):
        PAPER_ALIAS.setdefault(norm(_a), (_s["key"], _note))
PAPER_ALIAS.update({"bio": ("biology", None), "computer sci": ("computer_science", None), "comp sci": ("computer_science", None),
                    "phys": ("physics", None), "geo": ("geography", None), "psych": ("psychology", None), "global pol": ("global_politics", None),
                    "business": ("business_management", None), "english lang lit": ("lang_a_ll:English", None), "english lit": ("lang_a_lit:English", None),
                    "sport sci": ("sehs", None), "design tech": ("design_technology", None), "math": ("math_aa", "Unspecified maths course")})

NAME_ALIAS: list[tuple[str, str]] = []  # (normalised name, key), longest first
for _s in SUBJECTS:
    for _a in _s.get("names", []) + [_s["name"]]:
        NAME_ALIAS.append((norm(_a), _s["key"]))
for _c in CORE:
    for _a in _c["names"]:
        NAME_ALIAS.append((norm(_a), _c["key"]))
NAME_ALIAS.sort(key=lambda x: -len(x[0]))
_GENERIC_LANG_NAMES = {"language a language and literature": "shared:lang_a", "language a literature": "shared:lang_a", "language b": "shared:lang_b", "language ab initio": "shared:lang_b"}

BOOK_DIRS: list[tuple[str, str]] = []
for _s in SUBJECTS:
    for _b in _s.get("books", []):
        BOOK_DIRS.append((_b.lower(), _s["key"]))
BOOK_DIRS.sort(key=lambda x: -len(x[0]))

QB_SLUGS: list[tuple[str, str]] = sorted(((q, s["key"]) for s in SUBJECTS for q in s.get("qb", [])), key=lambda x: -len(x[0]))
QB_PAPER_NAMES: list[tuple[str, str]] = sorted(((norm(q), s["key"]) for s in SUBJECTS for q in s.get("qb_paper", [])), key=lambda x: -len(x[0]))
SME_NAMES: list[tuple[str, str]] = sorted(((norm(q), s["key"]) for s in SUBJECTS if ":" not in s["key"] for q in s.get("sme", [])), key=lambda x: -len(x[0]))
SITE_PATHS: list[tuple[str, str]] = sorted(((p.lower(), s["key"]) for s in SUBJECTS for p in s.get("sites", [])), key=lambda x: -len(x[0]))

DOC_LANGS = {"english": "en", "french": "fr", "spanish": "es", "german": "de", "japanese": "ja", "chinese": "zh", "arabic": "ar", "turkish": "tr", "korean": "ko", "italian": "it", "portuguese": "pt", "russian": "ru"}
AUDIO_LANG = {"eng": "English", "fre": "French", "spa": "Spanish", "ger": "German", "chi": "Chinese", "jpn": "Japanese", "ind": "Indonesian", "ita": "Italian", "kor": "Korean",
              "por": "Portuguese", "ara": "Arabic", "swe": "Swedish", "nor": "Norwegian", "hin": "Hindi", "fin": "Finnish", "dut": "Dutch", "dan": "Danish", "rus": "Russian", "man": "Mandarin"}
TEXT_EXTS = {"pdf", "epub", "docx", "pptx", "html", "htm", "txt"}
MEDIA_EXTS = {"mp4", "mov", "mp3", "m4a", "webm"}
KEEP_EXTS = TEXT_EXTS | MEDIA_EXTS | {"zip", "doc", "ppt", "ppsx", "xlsx", "tns"}
IMAGE_EXTS = {"jpg", "jpeg", "png"}

_SESSION_DIR = re.compile(r"(May|November) (\d{4}) Examination Session", re.I)
_DONATED = re.compile(r"DONATED PAPERS ([MN])(\d{2})", re.I)
_PACK = re.compile(r"^([mn])(\d{2})exampack$", re.I)
_YEAR_DIR = re.compile(r"^(\d{4}) Examination Session$")
_PAPER_MARK = re.compile(r"\b(?:paper\s*|p)(\d)\s?([ab])?\b(.*)$")
_LISTEN = re.compile(r"^(.*?)\blistening comprehension\b(.*)$")
_YEAR_IN_NAME = re.compile(r"(?<!\d)(19[89]\d|20[0-3]\d)(?!\d)")


def _level(text: str) -> str | None:
    t = f" {text} "
    if re.search(r"\b(hl\s?/?\s?sl|hlsl|sl\s?/?\s?hl|sl and hl|hl and sl)\b", t):
        return "HLSL"
    if re.search(r"\b(hl|higher level|aahl|aihl)\b", t):
        return "HL"
    if re.search(r"\b(sl|standard level|aasl|aisl|nm)\b", t):
        return "SL"
    return None


def _session_from_path(parts: tuple[str, ...], name_norm: str) -> tuple[int | None, str | None]:
    year = session = None
    for p in parts:
        m = _SESSION_DIR.search(p)
        if m:
            return int(m.group(2)), m.group(1).capitalize()
        m = _DONATED.search(p)
        if m:
            return 2000 + int(m.group(2)), ("May" if m.group(1).upper() == "M" else "November")
        m = _PACK.match(p)
        if m:
            return 2000 + int(m.group(2)), ("May" if m.group(1).lower() == "m" else "November")
        m = _YEAR_DIR.match(p)
        if m:
            year = int(m.group(1))
    m = re.search(r"\b([mn])(\d{2})\b", name_norm)
    if m:
        return 2000 + int(m.group(2)), ("May" if m.group(1) == "m" else "November")
    m = re.search(r"\b(may|nov|november)\s+(20\d{2})\b", name_norm)
    if m:
        return int(m.group(2)), ("May" if m.group(1) == "may" else "November")
    return year, session


def _match_alias(text: str) -> tuple[str | None, str | None]:
    """Longest alias that the cleaned subject text equals or starts with."""
    text = text.strip()
    if text in PAPER_ALIAS:
        return PAPER_ALIAS[text]
    words = text.split()
    for n in range(len(words) - 1, 0, -1):
        cand = " ".join(words[:n])
        if cand in PAPER_ALIAS:
            return PAPER_ALIAS[cand]
    return None, None


_NOISE = re.compile(r"\b(hl|sl|hlsl|tz\s?[0-9a-d]|zone\s[a-d]|[mn]\d{2}|may|nov|november|20\d{2}|leak|new|asia|tza|tzb|tzc)\b")


def parse_paper(stem: str) -> dict:
    """Parse an exam file name (official or donated spelling) into its parts."""
    n = norm(stem)
    n = re.sub(r"\b(aa|ai)(hl|sl)\b", r"\1 \2", n)
    out: dict = {"paper": None, "level": _level(n), "tz": None, "kind": "question_paper", "doc_lang": None, "part": None, "subject_text": None}
    m = re.search(r"\b(?:tz\s?|zone\s)([0-9a-d])\b", n)
    if m:
        out["tz"] = "TZ" + m.group(1).upper()
    if re.search(r"\b(markscheme|mark scheme|ms)\b", n):
        out["kind"] = "markscheme"
    for part, label in (("question booklet", "question booklet"), ("text booklet", "text booklet"), ("resource booklet", "resource booklet"), ("case study", "case study"),
                        ("insert", "insert"), ("score booklet", "score booklet"), ("reading comprehension", "reading"), ("worked solutions", "worked solutions")):
        if part in n:
            out["part"] = label if not out["part"] else out["part"] + ", " + label
    if out["part"] and any(x in out["part"] for x in ("text booklet", "resource booklet", "case study", "insert", "score booklet")) and out["kind"] != "markscheme":
        out["kind"] = "booklet"
    if "worked solutions" in n:
        out["kind"] = "markscheme"
    lm = _LISTEN.match(n)
    pm = _PAPER_MARK.search(n)
    if pm:
        out["paper"] = pm.group(1) + (pm.group(2) or "").upper()
        head, tail = n[:pm.start()], pm.group(3)
    elif lm:
        out["paper"] = "2"
        out["part"] = "listening"
        head, tail = lm.group(1), lm.group(2)
    else:
        head, tail = n, ""
    if "listening" in n and not out["part"]:
        out["part"] = "listening"
    for word, code in DOC_LANGS.items():
        if re.search(rf"\b{word}\b", tail):
            out["doc_lang"] = code
    out["subject_text"] = re.sub(r"\s+", " ", _NOISE.sub(" ", head)).strip()
    return out


def _title_case(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("_", " ").replace("-", " ")).strip()


def _name_subject(text: str) -> str | None:
    t = norm(text)
    for alias, key in NAME_ALIAS:
        if t == alias or t.startswith(alias + " ") or (" " + alias + " ") in (" " + t + " "):
            return key
    for alias, tag in _GENERIC_LANG_NAMES.items():
        if alias in t:
            return tag
    return None


def _book_kind(name_norm: str) -> str:
    if re.search(r"\b(answers|worked solutions|solutions|mark ?scheme)\b", name_norm):
        return "answers"
    if re.search(r"internal assessment|\bia\b|extended essay|skills for success", name_norm):
        return "coursework_guide"
    if re.search(r"study guide|revision guide|ib prepared|exam preparation|study and revision|essentials|fast facts|revision|in a nutshell|prepare for success|mind map|chapter summaries", name_norm):
        return "revision_guide"
    if re.search(r"workbook|worksheets?|exam practice|skills and practice|questions|quantitative", name_norm):
        return "workbook"
    if re.search(r"\bextra\b|cd rom|calculator", name_norm):
        return "extra"
    return "textbook"


def classify(rel: str) -> dict | None:
    """Metadata for a library file, or None when the file should not be indexed (site assets etc.)."""
    p = PurePosixPath(rel)
    parts = p.parts
    if len(parts) < 2:
        return None
    top, name = parts[0], p.name
    ext = p.suffix.lower().lstrip(".")
    stem = p.stem
    n = norm(stem)
    low = rel.lower()
    r: dict = {"ext": ext, "collection": "other", "kind": "document", "subject": None, "level": None, "title": _title_case(stem), "year": None, "session": None,
               "paper": None, "tz": None, "lang": None, "publisher": None, "topic_code": None, "unit_name": None, "syllabus": None, "note": None,
               "url_kind": "file", "pair_key": None, "text": ext in TEXT_EXTS}

    # ── past papers ──
    if top == "IB PAST PAPERS - YEAR":
        r["collection"] = "past_papers"
        year, session = _session_from_path(parts, n)
        r["year"], r["session"] = year, session
        if ext in ("mp3", "m4a"):
            r["kind"], r["text"] = "audio", False
            m = re.match(r"^[mn]\d{2}2(ab|an)([a-z]{3})(hl|sl)", stem.lower())
            if m and m.group(2) in AUDIO_LANG:
                lang = AUDIO_LANG[m.group(2)]
                key = f"ab_initio:{'Mandarin' if lang == 'Chinese' else lang}" if m.group(1) == "an" else f"lang_b:{'Chinese' if lang == 'Mandarin' else lang}"
                r["subject"] = key if key in BY_KEY else None
                r["level"] = m.group(3).upper()
                r["title"] = f"{lang} {'ab initio' if m.group(1) == 'an' else 'B'} {r['level']} · Listening audio · {session or ''} {year or ''}".strip()
            else:
                r["title"] = f"Listening audio · {_title_case(stem)} · {session or ''} {year or ''}".strip()
            r["paper"] = "2"
            return r
        if ext != "pdf" and ext not in IMAGE_EXTS:
            return None
        if ext in IMAGE_EXTS and not any("DONATED" in x.upper() or _YEAR_DIR.match(x) for x in parts[1:-1] + (parts[1],)):
            return None
        if ext in IMAGE_EXTS and len(parts) > 2 and parts[-2].lower() in ("images", "resources", "css", "js", "fonts"):
            return None
        info = parse_paper(stem)
        key, legacy = _match_alias(info["subject_text"] or "")
        if not key:
            key = _language_key_from_text(info["subject_text"] or "")
        subj = get_subject(key) if key else None
        if not subj:
            key = None
        r.update(kind=info["kind"], paper=info["paper"], level=info["level"], tz=info["tz"], lang=info["doc_lang"], subject=key, text=(ext == "pdf"))
        subj_label = subj["short"] if subj else _title_case(info["subject_text"] or stem).title()
        if key:
            s = subj
            if legacy:
                r["syllabus"], r["note"] = "legacy", legacy
            elif year and year < s.get("syllabus_from", 0):
                r["syllabus"], r["note"] = "legacy", f"Previous syllabus (the current course was first examined in {s['syllabus_from']})"
            else:
                r["syllabus"] = "current"
        bits = [subj_label + (f" {info['level']}" if info["level"] and info["level"] != "HLSL" else " HL/SL" if info["level"] == "HLSL" else "")]
        if info["paper"]:
            bits.append(f"Paper {info['paper']}")
        if info["part"]:
            bits.append(info["part"].capitalize())
        when = " ".join(x for x in [session, str(year) if year else None, info["tz"]] if x)
        if when:
            bits.append(when)
        if info["kind"] == "markscheme":
            bits.append("Markscheme")
        if info["doc_lang"] and info["doc_lang"] != "en":
            bits.append(info["doc_lang"].upper() + " version")
        r["title"] = " · ".join(bits)
        base = re.sub(r"\b(markscheme|mark scheme|ms)\b", " ", n)
        r["pair_key"] = str(p.parent) + "|" + re.sub(r"\s+", " ", base).strip()
        return r

    # ── textbooks ──
    if top == "IB BOOKS":
        if ext not in KEEP_EXTS:
            return None
        r["collection"] = "books"
        r["kind"] = _book_kind(n)
        r["level"] = _level(n)
        r["publisher"] = next((x.title() for x in parts[2:-1] if x.isupper() or x in ("Level7 Education", "DS Education")), None)
        ys = _YEAR_IN_NAME.findall(stem)
        r["year"] = int(ys[-1]) if ys else None
        if re.search(r"\bspanish\b|matem[aá]ticas|\bfisica\b|edici", n):
            r["lang"] = "es"
        elif re.search(r"\bfrench\b|\bfran[cç]ais", n):
            r["lang"] = "fr"
        sub = "/".join(parts[1:-1]).lower()
        if sub.startswith("group 5 - mathematics"):
            if "mathematical studies" in sub:
                r["subject"], r["syllabus"], r["note"] = "math_ai", "legacy", "Old syllabus (Mathematical Studies)"
            elif re.search(r"mathematics (higher|standard) level|further mathematics", sub):
                r["subject"], r["syllabus"], r["note"] = "math_aa", "legacy", "Old syllabus (Maths HL/SL)"
                r["level"] = r["level"] or ("HL" if "higher" in sub or "further" in sub else "SL")
            else:
                inner = low.split("/aa and ai/", 1)[-1].replace("-", " ").replace("_", " ")
                if re.search(r"analysis and approaches|an[aá]lisis y enfoques|\baa\b", inner):
                    r["subject"] = "math_aa"
                elif re.search(r"applications and interpretation|aplicaciones e interpretaci|\bai\b|\bmai\b", inner):
                    r["subject"] = "math_ai"
                else:
                    r["subject"] = "shared:math"
        elif sub.startswith("core - theory of knowledge"):
            r["subject"] = "tok"
        elif sub.startswith("core - extended essay"):
            r["subject"] = "ee"
        elif "/language a" in "/" + sub and sub.endswith(("language a", "language a/hodder")):
            r["subject"] = "shared:lang_a"
        else:
            for frag, key in BOOK_DIRS:
                if frag in sub:
                    r["subject"] = key
                    break
        if r["subject"] in BY_KEY and not r["syllabus"]:
            sf = BY_KEY[r["subject"]].get("syllabus_from", 0)
            if r["year"]:
                r["syllabus"] = "current" if r["year"] >= sf - 3 else "legacy"
                if r["syllabus"] == "legacy":
                    r["note"] = f"Written for an earlier syllabus (current course first examined {sf})"
        r["text"] = ext in ("pdf", "epub", "docx")
        return r

    # ── question banks (rendered by the view site) ──
    if top == "IB QUESTIONBANKS":
        r["collection"], r["url_kind"] = "questionbank", "view"
        edition = parts[1] if len(parts) > 1 else ""
        ed_label = re.sub(r"^\d+\.\s*", "", edition)
        if len(parts) == 3 and name.lower() == "index.html":
            r.update(kind="qb_home", title=f"IB Questionbank · {ed_label}", text=False)
            return r
        m = re.search(r"/questionbanks/(\d+-dp-[a-z0-9-]+)(?:/(syllabus_sections)/(\d+)\.html|\.html)$", rel)
        if m:
            slug_ = m.group(1)
            r["subject"] = next((k for q, k in QB_SLUGS if q in slug_), None)
            label = slug_.split("-dp-", 1)[1].replace("-", " ").title()
            if "last-assessment-2024" in slug_ or edition.startswith("4."):
                r["syllabus"], r["note"] = "legacy", "Questions from the previous syllabus"
            if m.group(2):
                r.update(kind="topic_questions", title=f"{label} · syllabus section {m.group(3)}", text=True)
            else:
                r.update(kind="qb_home", title=f"IB Questionbank · {label} · {ed_label}", text=False)
            return r
        m = re.search(r" - PAPER/(HTML|PDFs)/([^/]+)/([^/]+)/([^/]+)\.(html|pdf)$", rel)
        if m and "/images/" not in rel:
            subj_dir, topic_dir, fname = m.group(2), m.group(3), m.group(4)
            r["subject"] = next((k for q, k in QB_PAPER_NAMES if norm(subj_dir).startswith(q)), None)
            r["level"] = _level(norm(fname) + " " + norm(subj_dir))
            r["kind"] = "markscheme" if re.search(r"mark ?sc?h?eme", fname, re.I) else "topic_questions"
            pm = re.search(r"paper\s?(\d)", fname, re.I)
            r["paper"] = pm.group(1) if pm else None
            r["unit_name"] = re.sub(r"\s*HTML$", "", topic_dir)
            r["title"] = " · ".join(x for x in [subj_dir, r["unit_name"], (r["level"] or ""), (f"Paper {r['paper']}" if r["paper"] else ""), ("Markscheme" if r["kind"] == "markscheme" else "Questions")] if x)
            r["syllabus"], r["note"] = ("legacy", "Questions from the previous syllabus") if (edition.startswith("4.") or r["subject"] in ("physics", "chemistry", "biology")) else (None, None)
            if m.group(5) == "pdf":
                r["url_kind"] = "file"
            r["pair_key"] = str(p.parent) + "|" + re.sub(r"mark ?sc?h?eme|questions?", "", fname, flags=re.I).strip(" -_")
            return r
        if edition == "Mortar & Pestle" and name.lower() == "index.html":
            r.update(kind="qb_home", title="Mortar & Pestle question bank", text=False)
            return r
        return None

    # ── revision notes ──
    if top == "home" and "SaveMyExams - Notes" in parts:
        if ext != "pdf":
            return None
        i = parts.index("SaveMyExams - Notes")
        folder = parts[i + 1] if len(parts) > i + 2 else ""
        fn = norm(folder)
        r["collection"], r["kind"], r["publisher"] = "notes", "notes", "Save My Exams"
        r["subject"] = next((k for q, k in SME_NAMES if fn.startswith(q)), None)
        r["level"] = _level(fn)
        ym = _YEAR_IN_NAME.search(folder)
        r["year"] = int(ym.group(1)) if ym else None
        if r["subject"] in BY_KEY and r["year"] and r["year"] < BY_KEY[r["subject"]]["syllabus_from"]:
            r["syllabus"], r["note"] = "legacy", "Notes for the previous syllabus"
        elif r["subject"]:
            r["syllabus"] = "current"
        r["unit_name"] = re.sub(r"^\d+\.\s*", "", parts[i + 2]) if len(parts) > i + 3 else None
        cm = re.match(r"^(\d+(?:\.\d+)*)[\s-]+(.*)$", stem)
        if cm:
            r["topic_code"], rest = cm.group(1), cm.group(2)
        else:
            rest = stem
            um = re.match(r"^(\d+)\.", parts[i + 2]) if len(parts) > i + 3 else None
            r["topic_code"] = um.group(1) if um else None
        nice = re.sub(r"\s+", " ", rest.replace("--", " – ").replace("-", " ")).strip()
        r["title"] = (f"{r['topic_code']} " if cm else "") + nice[:1].upper() + nice[1:]
        return r

    # ── offline study sites ──
    if top in ("ThinkIB", "StudyIB"):
        if "InThinking Math mocks" in parts:
            if ext != "pdf":
                return None
            r.update(collection="mocks", subject="math_aa", level=_level(norm(parts[-2])), syllabus="current",
                     kind="markscheme" if "solution" in n else "question_paper", publisher="InThinking")
            pm = re.search(r"\bp(\d)\b", n)
            r["paper"] = pm.group(1) if pm else None
            r["title"] = f"InThinking mock · Maths AA {r['level'] or ''} · {_title_case(stem)}"
            r["pair_key"] = str(p.parent) + "|" + re.sub(r"\b(questions|worked solutions)\b", "", n).strip()
            return r
        if ext not in ("html", "htm", "pdf"):
            return None
        r["collection"], r["url_kind"], r["publisher"] = "site", ("view" if ext != "pdf" else "file"), ("InThinking" if top == "ThinkIB" else "StudyIB")
        r["subject"] = next((k for q, k in SITE_PATHS if low.startswith(q.lower() + "/") or low == q.lower() + ".html"), None)
        if ext == "pdf":
            r["kind"] = "document"
            return r
        if "/page/" in rel:
            r["kind"] = "page"
        elif len(parts) <= 4 and (name.lower() == "index.html" or stem.lower() == parts[-2].lower() or len(parts) == 2):
            r["kind"], r["text"] = "site_home", False
        else:
            return None
        if r["subject"] is None and r["kind"] == "page":
            return None
        r["title"] = _title_case(stem).capitalize()
        return r

    # ── videos and subject packs ──
    if top == "TeachMe Biology":
        r["subject"], r["publisher"], r["syllabus"] = "biology", "TeachMe", "current"
        if ext in MEDIA_EXTS:
            r["collection"], r["kind"], r["text"] = "videos", "video", False
            r["level"] = _level(norm(parts[1])) or _level(n)
            cm = re.match(r"^\(\s*([A-D]\d\.\d)\s*\)\s*-\s*(.*?)\s*-\s*IB Biology", stem)
            if cm:
                r["topic_code"], r["title"] = cm.group(1), f"{cm.group(1)} {cm.group(2)} (video)"
            return r
        if ext == "pdf":
            r["collection"] = "mocks"
            r["kind"] = "markscheme" if "markscheme" in n else "question_paper"
            r["level"] = _level(n)
            pm = _PAPER_MARK.search(n)
            r["paper"] = (pm.group(1) + (pm.group(2) or "").upper()) if pm else None
            r["title"] = f"TeachMe mock · Biology · {_title_case(stem)}"
            r["pair_key"] = str(p.parent) + "|" + re.sub(r"\bmarkscheme\b", "", n).strip()
            return r
        return None
    if top == "Lewwinski Business Management":
        r["subject"], r["publisher"], r["syllabus"] = "business_management", "Lewwinski", "current"
        cm = re.match(r"^\((\d\.\d)\)\s*(.*)$", stem)
        if ext in MEDIA_EXTS:
            r["collection"], r["kind"], r["text"] = "videos", "video", False
            if cm:
                r["topic_code"], r["title"] = cm.group(1), f"{cm.group(1)} {cm.group(2)} (video)"
            return r
        if ext in ("pdf", "docx", "pptx"):
            r["collection"], r["kind"] = "notes", "notes"
            if cm:
                r["topic_code"] = cm.group(1)
            return r
        return None
    if top == "IB Biz (BM Case Studies)":
        if ext != "pdf":
            return None
        r.update(collection="practice", kind="markscheme" if re.search(r"\bms\b", n) else "worksheet", subject="business_management", level=_level(n), syllabus="current")
        r["pair_key"] = str(p.parent) + "|" + re.sub(r"\bms\b", "", n).strip()
        return r

    # ── official documents ──
    if top == "IB SUBJECT GUIDES":
        if ext != "pdf":
            return None
        r["collection"], r["kind"] = "official", "subject_guide"
        r["subject"] = _name_subject(" ".join(parts[1:-1]) + " " + stem)
        for word, code in DOC_LANGS.items():
            if re.search(rf"\b{word}\b", n):
                r["lang"] = code
        ys = _YEAR_IN_NAME.findall(stem)
        r["year"] = int(ys[-1]) if ys else None
        if r["subject"] in BY_KEY and r["year"]:
            sf = BY_KEY[r["subject"]].get("syllabus_from", 0)
            r["syllabus"] = "current" if r["year"] >= sf else "legacy"
            if r["syllabus"] == "legacy":
                r["note"] = f"Guide for an earlier syllabus (current course first examined {sf})"
        return r
    if top == "IB DOCUMENTS":
        if ext not in KEEP_EXTS:
            return None
        r["collection"] = "official"
        sub = parts[1] if len(parts) > 2 else ""
        kinds = {"Data and Formula Booklets": "data_booklet", "Grade Boundaries": "grade_boundaries", "Examination Schedules": "exam_schedule", "IB Grade Descriptors": "grade_descriptors",
                 "Language B and ab initio Paper 1 Text Types": "text_types", "Case Studies": "case_study", "Use of Calculators in Examinations": "calculator_rules",
                 "Conduct of IB Diploma Programme Examinations": "exam_conduct", "Teacher Support Materials - PDF": "teacher_support", "Exam Paper Style Samples": "paper_samples"}
        r["kind"] = kinds.get(sub, "official_doc")
        if r["kind"] in ("data_booklet", "case_study", "teacher_support"):
            r["subject"] = _name_subject(" ".join(parts[2:-1]) + " " + stem)
        if r["kind"] == "text_types":
            lang_key = _language_key_from_text(n.split(" and ab initio")[0]) or _language_key_from_text(n)
            r["subject"] = lang_key if (lang_key and get_subject(lang_key)) else "shared:lang_b"
            r["title"] = "Paper 1 text types · " + _title_case(stem)
        for word, code in DOC_LANGS.items():
            if re.search(rf"\b{word}\b", n) or f"/{word}/" in low:
                r["lang"] = code
        ys = _YEAR_IN_NAME.findall(stem)
        r["year"] = int(ys[-1]) if ys else None
        sm = re.search(r"\b(may|november)\b", n)
        r["session"] = sm.group(1).capitalize() if sm else None
        if r["kind"] == "data_booklet" and r["subject"] in BY_KEY and r["year"]:
            sf = BY_KEY[r["subject"]].get("syllabus_from", 0)
            if r["year"] < sf - 1:
                r["syllabus"], r["note"] = "legacy", "Booklet for an earlier syllabus"
        return r
    if top == "IB SPECIMEN PAPERS":
        if ext not in ("pdf", "mp3"):
            return None
        info = parse_paper(stem)
        r.update(collection="specimen", kind=("audio" if ext == "mp3" else info["kind"]), paper=info["paper"], level=info["level"], lang=info["doc_lang"], text=(ext == "pdf"))
        r["subject"] = _name_subject(" ".join(parts[2:-1])) or _match_alias(info["subject_text"] or "")[0]
        ys = _YEAR_IN_NAME.findall(stem)
        r["year"] = int(ys[-1]) if ys else None
        sf = (get_subject(r["subject"]) or {}).get("syllabus_from", 0) if r["subject"] else 0
        if r["year"] and sf and r["year"] < sf - 1:
            r["syllabus"], r["note"] = "legacy", "Specimen for an earlier syllabus"
        else:
            r["syllabus"] = "current"
        for word, code in DOC_LANGS.items():
            if re.search(rf"\b{word}\b", n.split(" ab initio")[0].split(" b ")[0][-12:]) or n.endswith(word):
                r["lang"] = code
        r["title"] = "Specimen · " + _title_case(stem)
        r["pair_key"] = str(p.parent) + "|" + re.sub(r"\b(markscheme|mark scheme|ms)\b", " ", n).strip()
        return r
    if top == "IB OFFICIAL EE EXEMPLARS":
        if len(parts) > 2 and parts[1] == "Inspiring Extended Essays":
            if len(parts) == 3 and name.lower() == "index.html":
                r.update(collection="exemplars", kind="site_home", subject="ee", title="Inspiring Extended Essays (interactive)", url_kind="view", text=False)
                return r
            return None
        if ext not in ("pdf", "docx"):
            return None
        r["collection"] = "exemplars"
        if "Clastify IA EXEMPLARS" in parts:
            r["kind"] = "ia_exemplar"
            head = norm(re.split(r"\s+-\s+", stem, maxsplit=1)[0]) if " - " in stem else norm(" ".join(stem.split()[:3]))
            r["subject"] = _match_alias(head)[0] or _name_subject(head)
            r["title"] = "IA exemplar · " + stem
            return r
        r["kind"] = "ee_exemplar"
        ctx = " ".join(parts[2:-1])
        r["subject"] = "tok" if "theory of knowledge" in ctx.lower() else (_name_subject(ctx) or "ee")
        if r["subject"] == "ee" or r["subject"] is None:
            r["subject"] = "ee"
        r["unit_name"] = parts[-2] if len(parts) > 3 else None
        r["title"] = "EE exemplar · " + _title_case(stem)
        return r
    if top == "theoryofknowledge.net":
        if ext not in KEEP_EXTS:
            return None
        r.update(collection="exemplars" if "exemplar" in low or "/examples/" in low else "notes", subject="tok", publisher="theoryofknowledge.net")
        r["kind"] = "tok_exemplar" if r["collection"] == "exemplars" else "notes"
        r["unit_name"] = parts[1]
        return r
    if top == "LitCharts":
        if ext != "pdf":
            return None
        r.update(collection="notes", subject="shared:english_a", publisher="LitCharts", kind="literary_term" if "Literary Terms" in parts else "lit_guide")
        r["title"] = re.sub(r"\s*LitChart$", "", _title_case(stem)) + (" (literary term)" if r["kind"] == "literary_term" else " (LitChart study guide)")
        r["unit_name"] = parts[1] if len(parts) > 2 else None
        return r
    if top == "LitLearn":
        if ext != "pdf":
            return None
        r.update(collection="notes", kind="revision_guide", subject="shared:english_a", publisher="LitLearn")
        return r
    if top == "Kush UK Stuff":
        if ext != "pdf":
            return None
        r.update(collection="extra", kind="admissions_test", title="UK admissions · " + _title_case(stem))
        return r

    if ext in KEEP_EXTS and ext not in ("html", "htm"):
        return r
    return None
