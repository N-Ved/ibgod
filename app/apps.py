"""The Apps page: links to the other services on this server, showing only the ones the person can open.

Access is not configured here. For each service IB God asks Caddy, with the person's own Authelia session cookie,
for a small file on that site (`probe`). Caddy runs the normal Authelia check first, so the answer follows
Authelia's live access_control rules: allowed -> the site answers, not allowed -> 403, not signed in -> redirect.
The Files app is also hidden when the person has no view permission in FileBrowser.
Results are cached per person for a few minutes. Hosts and paths come only from apps.json, never from the request.
"""
from __future__ import annotations

import http.client
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import access, config

log = logging.getLogger("ibgod.apps")
CADDY = ("caddy", 80)
CACHE_S = 300
_cache: dict[str, tuple[float, list[dict]]] = {}
_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="apps")


def _catalogue() -> list[dict]:
    with open(config.APPS_FILE, encoding="utf-8") as f:
        return json.load(f)


def _allowed(app: dict, cookie: str) -> bool:
    """True when Caddy + Authelia let this session through to the app."""
    try:
        conn = http.client.HTTPConnection(*CADDY, timeout=4)
        conn.request("HEAD", app.get("probe") or "/", headers={"Host": app["host"], "Cookie": cookie, "X-Forwarded-Proto": "https", "User-Agent": "ibgod-apps-check"})
        res = conn.getresponse()
        status, location = res.status, res.getheader("Location") or ""
        conn.close()
    except OSError as e:
        log.warning("apps check for %s failed: %r", app.get("key"), e)
        return False
    if status >= 400:
        return False
    if 300 <= status < 400 and "auth." in location:
        return False  # sent to the login page: not allowed with this session
    return True


def for_user(username: str, cookie_header: str) -> list[dict]:
    # Only the Authelia session cookie is passed on, and only to Caddy on the internal network.
    session = "; ".join(c.strip() for c in (cookie_header or "").split(";") if c.strip().startswith("authelia_session="))
    key = username.lower()
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_S:
            return hit[1]
    apps = _catalogue()
    checks = {a["key"]: _pool.submit(_allowed, a, session) for a in apps if not a.get("always") and a.get("host") and session}
    out = []
    for a in apps:
        ok = True if a.get("always") else (checks[a["key"]].result() if a["key"] in checks else False)
        if ok and a.get("filebrowser") and not access.policy(username).view:
            ok = False
        if ok:
            out.append({k: a[k] for k in ("key", "name", "description", "url", "icon", "color") if k in a})
    with _lock:
        _cache[key] = (time.time(), out)
    return out
