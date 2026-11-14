"""IB God HTTP API."""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import advice, auth, backup, catalog, coach, config, db, feedback, indexer, llm, planner, search
from .auth import User, current_user
from .knowledge import FAMILY_TIPS, GRADE_BANDS, RUBRICS, TECHNIQUES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("ibgod")

CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; media-src 'self'; "
       "manifest-src 'self'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
SUBJECT_KEY = re.compile(r"^(?:[a-z_]{2,40}|(?:lang_a_ll|lang_a_lit|lang_b|ab_initio):[A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)?|custom:[A-Za-z0-9][A-Za-z0-9 &'()+.,-]{0,58})$")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
INLINE_TYPES = {"pdf": "application/pdf", "mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime", "mp3": "audio/mpeg", "m4a": "audio/mp4",
                "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "txt": "text/plain; charset=utf-8"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    os.umask(0o077)  # database, WAL and temp files are readable by this service account only
    if config.DEV_USER:
        if auth._resolve_proxies(force=True):
            raise RuntimeError("IBGOD_DEV_USER must never be set on a network where the reverse proxy is reachable")
        log.warning("DEVELOPMENT MODE: every request is treated as user %r. Never use this behind the public proxy.", config.DEV_USER)
    db.init()
    for path in (config.DATA_DIR, config.DB_PATH):
        try:
            os.chmod(path, 0o700 if path.is_dir() else 0o600)
        except OSError:
            pass
    if config.AUTO_INDEX:
        indexer.start()
    if config.FEEDBACK_WORKER:
        feedback.start()
        backup.start()
    yield
    indexer.stop()


app = FastAPI(title="IB God", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.middleware("http")
async def security(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/"):
        try:
            auth.csrf_guard(request)
        except HTTPException as e:
            return JSONResponse({"detail": e.detail}, status_code=e.status_code)
    response: Response = await call_next(request)
    h = response.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("Referrer-Policy", "same-origin")
    h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    h.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
    if not path.startswith("/api/files/"):
        h.setdefault("Content-Security-Policy", CSP)
        h.setdefault("X-Frame-Options", "DENY")
    if path.startswith("/api/") and "cache-control" not in h:
        h["Cache-Control"] = "no-store"
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Something went wrong on the server."}, status_code=500)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def check_key(key: str) -> str:
    if not SUBJECT_KEY.match(key) or not catalog.get_subject(key):
        raise HTTPException(404, "Unknown subject")
    return key


def check_date(s: str) -> str:
    if not ISO_DATE.match(s or "") or planner.parse_date(s) is None:
        raise HTTPException(422, "Invalid date")
    return s


def my_subject(con, username: str, key: str) -> dict:
    row = db.one(con, "SELECT * FROM user_subjects WHERE username=? AND subject=?", (username, key))
    if not row:
        raise HTTPException(404, "You do not take this subject")
    return row


def subject_label(key: str | None) -> str:
    s = catalog.get_subject(key) if key else None
    return s["short"] if s else ""


def task_public(t: dict) -> dict:
    meta = json.loads(t.get("meta") or "{}")
    return {"id": t["id"], "subject": t["subject"], "subject_name": subject_label(t["subject"]), "kind": t["kind"], "title": t["title"], "detail": t["detail"],
            "topic_code": t["topic_code"], "date": t["date"], "minutes": t["minutes"], "status": t["status"], "pinned": bool(t["pinned"]), "origin": t["origin"],
            "resources": meta.get("resources") or [], "markschemes": meta.get("markschemes") or [], "legacy": bool(meta.get("legacy")), "n": meta.get("n")}


# ───────────────────────── session / profile ─────────────────────────
_catalog_cache: dict = {"at": 0.0, "data": None}


def catalogue() -> list[dict]:
    if _catalog_cache["data"] is not None and time.time() - _catalog_cache["at"] < 600:
        return _catalog_cache["data"]
    items = {s["key"]: {**s, "resources": 0} for s in catalog.catalogue_summary()}
    with db.ro() as con:
        for r in db.rows(con, "SELECT subject, COUNT(*) n FROM resources WHERE subject IS NOT NULL GROUP BY subject"):
            key = r["subject"]
            if key in items:
                items[key]["resources"] = r["n"]
            elif ":" in key and not key.startswith(("shared:", "custom:")) and r["n"] >= 6:
                s = catalog.get_subject(key)
                if s:
                    items[key] = {"key": s["key"], "name": s["name"], "short": s["short"], "group": s["group"], "group_name": catalog.GROUP_NAMES.get(s["group"], "Other"),
                                  "levels": s["levels"], "family": s.get("family"), "language": s.get("language"), "resources": r["n"]}
    data = sorted(items.values(), key=lambda s: (s["group"], s["name"]))
    if any(s["resources"] for s in data):
        _catalog_cache.update(at=time.time(), data=data)
    return data


def me_payload(user: User) -> dict:
    with db.ro() as con:
        row = db.one(con, "SELECT * FROM users WHERE username=?", (user.username,)) or {}
        subs = db.rows(con, "SELECT * FROM user_subjects WHERE username=? ORDER BY position, id", (user.username,))
    settings = json.loads(row.get("settings") or "{}")
    for s in subs:
        c = catalog.get_subject(s["subject"]) or {}
        s.update(name=c.get("name", s["subject"]), short=c.get("short", s["subject"]), group=c.get("group", 0), family=c.get("family"))
    idx = indexer.status()
    return {"username": user.username, "display_name": row.get("display_name") or user.name, "email": row.get("email") or user.email, "is_admin": user.is_admin,
            "onboarded": bool(row.get("onboarded")), "settings": settings, "subjects": subs, "today": planner.today_local().isoformat(),
            "llm": llm.info(), "index": {"phase": idx["phase"], "text_done": idx["text_done"], "text_total": idx["text_total"]},
            "links": {"logout": config.LOGOUT_URL, "docs": config.DOCS_BASE, "view": config.VIEW_BASE}}


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/me")
def get_me(user: User = Depends(current_user)):
    return me_payload(user)


@app.get("/api/ping")
def ping(user: User = Depends(current_user)):
    return {"ok": True, "today": planner.today_local().isoformat()}


@app.get("/api/catalog")
def get_catalog(user: User = Depends(current_user)):
    return {"subjects": catalogue(), "groups": catalog.GROUP_NAMES}


@app.get("/api/textbooks")
def textbooks(subject: str, level: str = "HL", user: User = Depends(current_user)):
    check_key(subject)
    tags = catalog.subject_tags(subject)
    with db.ro() as con:
        rows = db.rows(con, f"""SELECT {search.RES_COLS} FROM resources r WHERE r.subject IN ({','.join('?' * len(tags))}) AND r.collection='books' AND r.kind='textbook'
                                AND r.ext IN ('pdf','epub') AND (r.level IS NULL OR r.level IN (?, 'HLSL')) AND (r.lang IS NULL OR r.lang='en') AND COALESCE(r.syllabus,'current')='current'
                                ORDER BY COALESCE(r.year,0) DESC, r.title LIMIT 60""", (*tags, level if level in ("HL", "SL") else "HL"))
    return {"textbooks": [search.public(r) for r in rows]}


class SubjectIn(BaseModel):
    subject: str = Field(max_length=80)
    level: Literal["HL", "SL"]
    current_grade: int = Field(ge=1, le=7)
    target_grade: int = Field(ge=1, le=7)
    textbook_id: int | None = None
    textbook_other: str | None = Field(default=None, max_length=160)
    exam_date: str | None = None

    @field_validator("exam_date")
    @classmethod
    def _d(cls, v):
        if v in (None, ""):
            return None
        if not ISO_DATE.match(v) or planner.parse_date(v) is None:
            raise ValueError("invalid date")
        return v


class SetupIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    session_month: Literal["May", "November"]
    session_year: int = Field(ge=2024, le=2040)
    subjects: list[SubjectIn] = Field(min_length=1, max_length=10)
    weekly_minutes: list[int] = Field(min_length=7, max_length=7)
    exam_start: str | None = None

    @field_validator("weekly_minutes")
    @classmethod
    def _w(cls, v):
        if any(x < 0 or x > 720 for x in v):
            raise ValueError("minutes per day must be between 0 and 720")
        return v

    @field_validator("exam_start")
    @classmethod
    def _e(cls, v):
        if v in (None, ""):
            return None
        if not ISO_DATE.match(v) or planner.parse_date(v) is None:
            raise ValueError("invalid date")
        return v


def _clean_text(s: str | None, n: int) -> str | None:
    if s is None:
        return None
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", s).strip()[:n] or None


def _save_subject(con, username: str, s: SubjectIn, position: int) -> None:
    key = check_key(s.subject)
    subj = catalog.get_subject(key)
    level = s.level if s.level in subj["levels"] else subj["levels"][0]
    target = max(s.target_grade, s.current_grade)
    tb = s.textbook_id
    if tb is not None and not con.execute("SELECT 1 FROM resources WHERE id=? AND collection='books'", (tb,)).fetchone():
        tb = None
    prev = db.one(con, "SELECT current_grade FROM user_subjects WHERE username=? AND subject=?", (username, key))
    con.execute("""INSERT INTO user_subjects(username, subject, level, current_grade, target_grade, textbook_id, textbook_other, exam_date, position) VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(username, subject) DO UPDATE SET level=excluded.level, current_grade=excluded.current_grade, target_grade=excluded.target_grade,
                   textbook_id=excluded.textbook_id, textbook_other=excluded.textbook_other, exam_date=excluded.exam_date, position=excluded.position""",
                (username, key, level, s.current_grade, target, tb, _clean_text(s.textbook_other, 160), s.exam_date, position))
    if not prev or prev["current_grade"] != s.current_grade:
        con.execute("INSERT INTO grade_log(username, subject, date, grade, note) VALUES(?,?,?,?,?)", (username, key, planner.today_local().isoformat(), s.current_grade, "setup" if not prev else "update"))


@app.post("/api/setup")
def setup(body: SetupIn, user: User = Depends(current_user)):
    keys = [s.subject for s in body.subjects]
    if len(set(keys)) != len(keys):
        raise HTTPException(422, "Each subject can only be added once")
    with db.tx() as con:
        settings = auth.get_settings(con, user.username)
        settings.update(session_month=body.session_month, session_year=body.session_year, weekly_minutes=body.weekly_minutes, exam_start=body.exam_start)
        name = _clean_text(body.display_name, 80)
        con.execute("UPDATE users SET settings=?, onboarded=1, display_name=COALESCE(?, display_name) WHERE username=?", (json.dumps(settings), name, user.username))
        existing = {r["subject"] for r in db.rows(con, "SELECT subject FROM user_subjects WHERE username=?", (user.username,))}
        for gone in existing - set(keys):
            con.execute("DELETE FROM user_subjects WHERE username=? AND subject=?", (user.username, gone))
            con.execute("DELETE FROM tasks WHERE username=? AND subject=? AND status='todo'", (user.username, gone))
        for i, s in enumerate(body.subjects):
            _save_subject(con, user.username, s, i)
        summary = planner.generate(con, user.username, keep_pinned=True)
        issues = planner.evaluate(con, user.username)
    return {"me": me_payload(user), "plan": summary, "issues": issues}


class SettingsIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    session_month: Literal["May", "November"] | None = None
    session_year: int | None = Field(default=None, ge=2024, le=2040)
    weekly_minutes: list[int] | None = Field(default=None, min_length=7, max_length=7)
    exam_start: str | None = None
    clear_exam_start: bool = False
    theme: Literal["auto", "light", "dark"] | None = None


@app.put("/api/settings")
def put_settings(body: SettingsIn, user: User = Depends(current_user)):
    if body.weekly_minutes is not None and any(x < 0 or x > 720 for x in body.weekly_minutes):
        raise HTTPException(422, "Minutes per day must be between 0 and 720")
    if body.exam_start:
        check_date(body.exam_start)
    with db.tx() as con:
        settings = auth.get_settings(con, user.username)
        before = json.dumps({k: settings.get(k) for k in ("session_month", "session_year", "weekly_minutes", "exam_start")}, sort_keys=True)
        for k in ("session_month", "session_year", "weekly_minutes", "theme"):
            v = getattr(body, k)
            if v is not None:
                settings[k] = v
        if body.exam_start:
            settings["exam_start"] = body.exam_start
        elif body.clear_exam_start:
            settings["exam_start"] = None
        name = _clean_text(body.display_name, 80)
        con.execute("UPDATE users SET settings=?, display_name=COALESCE(?, display_name) WHERE username=?", (json.dumps(settings), name, user.username))
        after = json.dumps({k: settings.get(k) for k in ("session_month", "session_year", "weekly_minutes", "exam_start")}, sort_keys=True)
        issues = planner.evaluate(con, user.username)
    return {"me": me_payload(user), "replan_suggested": before != after, "issues": issues}


# ───────────────────────── subjects ─────────────────────────
@app.post("/api/subjects")
def add_subject(body: SubjectIn, user: User = Depends(current_user)):
    with db.tx() as con:
        n = con.execute("SELECT COUNT(*) FROM user_subjects WHERE username=?", (user.username,)).fetchone()[0]
        exists = con.execute("SELECT 1 FROM user_subjects WHERE username=? AND subject=?", (user.username, body.subject)).fetchone()
        if n >= 10 and not exists:
            raise HTTPException(422, "You can have at most 10 subjects")
        _save_subject(con, user.username, body, n)
    return {"me": me_payload(user), "replan_suggested": True}


class SubjectPatch(BaseModel):
    level: Literal["HL", "SL"] | None = None
    current_grade: int | None = Field(default=None, ge=1, le=7)
    target_grade: int | None = Field(default=None, ge=1, le=7)
    textbook_id: int | None = None
    clear_textbook: bool = False
    textbook_other: str | None = Field(default=None, max_length=160)
    exam_date: str | None = None
    clear_exam_date: bool = False


@app.patch("/api/subjects/{key}")
def patch_subject(key: str, body: SubjectPatch, user: User = Depends(current_user)):
    check_key(key)
    with db.tx() as con:
        row = my_subject(con, user.username, key)
        subj = catalog.get_subject(key)
        level = body.level if body.level in subj["levels"] else row["level"]
        cur = body.current_grade or row["current_grade"]
        target = max(body.target_grade or row["target_grade"], cur)
        tb = row["textbook_id"]
        if body.clear_textbook:
            tb = None
        elif body.textbook_id is not None:
            if not con.execute("SELECT 1 FROM resources WHERE id=? AND collection='books'", (body.textbook_id,)).fetchone():
                raise HTTPException(422, "Unknown textbook")
            tb = body.textbook_id
        exam = row["exam_date"]
        if body.clear_exam_date:
            exam = None
        elif body.exam_date:
            exam = check_date(body.exam_date)
        other = _clean_text(body.textbook_other, 160) if body.textbook_other is not None else row["textbook_other"]
        con.execute("UPDATE user_subjects SET level=?, current_grade=?, target_grade=?, textbook_id=?, textbook_other=?, exam_date=? WHERE id=?", (level, cur, target, tb, other, exam, row["id"]))
        if cur != row["current_grade"]:
            con.execute("INSERT INTO grade_log(username, subject, date, grade, note) VALUES(?,?,?,?,?)", (user.username, key, planner.today_local().isoformat(), cur, "update"))
        changed = (level, cur, target, exam) != (row["level"], row["current_grade"], row["target_grade"], row["exam_date"])
    _topic_cache.clear()
    return {"ok": True, "replan_suggested": changed}


@app.delete("/api/subjects/{key}")
def delete_subject(key: str, user: User = Depends(current_user)):
    with db.tx() as con:
        my_subject(con, user.username, key)
        con.execute("DELETE FROM user_subjects WHERE username=? AND subject=?", (user.username, key))
        con.execute("DELETE FROM tasks WHERE username=? AND subject=? AND status='todo'", (user.username, key))
        con.execute("DELETE FROM topic_state WHERE username=? AND subject=?", (user.username, key))
    return {"me": me_payload(user), "replan_suggested": True}


@app.get("/api/subjects/{key}")
def get_subject(key: str, user: User = Depends(current_user)):
    check_key(key)
    with db.tx() as con:
        row = my_subject(con, user.username, key)
        profile = planner.load_profile(con, user.username)
        pub = catalog.public_subject(key)
        states = {r["topic_code"]: r for r in db.rows(con, "SELECT * FROM topic_state WHERE username=? AND subject=?", (user.username, key))}
        units = []
        for u in pub["units"]:
            ts = []
            for t in u["topics"]:
                if t["hl_only"] and row["level"] != "HL":
                    continue
                st = states.get(t["code"]) or {}
                ts.append({"code": t["code"], "name": st.get("custom_name") or t["name"], "default_name": t["name"], "hl_only": t["hl_only"], "optional": t["optional"],
                           "enabled": t["default_on"] if st.get("enabled") is None else bool(st["enabled"]), "confidence": st.get("confidence")})
            if ts:
                units.append({"code": u["code"], "name": u["name"], "topics": ts})
        tb = db.one(con, f"SELECT {search.RES_COLS} FROM resources r WHERE r.id=?", (row["textbook_id"],)) if row["textbook_id"] else None
        done = {r["topic_code"]: r["n"] for r in db.rows(con, "SELECT topic_code, COUNT(*) n FROM tasks WHERE username=? AND subject=? AND status='done' AND topic_code IS NOT NULL GROUP BY 1", (user.username, key))}
        grades = db.rows(con, "SELECT date, grade FROM grade_log WHERE username=? AND subject=? ORDER BY date, id", (user.username, key))
        plan_info = (db.get_meta(con, f"plan:{user.username}", {}) or {}).get("subjects", {}).get(key)
        return {"subject": {k: pub[k] for k in ("key", "name", "short", "group", "group_name", "levels", "family", "syllabus_from", "note", "generic")},
                "assessment": pub["assessment"].get(row["level"], []), "mine": row, "units": units, "textbook": search.public(tb) if tb else None,
                "path": advice.subject_path(con, user.username, profile, row), "overview": search.subject_overview(con, key, row["level"]),
                "done_by_topic": done, "grades": grades, "plan": plan_info, "exam_date": planner.subject_end(profile, row).isoformat()}


class TopicIn(BaseModel):
    enabled: bool | None = None
    confidence: int | None = Field(default=None, ge=0, le=5)
    custom_name: str | None = Field(default=None, max_length=120)


@app.put("/api/subjects/{key}/topics/{code}")
def put_topic(key: str, code: str, body: TopicIn, user: User = Depends(current_user)):
    check_key(key)
    with db.tx() as con:
        row = my_subject(con, user.username, key)
        if code not in {t["code"] for t in catalog.topics_for(key, row["level"])}:
            raise HTTPException(404, "Unknown topic")
        st = db.one(con, "SELECT * FROM topic_state WHERE username=? AND subject=? AND topic_code=?", (user.username, key, code)) or {}
        enabled = st.get("enabled") if body.enabled is None else int(body.enabled)
        conf = st.get("confidence") if body.confidence is None else (body.confidence or None)
        name = st.get("custom_name") if body.custom_name is None else _clean_text(body.custom_name, 120)
        con.execute("""INSERT INTO topic_state(username, subject, topic_code, enabled, confidence, custom_name) VALUES(?,?,?,?,?,?)
                       ON CONFLICT(username, subject, topic_code) DO UPDATE SET enabled=excluded.enabled, confidence=excluded.confidence, custom_name=excluded.custom_name""",
                    (user.username, key, code, enabled, conf, name))
    return {"ok": True}


_topic_cache: dict[tuple, tuple[float, dict]] = {}


@app.get("/api/subjects/{key}/topics/{code}/resources")
def topic_resources(key: str, code: str, user: User = Depends(current_user)):
    check_key(key)
    with db.ro() as con:
        row = my_subject(con, user.username, key)
        topic = next((t for t in catalog.topics_for(key, row["level"]) if t["code"] == code), None)
        if not topic:
            raise HTTPException(404, "Unknown topic")
        ck = (key, row["level"], code, row["textbook_id"])
        hit = _topic_cache.get(ck)
        if hit and time.time() - hit[0] < 1800:
            return hit[1]
        data = search.topic_resources(con, key, row["level"], topic, row["textbook_id"])
    if len(_topic_cache) > 3000:
        _topic_cache.clear()
    if any(data.values()):
        _topic_cache[ck] = (time.time(), data)
    return data


@app.get("/api/subjects/{key}/papers")
def subject_papers(key: str, user: User = Depends(current_user)):
    check_key(key)
    with db.ro() as con:
        row = my_subject(con, user.username, key)
        return {"papers": search.past_papers(con, key, row["level"], user.username)}


class AttemptIn(BaseModel):
    score: float | None = Field(default=None, ge=0, le=1000)
    max_score: float | None = Field(default=None, gt=0, le=1000)
    note: str | None = Field(default=None, max_length=300)
    date: str | None = None


@app.post("/api/papers/{rid}/attempts")
def add_attempt(rid: int, body: AttemptIn, user: User = Depends(current_user)):
    if body.score is not None and body.max_score is not None and body.score > body.max_score:
        raise HTTPException(422, "Score cannot be higher than the maximum")
    d = check_date(body.date) if body.date else planner.today_local().isoformat()
    with db.tx() as con:
        if not con.execute("SELECT 1 FROM resources WHERE id=?", (rid,)).fetchone():
            raise HTTPException(404, "Unknown paper")
        cur = con.execute("INSERT INTO paper_attempts(username, resource_id, date, score, max_score, note) VALUES(?,?,?,?,?,?)", (user.username, rid, d, body.score, body.max_score, _clean_text(body.note, 300)))
        return {"id": cur.lastrowid}


@app.delete("/api/attempts/{aid}")
def delete_attempt(aid: int, user: User = Depends(current_user)):
    with db.tx() as con:
        n = con.execute("DELETE FROM paper_attempts WHERE id=? AND username=?", (aid, user.username)).rowcount
    if not n:
        raise HTTPException(404, "Not found")
    return {"ok": True}


# ───────────────────────── plan ─────────────────────────
def _created(before: dict, after: dict) -> list[dict]:
    """Issues that a change introduced or made worse."""
    old = {i["ident"]: i for i in before["issues"] + before["dismissed"]}
    out = []
    for i in after["issues"]:
        prev = old.get(i["ident"])
        if prev is None or i.get("amount", 0) > prev.get("amount", 0):
            out.append(i)
    return out


@app.get("/api/dashboard")
def dashboard(user: User = Depends(current_user)):
    today = planner.today_local()
    with db.tx() as con:
        st = planner.stats(con, user.username, today)
        tasks = db.rows(con, "SELECT * FROM tasks WHERE username=? AND date=? ORDER BY status='todo' DESC, sort, id", (user.username, today.isoformat()))
        overdue = db.rows(con, "SELECT * FROM tasks WHERE username=? AND date<? AND status='todo' ORDER BY date DESC, sort LIMIT 30", (user.username, today.isoformat()))
        upcoming = db.rows(con, "SELECT date, SUM(minutes) m, COUNT(*) n FROM tasks WHERE username=? AND date>? AND date<=? AND status='todo' GROUP BY date ORDER BY date",
                           (user.username, today.isoformat(), (today + timedelta(days=7)).isoformat()))
        issues = planner.evaluate(con, user.username, today)
        last_grade = con.execute("SELECT MAX(date) FROM grade_log WHERE username=?", (user.username,)).fetchone()[0]
        profile = planner.load_profile(con, user.username)
        cap = planner.capacity_map(con, user.username, profile, today, today + timedelta(days=7))
        subs = []
        for s in profile["subjects"]:
            c = catalog.get_subject(s["subject"]) or {}
            p = st["subjects"].get(s["subject"], {"planned": 0, "done": 0, "todo_tasks": 0, "done_tasks": 0})
            subs.append({"key": s["subject"], "short": c.get("short", s["subject"]), "name": c.get("name", s["subject"]), "level": s["level"], "current": s["current_grade"], "target": s["target_grade"], **p})
    checkin = bool(last_grade) and (today - (planner.parse_date(last_grade) or today)).days >= 21
    return {"stats": st, "today": [task_public(t) for t in tasks], "overdue": [task_public(t) for t in overdue],
            "upcoming": [{"date": u["date"], "minutes": u["m"], "tasks": u["n"], "capacity": cap.get(planner.parse_date(u["date"]), 0)} for u in upcoming],
            "capacity_today": cap.get(today, 0), "issues": issues["issues"][:6], "issue_count": len(issues["issues"]), "subjects": subs,
            "tip": advice.tip_of_the_day(today.toordinal()), "checkin_due": checkin}


@app.get("/api/plan")
def get_plan(start: str | None = None, days: int = Query(default=7, ge=1, le=120), user: User = Depends(current_user)):
    today = planner.today_local()
    d0 = planner.parse_date(check_date(start)) if start else today - timedelta(days=today.weekday())
    d1 = d0 + timedelta(days=days - 1)
    with db.tx() as con:
        profile = planner.load_profile(con, user.username)
        tasks = db.rows(con, "SELECT * FROM tasks WHERE username=? AND date>=? AND date<=? ORDER BY date, sort, id", (user.username, d0.isoformat(), d1.isoformat()))
        cap = planner.capacity_map(con, user.username, profile, d0, d1)
        overrides = {r["date"]: r for r in db.rows(con, "SELECT date, minutes, note FROM day_overrides WHERE username=? AND date>=? AND date<=?", (user.username, d0.isoformat(), d1.isoformat()))}
        issues = planner.evaluate(con, user.username, today)
        meta = db.get_meta(con, f"plan:{user.username}", {})
        first_last = con.execute("SELECT MIN(date), MAX(date), COUNT(*) FROM tasks WHERE username=? AND status='todo'", (user.username,)).fetchone()
        subject_ends = {s["subject"]: (planner.subject_end(profile, s) + timedelta(days=1)).isoformat() for s in profile["subjects"]}
    day_list = []
    d = d0
    while d <= d1:
        ds = d.isoformat()
        day_list.append({"date": ds, "capacity": cap[d], "override": ds in overrides, "note": (overrides.get(ds) or {}).get("note"), "default": profile["week"][d.weekday()]})
        d += timedelta(days=1)
    return {"start": d0.isoformat(), "days": day_list, "tasks": [task_public(t) for t in tasks], "issues": issues["issues"], "dismissed": issues["dismissed"], "today": today.isoformat(),
            "exam_start": profile["exam_start"].isoformat(), "exam_dates": subject_ends, "summary": meta, "span": {"first": first_last[0], "last": first_last[1], "todo": first_last[2]}}


class ReplanIn(BaseModel):
    keep_pinned: bool = True


@app.post("/api/plan/replan")
def replan(body: ReplanIn, user: User = Depends(current_user)):
    auth.rate_limit(user.username, "replan", 30, 3600)
    with db.tx() as con:
        summary = planner.generate(con, user.username, keep_pinned=body.keep_pinned)
        issues = planner.evaluate(con, user.username)
    return {"summary": summary, "issues": issues["issues"], "dismissed": issues["dismissed"]}


class TaskIn(BaseModel):
    date: str
    title: str = Field(min_length=1, max_length=200)
    minutes: int = Field(ge=5, le=600)
    subject: str | None = Field(default=None, max_length=80)
    detail: str | None = Field(default=None, max_length=600)
    kind: Literal["custom", "learn", "practice", "review", "paper", "mixed", "coursework"] = "custom"
    resource_id: int | None = None


@app.post("/api/tasks")
def add_task(body: TaskIn, user: User = Depends(current_user)):
    check_date(body.date)
    with db.tx() as con:
        if body.subject:
            check_key(body.subject)
            my_subject(con, user.username, body.subject)
        if con.execute("SELECT COUNT(*) FROM tasks WHERE username=?", (user.username,)).fetchone()[0] > 20000:
            raise HTTPException(422, "Task limit reached")
        meta: dict = {}
        if body.resource_id is not None:
            r = db.one(con, "SELECT id, pair_id FROM resources WHERE id=?", (body.resource_id,))
            if r:
                meta = {"resources": [r["id"]], "markschemes": [r["pair_id"]] if r["pair_id"] else []}
        before = planner.evaluate(con, user.username)
        cur = con.execute("INSERT INTO tasks(username,subject,kind,title,detail,topic_code,date,minutes,status,pinned,origin,meta,sort,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (user.username, body.subject, body.kind, _clean_text(body.title, 200) or "Task", _clean_text(body.detail, 600), None, body.date, body.minutes, "todo", 1, "manual",
                           json.dumps(meta), planner.KIND_ORDER.get(body.kind, 8), now_iso()))
        after = planner.evaluate(con, user.username)
        task = db.one(con, "SELECT * FROM tasks WHERE id=?", (cur.lastrowid,))
    return {"task": task_public(task), "issues": after["issues"], "dismissed": after["dismissed"], "created": _created(before, after)}


class TaskPatch(BaseModel):
    date: str | None = None
    minutes: int | None = Field(default=None, ge=5, le=600)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    detail: str | None = Field(default=None, max_length=600)
    status: Literal["todo", "done", "skipped"] | None = None
    rating: Literal["hard", "ok", "easy"] | None = None
    pinned: bool | None = None


@app.patch("/api/tasks/{tid}")
def patch_task(tid: int, body: TaskPatch, user: User = Depends(current_user)):
    if body.date:
        check_date(body.date)
    with db.tx() as con:
        t = db.one(con, "SELECT * FROM tasks WHERE id=? AND username=?", (tid, user.username))
        if not t:
            raise HTTPException(404, "Task not found")
        before = planner.evaluate(con, user.username)
        sets, params = [], []
        if body.date and body.date != t["date"]:
            sets += ["date=?", "pinned=1"]
            params.append(body.date)
        if body.minutes and body.minutes != t["minutes"]:
            sets += ["minutes=?", "pinned=1"]
            params.append(body.minutes)
        if body.title is not None:
            sets.append("title=?")
            params.append(_clean_text(body.title, 200) or t["title"])
        if body.detail is not None:
            sets.append("detail=?")
            params.append(_clean_text(body.detail, 600))
        if body.pinned is not None and "pinned=1" not in sets:
            sets.append("pinned=?")
            params.append(int(body.pinned))
        extra_task = None
        if body.status and body.status != t["status"]:
            sets += ["status=?", "done_at=?"]
            params += [body.status, now_iso() if body.status == "done" else None]
            if body.status == "done" and t["topic_code"] and t["subject"] and body.rating in ("hard", "easy"):
                st = db.one(con, "SELECT confidence FROM topic_state WHERE username=? AND subject=? AND topic_code=?", (user.username, t["subject"], t["topic_code"]))
                conf = (st or {}).get("confidence") or 3
                conf = max(1, conf - 1) if body.rating == "hard" else min(5, conf + 1)
                con.execute("""INSERT INTO topic_state(username, subject, topic_code, confidence) VALUES(?,?,?,?)
                               ON CONFLICT(username, subject, topic_code) DO UPDATE SET confidence=excluded.confidence""", (user.username, t["subject"], t["topic_code"], conf))
                if body.rating == "hard":
                    when = (planner.today_local() + timedelta(days=2)).isoformat()
                    base = re.sub(r"^(Learn|Practise|Review): ", "", t["title"])
                    cur = con.execute("INSERT INTO tasks(username,subject,kind,title,detail,topic_code,date,minutes,status,pinned,origin,meta,sort,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                      (user.username, t["subject"], "review", f"Review: {base}", "Extra review because this felt hard. Closed-book retrieval first, then fix the gaps.", t["topic_code"], when, 20,
                                       "todo", 0, "auto", json.dumps({"phase": "review", "n": 9}), 0, now_iso()))
                    extra_task = cur.lastrowid
        if sets:
            con.execute(f"UPDATE tasks SET {','.join(dict.fromkeys(sets))} WHERE id=?", (*params, tid))
        after = planner.evaluate(con, user.username)
        t = db.one(con, "SELECT * FROM tasks WHERE id=?", (tid,))
        extra = db.one(con, "SELECT * FROM tasks WHERE id=?", (extra_task,)) if extra_task else None
    return {"task": task_public(t), "extra": task_public(extra) if extra else None, "issues": after["issues"], "dismissed": after["dismissed"], "created": _created(before, after)}


@app.delete("/api/tasks/{tid}")
def delete_task(tid: int, user: User = Depends(current_user)):
    with db.tx() as con:
        n = con.execute("DELETE FROM tasks WHERE id=? AND username=?", (tid, user.username)).rowcount
        if not n:
            raise HTTPException(404, "Task not found")
        after = planner.evaluate(con, user.username)
    return {"ok": True, "issues": after["issues"], "dismissed": after["dismissed"]}


class DayIn(BaseModel):
    minutes: int = Field(ge=0, le=720)
    note: str | None = Field(default=None, max_length=120)


@app.put("/api/days/{day}")
def put_day(day: str, body: DayIn, user: User = Depends(current_user)):
    check_date(day)
    with db.tx() as con:
        before = planner.evaluate(con, user.username)
        con.execute("INSERT INTO day_overrides(username, date, minutes, note) VALUES(?,?,?,?) ON CONFLICT(username, date) DO UPDATE SET minutes=excluded.minutes, note=excluded.note",
                    (user.username, day, body.minutes, _clean_text(body.note, 120)))
        after = planner.evaluate(con, user.username)
    return {"ok": True, "issues": after["issues"], "dismissed": after["dismissed"], "created": _created(before, after)}


@app.delete("/api/days/{day}")
def delete_day(day: str, user: User = Depends(current_user)):
    check_date(day)
    with db.tx() as con:
        before = planner.evaluate(con, user.username)
        con.execute("DELETE FROM day_overrides WHERE username=? AND date=?", (user.username, day))
        after = planner.evaluate(con, user.username)
    return {"ok": True, "issues": after["issues"], "dismissed": after["dismissed"], "created": _created(before, after)}


class IssueKey(BaseModel):
    key: str = Field(min_length=1, max_length=200)


@app.post("/api/issues/dismiss")
def dismiss_issue(body: IssueKey, user: User = Depends(current_user)):
    with db.tx() as con:
        con.execute("INSERT OR IGNORE INTO dismissed_issues(username, key, dismissed_at) VALUES(?,?,?)", (user.username, body.key, now_iso()))
        after = planner.evaluate(con, user.username)
    return {"issues": after["issues"], "dismissed": after["dismissed"]}


@app.post("/api/issues/restore")
def restore_issue(body: IssueKey, user: User = Depends(current_user)):
    with db.tx() as con:
        con.execute("DELETE FROM dismissed_issues WHERE username=? AND key=?", (user.username, body.key))
        after = planner.evaluate(con, user.username)
    return {"issues": after["issues"], "dismissed": after["dismissed"]}


# ───────────────────────── library ─────────────────────────
@app.get("/api/search")
def api_search(q: str = Query(default="", max_length=200), subject: str | None = Query(default=None, max_length=80), collection: str | None = Query(default=None, max_length=30),
               kind: str | None = Query(default=None, max_length=30), level: str | None = Query(default=None, max_length=4), year_from: int | None = Query(default=None, ge=1990, le=2100),
               year_to: int | None = Query(default=None, ge=1990, le=2100), all_languages: bool = False, current_only: bool = False, offset: int = Query(default=0, ge=0, le=600),
               user: User = Depends(current_user)):
    tags = None
    if subject:
        tags = catalog.subject_tags(check_key(subject)) if subject not in ("tok", "ee", "cas") else [subject]
    cols = [collection] if collection and re.fullmatch(r"[a-z_]{2,30}", collection) else None
    kinds = [kind] if kind and re.fullmatch(r"[a-z_]{2,30}", kind) else None
    with db.ro() as con:
        out = search.search(con, q, subject_tags=tags, collections=cols, kinds=kinds, level=level if level in ("HL", "SL") else None, year_from=year_from, year_to=year_to,
                            english_only=not all_languages, syllabus="current" if current_only else None, limit=30, offset=offset)
        ids = [r["id"] for r in out["results"]]
        if ids:
            marks = {r["resource_id"]: r["status"] for r in db.rows(con, f"SELECT resource_id, status FROM resource_marks WHERE username=? AND resource_id IN ({','.join('?' * len(ids))})", (user.username, *ids))}
            for r in out["results"]:
                r["mark"] = marks.get(r["id"])
    for r in out["results"]:
        r["subject_name"] = subject_label(r["subject"]) or {"tok": "TOK", "ee": "Extended Essay"}.get(r["subject"] or "", "")
    return out


@app.get("/api/library/overview")
def library_overview(user: User = Depends(current_user)):
    with db.ro() as con:
        counts = db.rows(con, "SELECT collection, COUNT(*) n FROM resources GROUP BY collection ORDER BY n DESC")
        general = search.general_docs(con)
        core = {}
        for key in ("tok", "ee"):
            core[key] = [search.public(r) for r in db.rows(con, f"SELECT {search.RES_COLS} FROM resources r WHERE r.subject=? AND (r.lang IS NULL OR r.lang='en') ORDER BY r.collection, r.kind, r.title LIMIT 400", (key,))]
        saved = [search.public(r) for r in db.rows(con, f"""SELECT {search.RES_COLS}, m.status AS mark FROM resource_marks m JOIN resources r ON r.id=m.resource_id
                                                           WHERE m.username=? ORDER BY m.updated_at DESC LIMIT 100""", (user.username,))]
    return {"counts": counts, "general": general, "core": core, "saved": saved, "index": indexer.status()}


@app.get("/api/resources")
def resources_by_id(ids: str = Query(max_length=400), user: User = Depends(current_user)):
    try:
        id_list = [int(x) for x in ids.split(",") if x.strip()][:40]
    except ValueError:
        raise HTTPException(422, "Bad ids")
    if not id_list:
        return {"resources": []}
    with db.ro() as con:
        rows = db.rows(con, f"SELECT {search.RES_COLS} FROM resources r WHERE r.id IN ({','.join('?' * len(id_list))})", id_list)
    return {"resources": [search.public(r) for r in rows]}


class MarkIn(BaseModel):
    status: Literal["saved", "done", "none"]


@app.post("/api/resources/{rid}/mark")
def mark_resource(rid: int, body: MarkIn, user: User = Depends(current_user)):
    with db.tx() as con:
        if not con.execute("SELECT 1 FROM resources WHERE id=?", (rid,)).fetchone():
            raise HTTPException(404, "Unknown resource")
        if body.status == "none":
            con.execute("DELETE FROM resource_marks WHERE username=? AND resource_id=?", (user.username, rid))
        else:
            con.execute("INSERT INTO resource_marks(username, resource_id, status, updated_at) VALUES(?,?,?,?) ON CONFLICT(username, resource_id) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at",
                        (user.username, rid, body.status, now_iso()))
    return {"ok": True}


@app.get("/api/files/{rid}/open")
def open_file(rid: int, user: User = Depends(current_user)):
    with db.ro() as con:
        r = db.one(con, "SELECT id, path, ext, url_kind, title FROM resources WHERE id=?", (rid,))
    if not r:
        raise HTTPException(404, "File not found")
    ext_url = search.external_url(r)
    if ext_url:
        return RedirectResponse(ext_url, status_code=302)
    root = config.LIBRARY_ROOT
    full = (root / r["path"]).resolve()
    # The index only ever holds paths found under the library root; verify again before touching the disk.
    if root not in full.parents or full.parts[len(root.parts)] in config.EXCLUDE_TOP or not full.is_file():
        raise HTTPException(404, "File not found")
    ext = (r["ext"] or "").lower()
    name = re.sub(r'[\r\n"\\/]', " ", full.name)[:150]
    headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=3600", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; media-src 'self'; object-src 'self'; frame-ancestors 'self'"}
    if ext in INLINE_TYPES:
        return FileResponse(full, media_type=INLINE_TYPES[ext], filename=name, content_disposition_type="inline", headers=headers)
    # Anything that a browser might render or execute is sent as a download only.
    headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return FileResponse(full, media_type="application/octet-stream", filename=name, content_disposition_type="attachment", headers=headers)


