"""Daily snapshot of everything students created (plans, grades, chats, drafts) into /data/backups.

The 3 GB library index is left out on purpose: it rebuilds itself from the drive. Snapshots are small,
owner-readable only, and the newest 14 are kept. They live on the same disk as the database, so copying
the folder elsewhere now and then is still the owner's job.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from datetime import datetime

from . import config

log = logging.getLogger("ibgod.backup")
TABLES = ["users", "user_subjects", "topic_state", "tasks", "day_overrides", "dismissed_issues", "grade_log", "paper_attempts", "resource_marks", "works"]
KEEP = 14
_thread: threading.Thread | None = None


def run_once() -> str | None:
    folder = config.DATA_DIR / "backups"
    folder.mkdir(mode=0o700, exist_ok=True)
    target = folder / f"students-{datetime.now():%Y%m%d}.sqlite"
    tmp = folder / (target.name + ".tmp")
    if tmp.exists():
        tmp.unlink()
    src = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True, timeout=60)
    try:
        if not src.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            return None  # nothing to protect yet
        dst = sqlite3.connect(tmp)
        try:
            for table in TABLES:
                ddl = src.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
                if not ddl:
                    continue
                dst.execute(ddl[0])
                rows = src.execute(f"SELECT * FROM {table}").fetchall()
                if rows:
                    dst.executemany(f"INSERT INTO {table} VALUES({','.join('?' * len(rows[0]))})", rows)
            dst.commit()
        finally:
            dst.close()
    finally:
        src.close()
    os.chmod(tmp, 0o600)
    os.replace(tmp, target)
    for old in sorted(folder.glob("students-*.sqlite"))[:-KEEP]:
        old.unlink()
    return str(target)


def _loop() -> None:
    time.sleep(120)
    while True:
        try:
            done = run_once()
            if done:
                log.info("student data snapshot written: %s", done)
        except Exception:
            log.exception("student data snapshot failed")
        time.sleep(24 * 3600)


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _thread = threading.Thread(target=_loop, name="backup", daemon=True)
    _thread.start()
