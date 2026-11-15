"""Who may see which library file: FileBrowser's own rules, applied here too.

IB God reads FileBrowser's database (read-only) and config.yaml and re-reads them whenever they change, so
anything changed in FileBrowser (a user's folder scope or view permission, an access rule on a folder or file,
FileBrowser groups, `denyByDefault`) applies to the library, search, topic links, past papers and file downloads
within about half a minute, for everyone. Nothing is configured per user in IB God.

How a decision is made, matching FileBrowser Quantum's behaviour (checked on this server: a rule on /Shaffy/ that
only allows two users hides the folder and every file in it from everyone else):
  1. The user needs the `view` permission on the source and the file must be inside the user's scope.
     Someone who never opened FileBrowser gets FileBrowser's defaults from config.yaml (it creates them the same way).
  2. Access rules apply to their path and everything below it. The most specific rule that says something about the
     user wins: listed in Deny (by name or group) -> hidden; listed in Allow -> visible; `denyAll` -> hidden.
  3. If no rule decides, the file is visible unless `denyByDefault` is on.
If FileBrowser's data cannot be read, everything is hidden (fail closed) rather than everything shown.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field

from . import config

log = logging.getLogger("ibgod.access")
REFRESH_S = 30


@dataclass
class Policy:
    username: str
    view: bool = False
    scope: str = ""  # relative to the library root, "" = everything
    denies: list[tuple[str, list[str]]] = field(default_factory=list)  # (hidden prefix, visible exceptions below it)
    default_deny: bool = False
    allows: list[str] = field(default_factory=list)  # with default_deny: the only visible prefixes

    def visible(self, path: str | None) -> bool:
        if not self.view or not path:
            return False
        if self.scope and not _under(path, self.scope):
            return False
        if self.default_deny and not any(_under(path, a) for a in self.allows):
            return False
        for deny, exceptions in self.denies:
            if _under(path, deny) and not any(_under(path, e) for e in exceptions):
                return False
        return True


def _under(path: str, prefix: str) -> bool:
    return prefix == "" or path == prefix or path.startswith(prefix + "/")


def _rel(fb_path: str) -> str:
    return fb_path.strip("/")


_lock = threading.Lock()
_state: dict = {"loaded": 0.0, "stamp": None, "users": {}, "groups": {}, "rules": [], "defaults": None, "error": None, "policies": {}}


def _stamp() -> tuple:
    out = []
    base = config.FB_DB
    for f in (base, base + "-wal", os.path.join(os.path.dirname(base), "config.yaml")):
        try:
            st = os.stat(f)
            out.append((f, st.st_mtime_ns, st.st_size))
        except OSError:
            out.append((f, None, None))
    return tuple(out)


def _read_defaults() -> dict:
    """The few keys of FileBrowser's config.yaml that decide access for people FileBrowser has not seen yet."""
    d = {"scope": config.FB_DEFAULT_SCOPE, "view": config.FB_DEFAULT_VIEW, "deny_by_default": config.FB_DENY_BY_DEFAULT}
    path = os.path.join(os.path.dirname(config.FB_DB), "config.yaml")
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return d
    def val(key: str) -> str | None:
        m = re.search(rf"^\s*{key}:\s*([^\s#]+)", text, re.M)
        return m.group(1).strip("'\"") if m else None
    if val("defaultUserScope"):
        d["scope"] = val("defaultUserScope")
    if val("denyByDefault"):
        d["deny_by_default"] = val("denyByDefault").lower() == "true"
    m = re.search(r"defaultPermissions:\s*\n((?:\s+\w+:.*\n)+)", text)
    if m:
        v = re.search(r"^\s*view:\s*(\w+)", m.group(1), re.M)
        if v:
            d["view"] = v.group(1).lower() == "true"
    if val("defaultEnabled") and val("defaultEnabled").lower() == "false":
        d["view"] = False
    return d


def _open() -> sqlite3.Connection:
    # Normal read-only open sees changes still in FileBrowser's WAL. On a read-only mount SQLite cannot create the
    # shared-memory file when FileBrowser has none open, so fall back to reading the main file as-is.
    try:
        con = sqlite3.connect(f"file:{config.FB_DB}?mode=ro", uri=True, timeout=5)
        con.execute("SELECT 1 FROM users LIMIT 1")
        return con
    except sqlite3.Error:
        return sqlite3.connect(f"file:{config.FB_DB}?mode=ro&immutable=1", uri=True, timeout=5)