@app.get("/api/techniques")
def techniques(user: User = Depends(current_user)):
    return {"techniques": TECHNIQUES, "bands": {str(k): {"title": v["title"], "focus": v["focus"], "actions": v["actions"], "mix": v["mix"]} for k, v in GRADE_BANDS.items()}, "families": FAMILY_TIPS}


# ───────────────────────── coach ─────────────────────────
class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


@app.get("/api/coach/chats")
def list_chats(user: User = Depends(current_user)):
    with db.ro() as con:
        return {"chats": db.rows(con, "SELECT id, title, updated_at FROM chats WHERE username=? ORDER BY updated_at DESC LIMIT 50", (user.username,)), "llm": llm.info()}


@app.post("/api/coach/chats")
def new_chat(user: User = Depends(current_user)):
    with db.tx() as con:
        if con.execute("SELECT COUNT(*) FROM chats WHERE username=?", (user.username,)).fetchone()[0] >= 200:
            old = con.execute("SELECT id FROM chats WHERE username=? ORDER BY updated_at LIMIT 1", (user.username,)).fetchone()
            con.execute("DELETE FROM chats WHERE id=?", (old[0],))
        cur = con.execute("INSERT INTO chats(username, title, created_at, updated_at) VALUES(?,?,?,?)", (user.username, "New conversation", now_iso(), now_iso()))
        return {"id": cur.lastrowid, "title": "New conversation"}


