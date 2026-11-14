"""AI study coach: retrieval over the study-science knowledge base and the library, answered by the local model."""
from __future__ import annotations

import re
import sqlite3

from . import catalog, planner, search
from .knowledge import FAMILY_TIPS, GRADE_BANDS, TECHNIQUES

SYSTEM = """You are IB God, a study coach for International Baccalaureate Diploma students. You run privately on the school's own server.

Rules:
- Be specific and practical. Give steps the student can do today. Prefer short paragraphs and numbered steps.
- Ground advice in the STUDY SCIENCE and LIBRARY notes you are given. When you use a library extract, name the resource in brackets, like [Physics Study Guide p.42].
- Use what you know about the student (subjects, grades, time left). Never invent facts about IB rules, dates or grade boundaries: if unsure, say so and point to the subject guide.
- For subject questions, explain the idea clearly, then suggest one way to test themselves on it.
- Do not write assessed work (IA, EE, TOK essay) for the student. Give feedback and guidance instead.
- Keep answers under about 220 words unless the student asks for more. No preamble, no closing pleasantries."""

_WORD = re.compile(r"[a-z]{3,}")
_STOP = {"the", "and", "for", "with", "that", "this", "how", "what", "why", "can", "should", "does", "have", "about", "from", "are", "you", "your", "get", "need", "want", "best", "way", "help"}


def relevant_techniques(question: str, k: int = 2) -> list[dict]:
    words = {w for w in _WORD.findall(question.lower()) if w not in _STOP}
    scored = []
    for t in TECHNIQUES:
        hay = (t["title"] + " " + t["summary"] + " " + t["category"] + " " + t["when"]).lower()
        score = sum(2 if w in t["title"].lower() else 1 for w in words if w in hay)
        if score:
            scored.append((score, t))
    scored.sort(key=lambda x: -x[0])
    return [t for _, t in scored[:k]]


def detect_subject(question: str, subs: list[dict]) -> dict | None:
    q = question.lower()
    best = None
    for s in subs:
        c = catalog.get_subject(s["subject"]) or {}
        names = {c.get("short", "").lower(), c.get("name", "").lower()} | {n for n in c.get("names", [])}
        if c.get("key") in ("math_aa", "math_ai"):
            names |= {"math", "maths", "mathematics"}
        if any(n and re.search(rf"\b{re.escape(n)}\b", q) for n in names):
            best = s
            break
    return best


def profile_text(profile: dict, stats: dict) -> str:
    lines = [f"Exam session: {profile['month']} {profile['year']} ({stats['days_left']} days until exams start)."]
    for s in profile["subjects"]:
        c = catalog.get_subject(s["subject"]) or {}
        lines.append(f"- {c.get('name', s['subject'])} {s['level']}: currently {s['current_grade']}, target {s['target_grade']}")
    wk = stats.get("week", {})
    lines.append(f"This week: {wk.get('done', 0)} of {wk.get('planned', 0)} planned minutes done.")
    return "\n".join(lines)


def build(con: sqlite3.Connection, username: str, question: str, history: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return (messages for the model, sources to show the student)."""
    profile = planner.load_profile(con, username)
    stats = planner.stats(con, username)
    sub = detect_subject(question, profile["subjects"])
    techs = relevant_techniques(question)
    tags = catalog.subject_tags(sub["subject"]) if sub else None
    passages = []
    if len(question.split()) >= 2:
        passages = search.passages(con, question, tags, collections=["notes", "books", "official"], limit=2, max_chars=650)
        if not passages and tags:
            passages = search.passages(con, question, tags, limit=2, max_chars=650)
    ctx = []
    if techs:
        ctx.append("STUDY SCIENCE:\n" + "\n".join(f"* {t['title']}: {t['summary']} How: {' '.join(t['how'][:3])}" for t in techs))
    if sub:
        band = GRADE_BANDS[max(1, min(7, sub["current_grade"]))]
        fam = FAMILY_TIPS.get((catalog.get_subject(sub["subject"]) or {}).get("family") or "")
        ctx.append(f"GRADE {sub['current_grade']} FOCUS: {band['focus']} Key moves: {' '.join(band['actions'][:3])}" + (f" Subject tips: {' '.join(fam['tips'][:2])}" if fam else ""))
    if passages:
        ctx.append("LIBRARY:\n" + "\n".join(f"[{p['title']}{' p.' + str(p['page']) if p.get('page') else ''}] {p['text']}" for p in passages))
    messages = [{"role": "system", "content": SYSTEM + "\n\nSTUDENT:\n" + profile_text(profile, stats)}]
    for m in history[-6:]:
        messages.append({"role": m["role"], "content": m["content"][:1200]})
    user = question.strip()[:2000]
    if ctx:
        user = "\n\n".join(ctx) + "\n\nQUESTION: " + user
    messages.append({"role": "user", "content": user})
    sources = [{"type": "technique", "id": t["id"], "title": t["title"]} for t in techs]
    sources += [{"type": "resource", "id": p["id"], "title": p["title"], "url": p["url"], "page": p.get("page")} for p in passages]
    return messages, sources


def fallback_answer(question: str, sources: list[dict]) -> str:
    """What the student sees when the AI model is unavailable: the retrieved guidance itself."""
    techs = relevant_techniques(question, 2) or TECHNIQUES[:2]
    parts = ["The AI model is not available right now, so here is the most relevant guidance from the knowledge base:"]
    for t in techs:
        parts.append(f"**{t['title']}**\n{t['summary']}\n" + "\n".join(f"{i}. {h}" for i, h in enumerate(t["how"], 1)))
    if any(s["type"] == "resource" for s in sources):
        parts.append("Related material from your library is linked below.")
    return "\n\n".join(parts)
