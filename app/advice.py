"""The grade-improvement path for one subject: what holds this grade back and what to do next."""
from __future__ import annotations

import sqlite3

from . import catalog, db, planner
from .knowledge import CORE_POINTS_NOTE, FAMILY_TIPS, GRADE_BANDS, TECHNIQUES

BAND_TECHNIQUES = {
    1: ["worked-examples", "retrieval-practice", "syllabus-checklist", "timeboxing"],
    2: ["worked-examples", "retrieval-practice", "syllabus-checklist", "timeboxing"],
    3: ["retrieval-practice", "worked-examples", "successive-relearning", "error-log"],
    4: ["retrieval-practice", "spaced-practice", "command-terms", "error-log"],
    5: ["interleaving", "past-papers", "command-terms", "error-log"],
    6: ["past-papers", "error-log", "interleaving", "exam-nerves"],
    7: ["past-papers", "spaced-practice", "sleep"],
}
_T = {t["id"]: t for t in TECHNIQUES}


def subject_path(con: sqlite3.Connection, username: str, profile: dict, sub: dict) -> dict:
    s = catalog.get_subject(sub["subject"]) or {}
    cur, target, level = sub["current_grade"], sub["target_grade"], sub["level"]
    band = GRADE_BANDS[max(1, min(7, cur))]
    steps = []
    for g in range(cur, max(cur, target)):
        b = GRADE_BANDS[max(1, min(7, g))]
        steps.append({"from": g, "to": g + 1, "title": b["title"], "focus": b["focus"], "actions": b["actions"], "mix": b["mix"]})
    if not steps:
        steps.append({"from": cur, "to": cur, "title": band["title"], "focus": band["focus"], "actions": band["actions"], "mix": band["mix"]})

    comps = s.get("assessment", {}).get(level, [])
    coursework = sum(c["weight"] for c in comps if c["kind"] == "coursework")
    topics = planner.active_topics(profile, sub)
    rated = [t for t in topics if t["confidence"]]
    weak = sorted([t for t in rated if t["confidence"] <= 2], key=lambda t: t["confidence"])
    unrated = len(topics) - len(rated)
    attempts = db.rows(con, """SELECT a.score, a.max_score, a.date FROM paper_attempts a JOIN resources r ON r.id=a.resource_id
                               WHERE a.username=? AND r.subject IN (%s) AND a.max_score>0 ORDER BY a.date""" % ",".join("?" * len(catalog.subject_tags(sub["subject"]))),
                       (username, *catalog.subject_tags(sub["subject"])))
    pct = [round(100 * a["score"] / a["max_score"]) for a in attempts if a["score"] is not None]

    nxt: list[str] = []
    if topics and all(t["coverage"] == 0 for t in topics):
        nxt.append("Tick off what your class has already covered in the Topics checklist, then re-plan: covered topics skip straight to practice and review.")
    if unrated and topics:
        nxt.append(f"Rate your confidence on {unrated} topic{'s' if unrated != 1 else ''} below so the plan can weight them properly.")
    if weak:
        nxt.append("Start with your weakest topics: " + ", ".join(f"{t['code']} {t['name']}" for t in weak[:4]) + ".")
    if coursework and cur < target:
        nxt.append(f"Coursework is {int(coursework)}% of this subject. Check it against the criteria in the subject guide and an exemplar before submitting.")
    if not pct and any(c["kind"] == "exam" for c in comps):
        nxt.append("Sit one timed paper and record your score in the Past papers tab. It gives a real baseline for the plan.")
    elif pct:
        trend = "rising" if len(pct) >= 2 and pct[-1] > pct[0] else "flat or falling" if len(pct) >= 2 else "one result so far"
        nxt.append(f"Your recorded paper scores: {', '.join(str(p) + '%' for p in pct[-5:])} ({trend}). Compare with the grade boundaries document in the library.")
    if target - cur >= 2:
        nxt.append("A jump of two or more grades is realistic only with consistent weekly hours. Treat the plan's sessions for this subject as fixed appointments.")
    if cur >= target:
        nxt.append("You are at your target. Keep the maintenance sessions and let spare hours go to other subjects.")

    fam = FAMILY_TIPS.get(s.get("family") or "", None)
    return {
        "current": cur, "target": target, "level": level, "steps": steps, "time_split": {"content": band["mix"][0], "practice": band["mix"][1], "papers": band["mix"][2]},
        "next_actions": nxt, "family_tips": fam, "coursework_weight": coursework,
        "techniques": [{"id": i, "title": _T[i]["title"], "summary": _T[i]["summary"]} for i in BAND_TECHNIQUES[max(1, min(7, cur))] if i in _T],
        "paper_scores": pct, "core_note": CORE_POINTS_NOTE,
        "note": s.get("note"),
    }


def tip_of_the_day(day_number: int) -> dict:
    pool = [t for t in TECHNIQUES if t["utility"] in ("high", "moderate", "practical")]
    t = pool[day_number % len(pool)]
    return {"id": t["id"], "title": t["title"], "summary": t["summary"]}
