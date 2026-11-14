"""SQLite storage. One file, WAL mode, a fresh connection per unit of work."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Iterator

from . import config

SCHEMA_VERSION = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);

-- ── library index ──
CREATE TABLE IF NOT EXISTS resources(
  id INTEGER PRIMARY KEY,
  path TEXT UNIQUE NOT NULL,
  size INTEGER NOT NULL DEFAULT 0,
  mtime REAL NOT NULL DEFAULT 0,
  ext TEXT,
  collection TEXT,
  kind TEXT,
  subject TEXT,
  level TEXT,
  title TEXT,
  year INTEGER,
  session TEXT,
  paper TEXT,
  tz TEXT,
  lang TEXT,
  publisher TEXT,
  topic_code TEXT,
  unit_name TEXT,
  syllabus TEXT,
  note TEXT,
  pages INTEGER,
  text_status TEXT NOT NULL DEFAULT 'pending',
  url_kind TEXT NOT NULL DEFAULT 'file',
  pair_id INTEGER,
  pair_key TEXT,
  chunk_lo INTEGER,
  chunk_hi INTEGER,
  seen INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS res_subject ON resources(subject, collection, kind);
CREATE INDEX IF NOT EXISTS res_coll ON resources(collection, kind);
CREATE INDEX IF NOT EXISTS res_status ON resources(text_status);
CREATE INDEX IF NOT EXISTS res_pair ON resources(pair_key);
CREATE VIRTUAL TABLE IF NOT EXISTS res_fts USING fts5(title, words, tokenize='porter unicode61 remove_diacritics 2');
CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(text, stag, ctag, resource_id UNINDEXED, page UNINDEXED, tokenize='porter unicode61 remove_diacritics 2');

-- ── people ──
CREATE TABLE IF NOT EXISTS users(
  username TEXT PRIMARY KEY,
  display_name TEXT,
  email TEXT,
  created_at TEXT NOT NULL,
  last_seen TEXT,
  onboarded INTEGER NOT NULL DEFAULT 0,
  settings TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS user_subjects(
  id INTEGER PRIMARY KEY,
  username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
  subject TEXT NOT NULL,
  level TEXT NOT NULL,
  current_grade INTEGER NOT NULL,
  target_grade INTEGER NOT NULL,
  textbook_id INTEGER,
  textbook_other TEXT,
  exam_date TEXT,
  position INTEGER NOT NULL DEFAULT 0,
  UNIQUE(username, subject)
);
CREATE TABLE IF NOT EXISTS topic_state(
  username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
  subject TEXT NOT NULL,
  topic_code TEXT NOT NULL,
  enabled INTEGER,
  confidence INTEGER,
  custom_name TEXT,
  PRIMARY KEY(username, subject, topic_code)
);
CREATE TABLE IF NOT EXISTS tasks(
  id INTEGER PRIMARY KEY,
  username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
  subject TEXT,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  detail TEXT,
  topic_code TEXT,
  date TEXT NOT NULL,
  minutes INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'todo',
  pinned INTEGER NOT NULL DEFAULT 0,
  origin TEXT NOT NULL DEFAULT 'auto',
  meta TEXT NOT NULL DEFAULT '{}',
  sort INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  done_at TEXT
);
CREATE INDEX IF NOT EXISTS tasks_user_date ON tasks(username, date);
CREATE TABLE IF NOT EXISTS day_overrides(
  username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
  date TEXT NOT NULL,
  minutes INTEGER NOT NULL,
  note TEXT,
  PRIMARY KEY(username, date)
);
CREATE TABLE IF NOT EXISTS dismissed_issues(
  username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
  key TEXT NOT NULL,
  dismissed_at TEXT NOT NULL,
  PRIMARY KEY(username, key)
);
CREATE TABLE IF NOT EXISTS grade_log(
  id INTEGER PRIMARY KEY,
  username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
  subject TEXT NOT NULL,
  date TEXT NOT NULL,
  grade INTEGER NOT NULL,
  note TEXT
);
CREATE TABLE IF NOT EXISTS paper_attempts(
  id INTEGER PRIMARY KEY,
  username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
  resource_id INTEGER NOT NULL,
  date TEXT NOT NULL,
  score REAL,
  max_score REAL,
  note TEXT
);
CREATE INDEX IF NOT EXISTS attempts_user ON paper_attempts(username, resource_id);
CREATE TABLE IF NOT EXISTS resource_marks(
  username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
  resource_id INTEGER NOT NULL,
  status TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(username, resource_id)
);

-- ── coach & feedback ──
CREATE TABLE IF NOT EXISTS chats(
  id INTEGER PRIMARY KEY,
  username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
  title TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_messages(
  id INTEGER PRIMARY KEY,
  chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  sources TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback_jobs(
  id INTEGER PRIMARY KEY,
  username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
  rubric TEXT NOT NULL,
  subject TEXT,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  words INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  progress TEXT,
  result TEXT,
  created_at TEXT NOT NULL,
  finished_at TEXT
);
CREATE TABLE IF NOT EXISTS usage_log(
  id INTEGER PRIMARY KEY,
  username TEXT NOT NULL,
  action TEXT NOT NULL,
  ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS usage_user ON usage_log(username, action, ts);
"""

_init_lock = threading.Lock()
_initialised = False


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(config.DB_PATH, timeout=30, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=30000")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA temp_store=MEMORY")
    return con


def init() -> None:
    global _initialised
    with _init_lock:
        if _initialised:
            return
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        con = connect()
        try:
            con.execute("PRAGMA journal_mode=WAL")
            row = None
            try:
                row = con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            except sqlite3.OperationalError:
                pass
            if row and int(row[0]) != SCHEMA_VERSION:
                # The library index is derived data: rebuild it rather than migrate. User tables are kept.
                for t in ("chunks", "res_fts", "resources"):
                    con.execute(f"DROP TABLE IF EXISTS {t}")
            con.executescript(SCHEMA)
            con.execute("INSERT INTO meta(key,value) VALUES('schema_version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(SCHEMA_VERSION),))
        finally:
            con.close()
        _initialised = True


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    """A write transaction. Commits on success, rolls back on error."""
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        yield con
        con.execute("COMMIT")
    except BaseException:
        try:
            con.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        con.close()


@contextmanager
def ro() -> Iterator[sqlite3.Connection]:
    con = connect()
    try:
        yield con
    finally:
        con.close()


def rows(con: sqlite3.Connection, sql: str, params: tuple | list = ()) -> list[dict]:
    return [dict(r) for r in con.execute(sql, params).fetchall()]


def one(con: sqlite3.Connection, sql: str, params: tuple | list = ()) -> dict | None:
    r = con.execute(sql, params).fetchone()
    return dict(r) if r else None


def get_meta(con: sqlite3.Connection, key: str, default: Any = None) -> Any:
    r = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    if not r:
        return default
    try:
        return json.loads(r[0])
    except (ValueError, TypeError):
        return r[0]


def set_meta(con: sqlite3.Connection, key: str, value: Any) -> None:
    con.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))