def _chat(con, username: str, cid: int) -> dict:
    c = db.one(con, "SELECT * FROM chats WHERE id=? AND username=?", (cid, username))
    if not c:
        raise HTTPException(404, "Conversation not found")
    return c


@app.get("/api/coach/chats/{cid}")
def get_chat(cid: int, user: User = Depends(current_user)):
    with db.ro() as con:
        c = _chat(con, user.username, cid)
        msgs = db.rows(con, "SELECT id, role, content, sources, created_at FROM chat_messages WHERE chat_id=? ORDER BY id", (cid,))
    for m in msgs:
        m["sources"] = json.loads(m["sources"] or "[]")
    return {"id": c["id"], "title": c["title"], "messages": msgs}


@app.delete("/api/coach/chats/{cid}")
def delete_chat(cid: int, user: User = Depends(current_user)):
    with db.tx() as con:
        _chat(con, user.username, cid)
        con.execute("DELETE FROM chats WHERE id=?", (cid,))
    return {"ok": True}


_coach_active: dict[str, float] = {}
_coach_lock = threading.Lock()
COACH_MAX_WAITING = 6


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.post("/api/coach/chats/{cid}/messages")
def post_message(cid: int, body: ChatIn, user: User = Depends(current_user)):
    question = _clean_text(body.message, 2000) or ""
    if not question:
        raise HTTPException(422, "Empty message")
    with db.ro() as con:
        _chat(con, user.username, cid)
    with _coach_lock:
        now = time.time()
        if now - _coach_active.get(user.username, 0) < 900:
            raise HTTPException(429, "Your previous question is still being answered. Wait for it to finish.")
        if llm.info()["waiting"] >= COACH_MAX_WAITING and not coach.is_crisis(question):
            raise HTTPException(429, "The coach is very busy right now. Please try again in a few minutes.")
        _coach_active[user.username] = now
    try:
        auth.rate_limit(user.username, "coach", config.RATE_COACH_PER_HOUR, 3600)
    except HTTPException:
        _coach_active.pop(user.username, None)
        raise
    try:
        with db.tx() as con:
            c = _chat(con, user.username, cid)
            history = db.rows(con, "SELECT role, content FROM chat_messages WHERE chat_id=? ORDER BY id DESC LIMIT 6", (cid,))[::-1]
            messages, sources = coach.build(con, user.username, question, history)
            con.execute("INSERT INTO chat_messages(chat_id, role, content, sources, created_at) VALUES(?,?,?,?,?)", (cid, "user", question, "[]", now_iso()))
            if c["title"] == "New conversation":
                con.execute("UPDATE chats SET title=? WHERE id=?", (question[:60], cid))
            con.execute("UPDATE chats SET updated_at=? WHERE id=?", (now_iso(), cid))
    except Exception:
        _coach_active.pop(user.username, None)
        raise

    def gen():
        parts: list[str] = []
        try:
            if coach.is_crisis(question):
                parts.append(coach.CRISIS_REPLY)
                yield _sse("sources", {"sources": []})
                yield _sse("token", {"text": coach.CRISIS_REPLY})
                yield _sse("done", {"fixed": True})
                return
            yield _sse("sources", {"sources": sources})
            if not llm.available():
                text = coach.fallback_answer(question, sources)
                parts.append(text)
                yield _sse("token", {"text": text})
                yield _sse("done", {"fallback": True})
                return
            for ev in llm.stream(messages, max_tokens=640, temperature=0.4):
                if "wait" in ev:
                    yield _sse("wait", {"ahead": max(0, ev["wait"] - 1)})
                elif "text" in ev:
                    parts.append(ev["text"])
                    yield _sse("token", {"text": ev["text"]})
                elif "done" in ev:
                    if ev["done"].get("finish") == "length":
                        tail = "\n\n(I stopped here to keep this short. Say \"continue\" if you want the rest.)"
                        parts.append(tail)
                        yield _sse("token", {"text": tail})
                    yield _sse("done", ev["done"])
        except llm.Busy:
            yield _sse("error", {"detail": "The AI is busy with other requests. Please try again in a few minutes."})
        except GeneratorExit:
            raise
        except Exception:
            log.exception("coach stream failed")
            if not parts:
                text = coach.fallback_answer(question, sources)
                parts.append(text)
                yield _sse("token", {"text": text})
            yield _sse("done", {"fallback": True})
        finally:
            _coach_active.pop(user.username, None)
            text = "".join(parts).strip()
            if text:
                shown = [] if coach.is_crisis(question) else sources
                with db.tx() as con2:
                    con2.execute("INSERT INTO chat_messages(chat_id, role, content, sources, created_at) VALUES(?,?,?,?,?)", (cid, "assistant", text[:12000], json.dumps(shown), now_iso()))

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


