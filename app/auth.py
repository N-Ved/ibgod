"""Identity and request-forgery protection.

The app has no login of its own. Authelia authenticates the browser, and Caddy passes the verified
identity in Remote-* headers. Those headers are honoured only when the TCP peer is the proxy itself,
so another container on the shared network cannot impersonate a user.
"""
from __future__ import annotations

import json
import re
import socket
import threading
import time
from datetime import datetime
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

from . import config, db

_USER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{0,63}$")
_proxy_lock = threading.Lock()
_proxy_ips: set[str] = set()
_proxy_checked = 0.0
_seen: dict[str, float] = {}


def _resolve_proxies(force: bool = False) -> set[str]:
    global _proxy_ips, _proxy_checked
    with _proxy_lock:
        if not force and time.time() - _proxy_checked < 60 and _proxy_ips:
            return _proxy_ips
        ips: set[str] = set()
        for host in config.TRUSTED_PROXY_HOSTS:
            try:
                for info in socket.getaddrinfo(host, None):
                    ips.add(info[4][0])
            except OSError:
                continue
        _proxy_ips, _proxy_checked = ips, time.time()
        return ips


def peer_is_proxy(request: Request) -> bool:
    peer = request.client.host if request.client else ""
    if not peer:
        return False
    if peer in _resolve_proxies():
        return True
    # The proxy container may have been recreated with a new address.
    return peer in _resolve_proxies(force=True)


class User:
    def __init__(self, username: str, name: str, email: str, groups: list[str]):
        self.username = username
        self.name = name
        self.email = email
        self.groups = groups
        self.is_admin = username in config.ADMIN_USERS or bool(set(groups) & config.ADMIN_GROUPS)


def _clean(s: str, n: int) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", "", s or "")[:n]


def current_user(request: Request) -> User:
    if config.DEV_USER:
        username, name, email, groups = config.DEV_USER, config.DEV_USER.title(), "", ["dev"]
    else:
        if not peer_is_proxy(request):
            raise HTTPException(status_code=403, detail="Direct access is not allowed")
        username = request.headers.get("remote-user", "")
        name = _clean(request.headers.get("remote-name", ""), 80)
        email = _clean(request.headers.get("remote-email", ""), 120)
        groups = [g for g in _clean(request.headers.get("remote-groups", ""), 400).split(",") if g]
    if not _USER_RE.match(username or ""):
        raise HTTPException(status_code=401, detail="Not signed in")
    username = username.lower()
    now = time.time()
    if now - _seen.get(username, 0) > 300:
        _seen[username] = now
        stamp = datetime.now().isoformat(timespec="seconds")
        with db.tx() as con:
            con.execute("""INSERT INTO users(username, display_name, email, created_at, last_seen) VALUES(?,?,?,?,?)
                           ON CONFLICT(username) DO UPDATE SET last_seen=excluded.last_seen, email=CASE WHEN excluded.email<>'' THEN excluded.email ELSE users.email END""",
                        (username, name or username, email, stamp, stamp))
    return User(username, name or username, email, groups)


def forget(username: str) -> None:
    _seen.pop(username, None)


def csrf_guard(request: Request) -> None:
    """State-changing requests must come from our own pages: custom header + same-origin checks."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    if request.headers.get("x-ibgod") != "1":
        raise HTTPException(status_code=403, detail="Missing request marker")
    site = request.headers.get("sec-fetch-site")
    if site and site not in ("same-origin", "none"):
        raise HTTPException(status_code=403, detail="Cross-site request blocked")
    origin = request.headers.get("origin")
    if origin:
        host = urlsplit(origin).netloc.lower()
        own = (request.headers.get("host") or "").lower()
        if host != own and host not in config.PUBLIC_HOSTS:
            raise HTTPException(status_code=403, detail="Cross-origin request blocked")


def rate_limit(username: str, action: str, limit: int, window_s: int) -> None:
    now = time.time()
    with db.tx() as con:
        n = con.execute("SELECT COUNT(*) FROM usage_log WHERE username=? AND action=? AND ts>?", (username, action, now - window_s)).fetchone()[0]
        if n >= limit:
            raise HTTPException(status_code=429, detail="You have reached the limit for this feature. Try again later.")
        con.execute("INSERT INTO usage_log(username, action, ts) VALUES(?,?,?)", (username, action, now))
        con.execute("DELETE FROM usage_log WHERE ts<?", (now - 7 * 86400,))


def get_settings(con, username: str) -> dict:
    r = con.execute("SELECT settings FROM users WHERE username=?", (username,)).fetchone()
    try:
        return json.loads(r[0]) if r else {}
    except (ValueError, TypeError):
        return {}
