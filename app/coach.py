"""AI study coach: retrieval over the study-science knowledge base and the library, answered by the local model."""
from __future__ import annotations

import re
import sqlite3

from . import advice, catalog, planner, search
from .knowledge import FAMILY_TIPS, GRADE_BANDS, TECHNIQUES

SYSTEM = """You are IB God, a study coach for International Baccalaureate Diploma students. You run privately on the school's own server.

Rules:
- Be specific and practical. Give steps the student can do today. Prefer short paragraphs and numbered steps.
- Base advice on the STUDY SCIENCE notes you are given and on what you know about the student (subjects, grades, time left).
- Exam facts (paper lengths, weights, formats) come ONLY from SUBJECT FACTS. If a fact is not given there, do not state it: tell the student to check the subject guide. Never invent dates, grade boundaries, syllabus codes or textbook page numbers.
- For subject questions, explain the idea clearly and correctly, use the LIBRARY extracts when they are relevant and name them in brackets like [Notes title p.4], then give one way to self-test.
- Do not write assessed work (IA, EE, TOK essay) for the student. Explain why briefly, then help them do it themselves.
- If the student seems distressed, be kind first and suggest talking to a trusted adult or school counsellor.
- Write maths in plain text with Unicode symbols (× ÷ √ ² ³ ± Δ λ ≈), for example  f' = f × v / (v − vs). Never use LaTeX, dollar signs or backslashes.
- When you set a practice calculation, give the set-up and let the student work out the final number. Do not state numerical results you were not given.
- Keep answers under about 200 words unless the student asks for more. Finish your last sentence. No preamble, no closing pleasantries."""

_WORD = re.compile(r"[a-z]{3,}")
_STOP = {"the", "and", "for", "with", "that", "this", "how", "what", "why", "can", "should", "does", "have", "about", "from", "are", "you", "your", "get", "need", "want", "best", "way", "help",
         "move", "make", "more", "most", "much", "keep", "give", "specific", "each", "every", "week", "day", "time", "when", "them", "they", "will", "would", "could", "just", "into", "than", "then",
         "subject", "subjects", "grade", "grades", "really", "always", "never", "its", "it's", "i'm", "don't", "doing", "going", "good", "better", "thing", "things", "know"}
_CONTENT = re.compile(r"\b(explain|what is|what are|what does|what's|define|definition of|how does|how do (?:you|i) (?:calculate|find|solve|derive|draw|balance)|why does|why is|why do|difference between|derive|calculate|"
                      r"prove|meaning of|describe|outline|summari[sz]e|example of|formula for|equation for)\b", re.I)
_METHOD = re.compile(r"\b(revis\w*|stud(?:y|ying|ies)|plan\w*|routine|schedule|timetable|motivat\w*|procrastinat\w*|forget\w*|remember\w*|memor\w*|improve|stress\w*|anxi\w*|nervous|sleep\w*|focus\w*|concentrat\w*|"
                     r"exam technique|past papers?|predicted|time management|burn\w*|tired|mocks?|from an? \d to an? \d|get an? [4-7]|behind|catch up|overwhelm\w*|cram\w*|flashcards?|notes)\b", re.I)
_IMPROVE = re.compile(r"\b(from an? \d to an? \d|get an? [4-7]|improve|raise|boost|higher grade|better grade|move up|go up)\b", re.I)
_CRISIS = re.compile(r"\b(kill myself|killing myself|suicid\w*|end my life|take my own life|self[- ]?harm\w*|hurt myself|harm myself|don'?t want to (?:live|be alive|be here)|want to die|no reason to live|"
                     r"being abused|abus(?:es|ing) me|hits me|not safe at home)\b", re.I)

CRISIS_REPLY = ("I'm really glad you told me, and I'm sorry things feel this heavy right now. This matters far more than any exam.\n\n"
                "I'm a study coach running on a school server, so I can't give you the support you deserve here, but people can, right now:\n\n"
                "1. Tell a trusted adult today: a parent or carer, your school counsellor, your IB coordinator or a teacher you trust.\n"
                "2. If you might act on these thoughts or you are in danger, call your local emergency number now (112 in Europe, 911 in North America).\n"
                "3. You can find a free, confidential helpline for your country at findahelpline.com.\n\n"
                "You don't have to explain everything perfectly. Saying \"I'm not okay and I need help\" is enough. Your studies can wait until you are safe and supported.")


def is_crisis(question: str) -> bool:
    return bool(_CRISIS.search(question))


def intent(question: str) -> str:
    """'method' (how to study/plan/cope), 'content' (explain a syllabus idea) or 'general'."""
    if _METHOD.search(question):
        return "method"
    if _CONTENT.search(question):
        return "content"
    return "general"