# ───────────────────────── feedback writer ─────────────────────────
@app.get("/api/feedback/rubrics")
def rubrics(user: User = Depends(current_user)):
    return {"rubrics": [{"key": k, "name": v["name"], "words": v["words"], "total": v["total"], "applies": v["applies"],
                         "criteria": [{"code": c[0], "name": c[1], "marks": c[2], "descriptor": c[3]} for c in v["criteria"]]} for k, v in RUBRICS.items()],
            "llm": llm.info(), "max_words": config.MAX_FEEDBACK_WORDS, "per_day": config.RATE_FEEDBACK_PER_DAY}


@app.post("/api/feedback/extract")
async def extract_upload(file: UploadFile = File(...), user: User = Depends(current_user)):
    auth.rate_limit(user.username, "extract", 30, 3600)
    name = (file.filename or "upload").lower()
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    if ext not in ("pdf", "docx", "txt"):
        raise HTTPException(415, "Upload a PDF, DOCX or TXT file")
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File is larger than {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    if (ext == "pdf" and not data.startswith(b"%PDF")) or (ext == "docx" and not data.startswith(b"PK")):
        raise HTTPException(415, "The file does not look like a valid " + ext.upper())
    fd, tmp = tempfile.mkstemp(suffix="." + ext, prefix="ibgod-upload-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        from starlette.concurrency import run_in_threadpool
        text = await run_in_threadpool(indexer.extract_document, Path(tmp), ext)
    except Exception:
        raise HTTPException(422, "Could not read text from this file. Try pasting the text instead.")
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    if len(text.strip()) < 50:
        raise HTTPException(422, "No text found. If this is a scanned document, paste the text instead.")
    return {"text": text[:200000], "words": feedback.word_count(text)}


class FeedbackIn(BaseModel):
    rubric: str = Field(max_length=40)
    title: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=200, max_length=200000)
    subject: str | None = Field(default=None, max_length=80)


def _job_public(j: dict, full: bool = False) -> dict:
    out = {"id": j["id"], "rubric": j["rubric"], "rubric_name": RUBRICS.get(j["rubric"], {}).get("name", j["rubric"]), "title": j["title"], "words": j["words"], "status": j["status"],
           "progress": j["progress"], "created_at": j["created_at"], "finished_at": j["finished_at"], "subject": j["subject"]}
    if full:
        out["result"] = json.loads(j["result"]) if j["result"] else None
        out["text"] = j["body"]
    return out


@app.post("/api/feedback/jobs")
def create_feedback(body: FeedbackIn, user: User = Depends(current_user)):
    if body.rubric not in RUBRICS:
        raise HTTPException(422, "Unknown rubric")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", body.text).strip()
    if feedback.word_count(text) < 80:
        raise HTTPException(422, "Paste at least a few paragraphs of your work")
    with db.ro() as con:
        active = con.execute("SELECT COUNT(*) FROM feedback_jobs WHERE username=? AND status IN ('queued','running')", (user.username,)).fetchone()[0]
    if active >= 2:
        raise HTTPException(429, "You already have feedback in progress. Wait for it to finish first.")
    auth.rate_limit(user.username, "feedback", config.RATE_FEEDBACK_PER_DAY, 86400)
    with db.tx() as con:
        con.execute("DELETE FROM feedback_jobs WHERE username=? AND status IN ('done','error') AND id NOT IN (SELECT id FROM feedback_jobs WHERE username=? ORDER BY id DESC LIMIT 40)",
                    (user.username, user.username))
    jid = feedback.create_job(user.username, body.rubric, body.subject if body.subject and SUBJECT_KEY.match(body.subject) else None, _clean_text(body.title, 160) or "Untitled", text)
    return {"id": jid}


@app.get("/api/feedback/jobs")
def list_feedback(user: User = Depends(current_user)):
    with db.ro() as con:
        jobs = db.rows(con, "SELECT * FROM feedback_jobs WHERE username=? ORDER BY id DESC LIMIT 40", (user.username,))
        ahead = con.execute("SELECT COUNT(*) FROM feedback_jobs WHERE status IN ('queued','running')").fetchone()[0]
    return {"jobs": [_job_public(j) for j in jobs], "queue": ahead, "llm": llm.info()}


@app.get("/api/feedback/jobs/{jid}")
def get_feedback(jid: int, user: User = Depends(current_user)):
    with db.ro() as con:
        j = db.one(con, "SELECT * FROM feedback_jobs WHERE id=? AND username=?", (jid, user.username))
        if not j:
            raise HTTPException(404, "Not found")
        ahead = con.execute("SELECT COUNT(*) FROM feedback_jobs WHERE status IN ('queued','running') AND id<?", (jid,)).fetchone()[0]
    out = _job_public(j, full=True)
    out["ahead"] = ahead
    return out


@app.delete("/api/feedback/jobs/{jid}")
def delete_feedback(jid: int, user: User = Depends(current_user)):
    with db.tx() as con:
        j = db.one(con, "SELECT status FROM feedback_jobs WHERE id=? AND username=?", (jid, user.username))
        if not j:
            raise HTTPException(404, "Not found")
        if j["status"] == "running":
            raise HTTPException(409, "This feedback is being written right now. Delete it when it has finished.")
        con.execute("DELETE FROM feedback_jobs WHERE id=?", (jid,))
    return {"ok": True}


# ───────────────────────── account data ─────────────────────────
@app.get("/api/export")
def export(user: User = Depends(current_user)):
    out: dict = {"exported_at": now_iso(), "username": user.username}
    with db.ro() as con:
        out["profile"] = db.one(con, "SELECT username, display_name, email, created_at, settings FROM users WHERE username=?", (user.username,))
        for table in ("user_subjects", "topic_state", "tasks", "day_overrides", "dismissed_issues", "grade_log", "paper_attempts", "resource_marks", "chats", "feedback_jobs"):
            out[table] = db.rows(con, f"SELECT * FROM {table} WHERE username=?", (user.username,))
        out["chat_messages"] = db.rows(con, "SELECT m.* FROM chat_messages m JOIN chats c ON c.id=m.chat_id WHERE c.username=?", (user.username,))
    return JSONResponse(out, headers={"Content-Disposition": f'attachment; filename="ibgod-{user.username}.json"'})


class ConfirmIn(BaseModel):
    confirm: Literal["DELETE"]


@app.post("/api/account/delete")
def delete_account(body: ConfirmIn, user: User = Depends(current_user)):
    with db.tx() as con:
        con.execute("DELETE FROM users WHERE username=?", (user.username,))
        con.execute("DELETE FROM usage_log WHERE username=?", (user.username,))
        con.execute("DELETE FROM meta WHERE key=?", (f"plan:{user.username}",))
    auth.forget(user.username)
    return {"ok": True}


# ───────────────────────── admin ─────────────────────────
def admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Admins only")
    return user


@app.get("/api/admin/status")
def admin_status(user: User = Depends(admin)):
    with db.ro() as con:
        by_coll = db.rows(con, "SELECT collection, COUNT(*) files, SUM(text_status='done') indexed, SUM(text_status='pending') pending, SUM(text_status='error') errors FROM resources GROUP BY collection ORDER BY files DESC")
        users = db.rows(con, "SELECT username, display_name, onboarded, last_seen, (SELECT COUNT(*) FROM user_subjects s WHERE s.username=u.username) subjects FROM users u ORDER BY last_seen DESC LIMIT 200")
        last = db.get_meta(con, "last_scan", None)
        size = os.path.getsize(config.DB_PATH) if config.DB_PATH.exists() else 0
        jobs = con.execute("SELECT COUNT(*) FROM feedback_jobs WHERE status IN ('queued','running')").fetchone()[0]
    return {"index": indexer.status(), "collections": by_coll, "users": users, "last_scan": last, "db_bytes": size, "llm": llm.info(), "feedback_queue": jobs,
            "excluded": sorted(config.EXCLUDE_TOP)}


@app.post("/api/admin/rescan")
def admin_rescan(user: User = Depends(admin)):
    indexer.start()
    indexer.request_rescan()
    _catalog_cache.update(at=0.0, data=None)
    _topic_cache.clear()
    return {"ok": True}


# ───────────────────────── web app ─────────────────────────
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("text/javascript", ".js")


@app.get("/")
def index():
    return FileResponse(config.WEB_DIR / "index.html", media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache"})


class CachedStatic(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers.setdefault("Cache-Control", "no-cache")
        return response


if config.WEB_DIR.is_dir():
    app.mount("/", CachedStatic(directory=str(config.WEB_DIR), follow_symlink=False), name="web")