def _load() -> None:
    con = _open()
    try:
        users = {}
        for username, admin, data in con.execute("SELECT username, perm_admin, user_data FROM users"):
            d = json.loads(data)
            scopes = {s.get("path"): s for s in (d.get("backendScopes") or [])}
            users[username.lower()] = {"admin": bool(admin), "scope": scopes.get(config.FB_SOURCE)}
        groups: dict[str, set] = {}
        for name, members in con.execute("SELECT name, members FROM groups"):
            try:
                m = json.loads(members)
            except (TypeError, ValueError):
                m = []
            for u in (m if isinstance(m, list) else list(m)):
                groups.setdefault(str(u).lower(), set()).add(name)
        rules = []
        for source, path, data in con.execute("SELECT source, path, rule_data FROM access_rules"):
            if source != config.FB_SOURCE:
                continue
            r = json.loads(data if isinstance(data, str) else data.decode())
            rules.append({"path": _rel(path), "deny_all": bool(r.get("denyAll")),
                          "deny_users": {u.lower() for u in ((r.get("Deny") or {}).get("Users") or {})},
                          "deny_groups": set(((r.get("Deny") or {}).get("Groups") or {})),
                          "allow_users": {u.lower() for u in ((r.get("Allow") or {}).get("Users") or {})},
                          "allow_groups": set(((r.get("Allow") or {}).get("Groups") or {}))})
    finally:
        con.close()
    _state.update(users=users, groups=groups, rules=rules, defaults=_read_defaults(), error=None, policies={})


def _refresh() -> None:
    now = time.time()
    if now - _state["loaded"] < REFRESH_S and _state["defaults"] is not None:
        return
    stamp = _stamp()
    if stamp == _state["stamp"] and _state["defaults"] is not None:
        _state["loaded"] = now
        return
    try:
        _load()
        _state["stamp"] = stamp
        log.info("FileBrowser access data loaded: %d users, %d rules", len(_state["users"]), len(_state["rules"]))
    except Exception as e:  # keep the last good data; with none, everything stays hidden
        _state["error"] = repr(e)[:200]
        log.warning("could not read FileBrowser access data: %r", e)
    _state["loaded"] = now


def _decide(rule: dict, user: str, groups: set) -> bool | None:
    if user in rule["deny_users"] or groups & rule["deny_groups"]:
        return False
    if user in rule["allow_users"] or groups & rule["allow_groups"]:
        return True
    if rule["deny_all"]:
        return False
    return None


def policy(username: str) -> Policy:
    user = username.lower()
    with _lock:
        _refresh()
        cached = _state["policies"].get(user)
        if cached:
            return cached
        if _state["defaults"] is None:
            return Policy(user)  # never loaded: fail closed
        info = _state["users"].get(user)
        defaults = _state["defaults"]
        if info is None:
            view, scope = defaults["view"], _rel(defaults["scope"] or "/")
        elif info["scope"] is None:
            view, scope = False, ""
        else:
            view = bool((info["scope"].get("permissions") or {}).get("view", False))
            scope = _rel(info["scope"].get("scope") or "/")
        groups = _state["groups"].get(user, set())
        decided = sorted(((r["path"], _decide(r, user, groups)) for r in _state["rules"]), key=lambda x: x[0].count("/") + (len(x[0]) > 0))
        decided = [(p, d) for p, d in decided if d is not None]
        denies = [(p, [q for q, dq in decided if dq and q != p and _under(q, p)]) for p, d in decided if d is False]
        pol = Policy(user, view=view, scope=scope, denies=denies, default_deny=defaults["deny_by_default"], allows=[p for p, d in decided if d])
        _state["policies"][user] = pol
        return pol


def bind(con: sqlite3.Connection, username: str) -> Policy:
    """Make `visible(r.path)` usable in this connection's queries for this user. Queries that use it on a connection
    that was not bound fail with an error instead of showing everything."""
    pol = policy(username)
    con.create_function("visible", 1, lambda p: 1 if pol.visible(p) else 0, deterministic=True)
    return pol


def status() -> dict:
    with _lock:
        _refresh()
        return {"users": len(_state["users"]), "rules": len(_state["rules"]), "error": _state["error"], "loaded": int(_state["loaded"]),
                "defaults": _state["defaults"]}
