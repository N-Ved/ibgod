"""Runtime configuration, all from environment variables with safe defaults."""
from __future__ import annotations

import os
from pathlib import Path


def _list(name: str, default: str) -> list[str]:
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]


LIBRARY_ROOT = Path(os.environ.get("IBGOD_LIBRARY_ROOT", "/library")).resolve()
DATA_DIR = Path(os.environ.get("IBGOD_DATA_DIR", "/data")).resolve()
DB_PATH = DATA_DIR / "ibgod.db"
WEB_DIR = Path(os.environ.get("IBGOD_WEB_DIR", str(Path(__file__).resolve().parent.parent / "web"))).resolve()

# Top-level folders of the library that are never indexed or served.
EXCLUDE_TOP = set(_list("IBGOD_EXCLUDE_TOP", "lost+found,Shaffy"))

# Folders that the existing `view` site serves as rendered HTML (scripts must never run on our origin).
VIEW_BASE = os.environ.get("IBGOD_VIEW_BASE", "https://view.n-ved.com").rstrip("/")
VIEW_FOLDERS = _list("IBGOD_VIEW_FOLDERS", "IB QUESTIONBANKS,ThinkIB,StudyIB,IB PAST PAPERS - YEAR,IB OFFICIAL EE EXEMPLARS")
DOCS_BASE = os.environ.get("IBGOD_DOCS_BASE", "https://docs.n-ved.com/files/docs").rstrip("/")

# Identity: only the reverse proxy may set Remote-* headers. We accept them solely from its address.
TRUSTED_PROXY_HOSTS = _list("IBGOD_TRUSTED_PROXY_HOSTS", "caddy")
ADMIN_GROUPS = set(_list("IBGOD_ADMIN_GROUPS", "lldap_admin"))
ADMIN_USERS = set(_list("IBGOD_ADMIN_USERS", "admin"))
LOGOUT_URL = os.environ.get("IBGOD_LOGOUT_URL", "https://auth.n-ved.com/logout")
PUBLIC_HOSTS = set(_list("IBGOD_PUBLIC_HOSTS", "ibgod.n-ved.com"))
# Development only: a fixed user when no proxy is present. Never set in the deployed container.
DEV_USER = os.environ.get("IBGOD_DEV_USER", "")

LLM_URL = os.environ.get("IBGOD_LLM_URL", "http://llm:8080").rstrip("/")
LLM_CTX = int(os.environ.get("IBGOD_LLM_CTX", "12288"))
LLM_ENABLED = os.environ.get("IBGOD_LLM_ENABLED", "1") == "1"

INDEX_WORKERS = int(os.environ.get("IBGOD_INDEX_WORKERS", "2"))
AUTO_INDEX = os.environ.get("IBGOD_AUTO_INDEX", "1") == "1"
FEEDBACK_WORKER = os.environ.get("IBGOD_FEEDBACK_WORKER", "1") == "1"  # off only for a second test instance sharing the database
MAX_UPLOAD_BYTES = int(os.environ.get("IBGOD_MAX_UPLOAD_MB", "20")) * 1024 * 1024
MAX_FEEDBACK_WORDS = int(os.environ.get("IBGOD_MAX_FEEDBACK_WORDS", "6500"))

# Per-user hourly limits for the expensive endpoints.
RATE_COACH_PER_HOUR = int(os.environ.get("IBGOD_RATE_COACH", "40"))
RATE_FEEDBACK_PER_DAY = int(os.environ.get("IBGOD_RATE_FEEDBACK", "8"))
