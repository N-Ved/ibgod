"""Tiny HTTP client for exercising a running IB God instance (stdlib only)."""
import json, urllib.request, urllib.error, urllib.parse

BASE = "http://127.0.0.1:18081"


def call(method, path, body=None, headers=None, raw=False, timeout=120):
    h = {"X-IBGod": "1", "Accept": "application/json"}
    if headers is not None:
        h.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={k: v for k, v in h.items() if v is not None})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
            if raw:
                return r.status, dict(r.headers), payload
            return r.status, (json.loads(payload) if payload else None)
    except urllib.error.HTTPError as e:
        payload = e.read()
        if raw:
            return e.code, dict(e.headers), payload
        try:
            return e.code, json.loads(payload)
        except ValueError:
            return e.code, payload.decode("utf-8", "replace")


def get(path, **kw): return call("GET", path, **kw)
def post(path, body=None, **kw): return call("POST", path, body if body is not None else {}, **kw)
def q(s): return urllib.parse.quote(s, safe="")


def reset():
    """Delete the test user's data so every test run starts clean."""
    call("POST", "/api/account/delete", {"confirm": "DELETE"})
    return get("/api/me")
