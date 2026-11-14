"""Client for the local llama.cpp server. One generation at a time: the CPU cannot do more."""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Iterator

import httpx

from . import config

log = logging.getLogger("ibgod.llm")
_lock = threading.Lock()
_waiting = 0
_waiting_lock = threading.Lock()
_health = {"ok": False, "at": 0.0, "model": None}


def available(force: bool = False) -> bool:
    if not config.LLM_ENABLED:
        return False
    if not force and time.time() - _health["at"] < 15:
        return bool(_health["ok"])
    ok = False
    try:
        r = httpx.get(config.LLM_URL + "/health", timeout=2.5)
        ok = r.status_code == 200
        if ok and not _health["model"]:
            try:
                m = httpx.get(config.LLM_URL + "/v1/models", timeout=2.5).json()
                _health["model"] = (m.get("data") or [{}])[0].get("id")
            except Exception:
                pass
    except Exception:
        ok = False
    _health.update(ok=ok, at=time.time())
    return ok


def info() -> dict:
    name = (_health["model"] or "").rsplit("/", 1)[-1].replace(".gguf", "")
    return {"available": available(), "busy": _lock.locked(), "waiting": _waiting, "model": name or None}


class Busy(Exception):
    pass


def _acquire(timeout: float, on_wait=None) -> None:
    global _waiting
    with _waiting_lock:
        _waiting += 1
    try:
        deadline = time.time() + timeout
        while not _lock.acquire(timeout=2.0):
            if time.time() > deadline:
                raise Busy()
            if on_wait:
                on_wait()
    finally:
        with _waiting_lock:
            _waiting -= 1


def _body(messages: list[dict], max_tokens: int, temperature: float, stream: bool, schema: dict | None) -> dict:
    body = {"messages": messages, "max_tokens": max_tokens, "temperature": temperature, "top_p": 0.9, "stream": stream, "cache_prompt": True,
            "chat_template_kwargs": {"enable_thinking": False}}
    if schema:
        body["response_format"] = {"type": "json_schema", "json_schema": {"name": "out", "strict": True, "schema": schema}}
    return body


def stream(messages: list[dict], max_tokens: int = 500, temperature: float = 0.4, queue_timeout: float = 600) -> Iterator[dict]:
    """Yield {'wait': n} while queued, then {'text': delta} pieces, then {'done': stats}."""
    global _waiting
    with _waiting_lock:
        _waiting += 1
    got = False
    try:
        deadline = time.time() + queue_timeout
        while True:
            got = _lock.acquire(timeout=3.0)
            if got:
                break
            if time.time() > deadline:
                raise Busy()
            yield {"wait": _waiting}
    finally:
        with _waiting_lock:
            _waiting -= 1
    try:
        started = time.time()
        n = 0
        with httpx.stream("POST", config.LLM_URL + "/v1/chat/completions", json=_body(messages, max_tokens, temperature, True, None),
                          timeout=httpx.Timeout(connect=5, read=600, write=30, pool=5)) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except ValueError:
                    continue
                delta = ((obj.get("choices") or [{}])[0].get("delta") or {}).get("content")
                if delta:
                    n += 1
                    yield {"text": delta}
        yield {"done": {"seconds": round(time.time() - started, 1), "pieces": n}}
    finally:
        _lock.release()


def complete(messages: list[dict], max_tokens: int = 400, temperature: float = 0.3, schema: dict | None = None, queue_timeout: float = 3600) -> str:
    _acquire(queue_timeout)
    try:
        r = httpx.post(config.LLM_URL + "/v1/chat/completions", json=_body(messages, max_tokens, temperature, False, schema),
                       timeout=httpx.Timeout(connect=5, read=1500, write=60, pool=5))
        r.raise_for_status()
        return (r.json()["choices"][0]["message"].get("content") or "").strip()
    finally:
        _lock.release()