def relevant_techniques(question: str, k: int = 2) -> list[dict]:
    words = {w for w in _WORD.findall(question.lower()) if w not in _STOP}
    scored = []
    for t in TECHNIQUES:
        title = t["title"].lower()
        hay = (t["summary"] + " " + t["category"] + " " + t["when"]).lower()
        score = sum(3 for w in words if w in title) + sum(1 for w in words if w in hay)
        if score >= 2:
            scored.append((score, t))
    scored.sort(key=lambda x: -x[0])
    return [t for _, t in scored[:k]]


def detect_subject(question: str, subs: list[dict]) -> dict | None:
    q = question.lower()
    for s in subs:
        c = catalog.get_subject(s["subject"]) or {}
        names = {c.get("short", "").lower(), c.get("name", "").lower()} | set(c.get("names", []))
        if c.get("key") in ("math_aa", "math_ai"):
            names |= {"math", "maths", "mathematics"}
        if c.get("language"):
            names.add(c["language"].lower())
        if any(n and re.search(rf"\b{re.escape(n)}\b", q) for n in names):
            return s
    return None


def profile_text(profile: dict, stats: dict) -> str:
    lines = [f"Exam session: {profile['month']} {profile['year']} ({stats['days_left']} days until exams start)."]
    for s in profile["subjects"]:
        c = catalog.get_subject(s["subject"]) or {}
        lines.append(f"- {c.get('name', s['subject'])} {s['level']}: currently {s['current_grade']}, target {s['target_grade']}")
    wk = stats.get("week", {})
    lines.append(f"This week: {wk.get('done', 0)} of {wk.get('planned', 0)} planned minutes done.")
    return "\n".join(lines)


def subject_facts(sub: dict) -> str:
    c = catalog.get_subject(sub["subject"]) or {}
    parts = []
    for comp in c.get("assessment", {}).get(sub["level"], []):
        dur = f"{comp['minutes']} min, " if comp["minutes"] else ""
        parts.append(f"{comp['name']} ({dur}{comp['weight']}% of the grade): {comp['detail']}")
    return f"{c.get('name')} {sub['level']} is assessed by: " + " | ".join(parts)


def build(con: sqlite3.Connection, username: str, question: str, history: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return (messages for the model, sources to show the student)."""
    profile = planner.load_profile(con, username)
    stats = planner.stats(con, username)
    kind = intent(question)
    sub = detect_subject(question, profile["subjects"])
    if not sub and history:
        sub = detect_subject(" ".join(m["content"] for m in history[-2:] if m["role"] == "user"), profile["subjects"])
    improving = bool(_IMPROVE.search(question))
    techs = relevant_techniques(question)
    if sub and improving:
        ids = advice.BAND_TECHNIQUES[max(1, min(7, sub["current_grade"]))][:2]
        techs = [t for i in ids for t in TECHNIQUES if t["id"] == i]
    if not techs and kind != "content":
        techs = [t for t in TECHNIQUES if t["id"] in ("retrieval-practice", "spaced-practice")]
    passages: list[dict] = []
    if kind == "content" and len(question.split()) >= 2:
        # Subject questions are answered from the student's own current-syllabus notes and textbooks, nothing else.
        tags = catalog.subject_tags(sub["subject"]) if sub else sorted({t for s in profile["subjects"] for t in catalog.subject_tags(s["subject"])})
        if tags:
            passages = search.passages(con, question, tags, collections=["notes"], limit=2, max_chars=700) or search.passages(con, question, tags, collections=["books"], limit=2, max_chars=700)
    ctx = []
    if techs and kind != "content":
        ctx.append("STUDY SCIENCE:\n" + "\n".join(f"* {t['title']}: {t['summary']} How: {' '.join(t['how'][:3])}" for t in techs))
    elif techs:
        ctx.append("SELF-TEST METHOD: " + techs[0]["title"] + ". " + " ".join(techs[0]["how"][:2]))
    if not sub and kind == "method" and profile["subjects"]:
        lengths = []
        for s_ in profile["subjects"]:
            c = catalog.get_subject(s_["subject"]) or {}
            papers = ", ".join(f"{x['name']} {x['minutes']} min" for x in c.get("assessment", {}).get(s_["level"], []) if x["minutes"])
            if papers:
                lengths.append(f"{c.get('short')} {s_['level']}: {papers}")
        if lengths:
            ctx.append("SUBJECT FACTS (exam paper lengths): " + "; ".join(lengths))
    if sub:
        ctx.append("SUBJECT FACTS: " + subject_facts(sub))
        if kind != "content":
            band = GRADE_BANDS[max(1, min(7, sub["current_grade"]))]
            fam = FAMILY_TIPS.get((catalog.get_subject(sub["subject"]) or {}).get("family") or "")
            ctx.append(f"AT GRADE {sub['current_grade']}: {band['focus']} Key moves: {' '.join(band['actions'][:4])}" + (f" Examiner tips: {' '.join(fam['tips'][:3])}" if fam else ""))
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
