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
EXCLUDE_TOP = set(_list("IBGOD_EXCLUDE_TOP", "lost+found"))

# Folders that the existing `view` site serves as rendered HTML (scripts must never run on our origin).
VIEW_BASE = os.environ.get("IBGOD_VIEW_BASE", "").rstrip("/")
VIEW_FOLDERS = _list("IBGOD_VIEW_FOLDERS", "IB QUESTIONBANKS,ThinkIB,StudyIB,IB PAST PAPERS - YEAR,IB OFFICIAL EE EXEMPLARS")
DOCS_BASE = os.environ.get("IBGOD_DOCS_BASE", "").rstrip("/")

# Identity: only the reverse proxy may set Remote-* headers. We accept them solely from its address.
TRUSTED_PROXY_HOSTS = _list("IBGOD_TRUSTED_PROXY_HOSTS", "caddy")
ADMIN_GROUPS = set(_list("IBGOD_ADMIN_GROUPS", ""))
ADMIN_USERS = set(_list("IBGOD_ADMIN_USERS", "admin"))
LOGOUT_URL = os.environ.get("IBGOD_LOGOUT_URL", "/logout")
PUBLIC_HOSTS = set(_list("IBGOD_PUBLIC_HOSTS", ""))
# Development only: a fixed user when no proxy is present. Never set in the deployed container.
DEV_USER = os.environ.get("IBGOD_DEV_USER", "")


INDEX_WORKERS = int(os.environ.get("IBGOD_INDEX_WORKERS", "2"))
AUTO_INDEX = os.environ.get("IBGOD_AUTO_INDEX", "1") == "1"
BACKGROUND_JOBS = os.environ.get("IBGOD_BACKGROUND_JOBS", "1") == "1"  # off only for a second test instance sharing the database


# FileBrowser's own database (mounted read-only). Its users, groups and access rules decide what each person can see here.
FB_DB = os.environ.get("IBGOD_FB_DB", "/filebrowser/database.sqlite")
FB_SOURCE = os.environ.get("IBGOD_FB_SOURCE", "/srv/docs")  # FileBrowser's path for the same folder that is mounted here at /library
# Mirrors FileBrowser's config.yaml for people who have not opened FileBrowser yet (FileBrowser creates their account on first visit).
FB_DEFAULT_SCOPE = os.environ.get("IBGOD_FB_DEFAULT_SCOPE", "/")
FB_DEFAULT_VIEW = os.environ.get("IBGOD_FB_DEFAULT_VIEW", "1") == "1"
FB_DENY_BY_DEFAULT = os.environ.get("IBGOD_FB_DENY_BY_DEFAULT", "0") == "1"
# Services shown on the Apps page: JSON list of {name, url, description, icon, groups}. Empty groups = every signed-in user.
APPS_FILE = os.environ.get("IBGOD_APPS_FILE", str(Path(__file__).resolve().parent / "apps.json"))
