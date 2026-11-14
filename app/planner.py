"""Study-plan generation, re-planning, and the checks that flag problems in a schedule.

The plan is deterministic: the same profile always produces the same plan, so students can
trust what a re-plan will do. Evidence behind the structure (see knowledge.py):
  • content is learned once, practised with exam questions, then revisited at growing gaps
    (spaced retrieval: +3, +10, +30 days);
  • timed past papers start once most content is covered and the newest are kept for the end;
  • time is weighted towards HL subjects and subjects with the largest grade gap.
"""
from __future__ import annotations

import heapq
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from . import catalog, db
from .knowledge import GRADE_BANDS

KIND_ORDER = {"review": 0, "learn": 1, "practice": 2, "mixed": 3, "paper": 4, "paper_review": 5, "coursework": 6, "final": 7, "custom": 8}
# Days after first study for each review round. With fewer rounds the gaps are longer (one review works best ~10 days out).
REVIEW_SCHEDULES = {1: (10,), 2: (4, 21), 3: (3, 10, 30)}
LEARN_END = {1: 0.78, 2: 0.78, 3: 0.75, 4: 0.70, 5: 0.62, 6: 0.50, 7: 0.40}
CONF_FACTOR = {1: 1.5, 2: 1.25, 3: 1.0, 4: 0.6, 5: 0.35}
GRADE_FACTOR = {1: 1.3, 2: 1.3, 3: 1.25, 4: 1.1, 5: 1.0, 6: 0.7, 7: 0.5}
DEFAULT_WEEK = [90, 90, 90, 90, 0, 180, 180]  # Mon..Sun minutes; one rest day by default


def today_local() -> date:
    return datetime.now().date()


def r5(x: float) -> int:
    return max(5, int(round(x / 5.0)) * 5)


def parse_date(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s) if s else None
    except (ValueError, TypeError):
        return None


# ───────────────────────── profile loading ─────────────────────────
def load_profile(con: sqlite3.Connection, username: str) -> dict:
    user = db.one(con, "SELECT * FROM users WHERE username=?", (username,)) or {}
    settings = json.loads(user.get("settings") or "{}")
    subs = db.rows(con, "SELECT * FROM user_subjects WHERE username=? ORDER BY position, id", (username,))
    states: dict[tuple[str, str], dict] = {}
    for r in db.rows(con, "SELECT * FROM topic_state WHERE username=?", (username,)):
        states[(r["subject"], r["topic_code"])] = r
    month = settings.get("session_month") or "May"
    year = int(settings.get("session_year") or (today_local().year + 1))
    win_start, win_end = catalog.exam_window(month, year)
    exam_start = parse_date(settings.get("exam_start")) or win_start
    week = settings.get("weekly_minutes")
    if not (isinstance(week, list) and len(week) == 7):
        week = list(DEFAULT_WEEK)
    week = [max(0, min(720, int(x or 0))) for x in week]
    return {"user": user, "settings": settings, "subjects": subs, "states": states, "month": month, "year": year, "exam_start": exam_start,
            "exam_end": max(win_end, exam_start + timedelta(days=21)), "week": week}


def subject_end(profile: dict, sub: dict) -> date:
    """Last study day for a subject: the day before its (first) exam."""
    return (parse_date(sub.get("exam_date")) or profile["exam_start"]) - timedelta(days=1)


def active_topics(profile: dict, sub: dict) -> list[dict]:
    out = []
    for t in catalog.topics_for(sub["subject"], sub["level"]):
        st = profile["states"].get((sub["subject"], t["code"]))
        enabled = t["default_on"] if (st is None or st["enabled"] is None) else bool(st["enabled"])
        if not enabled:
            continue
        out.append({**t, "confidence": (st or {}).get("confidence"), "name": ((st or {}).get("custom_name") or t["name"])})
    return out


def capacity_map(con: sqlite3.Connection, username: str, profile: dict, start: date, end: date) -> dict[date, int]:
    over = {parse_date(r["date"]): r["minutes"] for r in db.rows(con, "SELECT date, minutes FROM day_overrides WHERE username=? AND date>=? AND date<=?",
                                                                 (username, start.isoformat(), end.isoformat()))}
    cap = {}
    d = start
    while d <= end:
        cap[d] = over[d] if d in over else profile["week"][d.weekday()]
        d += timedelta(days=1)
    return cap


def subject_weight(sub: dict) -> float:
    gap = max(0, sub["target_grade"] - sub["current_grade"])
    level = 1.25 if sub["level"] == "HL" else 1.0
    need = {1: 1.2, 2: 1.2, 3: 1.15, 4: 1.1, 5: 1.0, 6: 0.9, 7: 0.6}.get(sub["current_grade"], 1.0)
    return level * (1 + 0.3 * gap) * need


# ───────────────────────── demand model ─────────────────────────
@dataclass
class Draft:
    subject: str
    kind: str
    title: str
    minutes: int
    ideal: int
    detail: str = ""
    topic_code: str | None = None
    meta: dict = field(default_factory=dict)
    children: list[tuple[int, "Draft"]] = field(default_factory=list)  # (days after parent, task)
    last: int = 0  # last allowed day index
    earliest: int = 0  # first allowed day index (a follow-up never lands before the task it follows)


def _paper_sittings(con: sqlite3.Connection, username: str, sub: dict) -> dict[str, list[dict]]:
    """Available question papers per paper number, oldest first, with their markschemes; attempted papers removed."""
    tags = catalog.subject_tags(sub["subject"])
    ph = ",".join("?" * len(tags))
    s = catalog.get_subject(sub["subject"]) or {}
    lang_sql = "" if s.get("family") in ("lang_a", "lang_b") else " AND (r.lang IS NULL OR r.lang='en')"
    rows = db.rows(con, f"""SELECT r.id, r.kind, r.paper, r.year, r.session, r.tz, r.syllabus, r.pair_id, r.title, r.collection FROM resources r
                            WHERE r.subject IN ({ph}) AND r.collection IN ('past_papers','specimen','mocks') AND r.kind IN ('question_paper','booklet','audio')
                            AND r.paper IS NOT NULL AND (r.level IS NULL OR r.level IN (?, 'HLSL')){lang_sql}""", (*tags, sub["level"]))
    tried = {r["resource_id"] for r in db.rows(con, "SELECT DISTINCT resource_id FROM paper_attempts WHERE username=?", (username,))}
    groups: dict[tuple, dict] = {}
    for r in rows:
        num = r["paper"][0]
        key = (num, r["year"] or 0, r["session"] or "", r["tz"] or "", r["collection"])
        g = groups.setdefault(key, {"paper": num, "year": r["year"], "session": r["session"], "tz": r["tz"], "legacy": r["syllabus"] == "legacy", "resources": [], "markschemes": [],
                                    "collection": r["collection"], "tried": False})
        g["resources"].append(r["id"])
        if r["pair_id"]:
            g["markschemes"].append(r["pair_id"])
        if r["id"] in tried:
            g["tried"] = True
        if r["syllabus"] != "legacy":
            g["legacy"] = False
    out: dict[str, list[dict]] = {}
    for g in groups.values():
        if g["tried"] or not g["year"]:
            continue
        out.setdefault(g["paper"], []).append(g)
    for num in out:
        out[num].sort(key=lambda g: (not g["legacy"], g["year"], 0 if g["session"] == "May" else 1, g["tz"] or ""))
    return out


def _sitting_label(g: dict) -> str:
    return " ".join(x for x in [g["session"], str(g["year"]) if g["year"] else "", g["tz"]] if x)


def _subject_drafts(con: sqlite3.Connection, username: str, profile: dict, sub: dict, n_days: int, budget: int, resolved: set[tuple], done_papers: dict[str, int],
                    maxcap: int = 180) -> tuple[list[Draft], dict]:
    """All tasks a subject should get, shaped by its grade band and fitted to its minute budget. Returns (drafts, summary).

    The budget is split the way the grade band recommends (content / topic practice / timed papers):
    a student on a 3 spends most of it learning content, a student on a 6 spends most of it on papers.
    Nothing is generated beyond the budget: when time is short the programme gets thinner, not the days longer.
    """
    s = catalog.get_subject(sub["subject"])
    if not s or n_days <= 0:
        return [], {"budget": budget, "demand": 0, "short": 0}
    key, name = sub["subject"], s["short"]
    level, cur = sub["level"], max(1, min(7, sub["current_grade"]))
    topics = active_topics(profile, sub)
    comps = [c for c in s["assessment"].get(level, []) if c["kind"] == "exam"]
    weeks = n_days / 7.0
    band = GRADE_BANDS[cur]
    mix = band["mix"]
    last = n_days - 1

    # Order: syllabus order, with weak topics pulled earlier.
    n = max(1, len(topics))
    order = sorted(range(len(topics)), key=lambda i: i + ((topics[i]["confidence"] or 3) - 3) * n * 0.15)
    topics = [topics[i] for i in order]
    hrs = [t["unit_hours"] / max(1, t["unit_size"]) for t in topics if t.get("unit_hours")]
    mean_hours = (sum(hrs) / len(hrs)) if hrs else None

    def size_of(t: dict) -> float:
        if mean_hours and t.get("unit_hours"):
            return max(0.6, min(1.6, (t["unit_hours"] / max(1, t["unit_size"])) / mean_hours))
        return 1.0

    def review_len(c: dict) -> int:
        return r5(min(90, maxcap, c["minutes"] * 0.5))

    def paper_cost(c: dict) -> int:
        return c["minutes"] + review_len(c)

    n_final = (3 if n_days >= 14 else 2 if n_days >= 7 else 1) if (comps and n_days >= 3) else 0
    final_len = min(35, max(15, r5(maxcap * 0.5))) if maxcap < 70 else 35
    finals = n_final * final_len
    if finals > budget * 0.25:
        n_final = max(0, int(budget * 0.25 // final_len))
        finals = n_final * final_len
    avail = max(0, budget - finals)

    # ── timed papers: chosen one sitting at a time (Paper 1, Paper 2, Paper 3, Paper 1, ...) while the paper budget lasts ──
    sittings = _paper_sittings(con, username, sub) if comps else {}
    max_avail = max((len(v) for v in sittings.values()), default=0)
    can_sit = bool(comps) and maxcap >= 30 and weeks >= 0.5
    cycles_floor = 0 if (weeks < 1 or not can_sit) else (1 if weeks < 3 else 2)
    cycles_cap = max(cycles_floor, min(12 if cur >= 5 else 5, max(max_avail, cycles_floor), int(weeks // 1.5) or cycles_floor))
    share_cap = 0.6 if cur >= 5 else 0.4
    floor_cost = sum(paper_cost(c) * max(0, cycles_floor - done_papers.get(c["name"], 0)) for c in comps)
    paper_budget = max(avail * mix[2] / 100, min(floor_cost, avail * share_cap)) if can_sit else 0
    sit_count = {c["name"]: 0 for c in comps}
    spent = 0

    def next_sitting(limit: float) -> bool:
        nonlocal spent
        for cyc in range(1, cycles_cap + 1):
            for c in comps:
                have = done_papers.get(c["name"], 0) + sit_count[c["name"]]
                if have < cyc:
                    if spent + paper_cost(c) <= limit:
                        sit_count[c["name"]] += 1
                        spent += paper_cost(c)
                        return True
                    return False
        return False

    while can_sit and next_sitting(paper_budget):
        pass
    rest = max(0, avail - spent)

    need_learn = [t for t in topics if (key, "learn", t["code"], 0) not in resolved]
    need_prac = [t for t in topics if (key, "practice", t["code"], 0) not in resolved]

    # ── spaced reviews are reserved first: retrieval at growing gaps is the best-evidenced technique we have ──
    max_rev = 3 if weeks >= 8 else (2 if weeks >= 3 else 1)
    n_reviews, rev_len = 0, 20
    if topics and weeks >= 1:
        options = [(c, length) for c in range(max_rev, 0, -1) for length in (20, 15)]
        pick = next(((c, length) for c, length in options if len(topics) * c * length <= rest * 0.38), None)
        n_reviews, rev_len = pick if pick else ((1, 15) if len(topics) * 15 <= rest * 0.38 else (0, 20))
    gaps = REVIEW_SCHEDULES.get(n_reviews, ())
    reviews_total = sum(rev_len for t in topics for i in range(1, n_reviews + 1) if (key, "review", t["code"], i) not in resolved)
    # When per-topic reviews do not fit, review whole units instead: coarser, but the spacing effect is kept.
    unit_reviews: list[tuple[str, str, int, int]] = []  # (unit code, unit name, round, position of the unit's last topic)
    unit_gaps: tuple = ()
    if topics and n_reviews == 0 and weeks >= 1:
        upos: dict[str, tuple[str, int]] = {}
        for i, t in enumerate(topics):
            upos[t["unit_code"]] = (t["unit_name"], i)
        rounds = next((c for c in range(max_rev, 0, -1) if len(upos) * c * 20 <= rest * 0.38), 0)
        unit_gaps = REVIEW_SCHEDULES.get(rounds, ())
        unit_reviews = [(uc, un, rnd, pos) for uc, (un, pos) in upos.items() for rnd in range(1, rounds + 1) if (key, "review", f"unit:{uc}", rnd) not in resolved]
        reviews_total = len(unit_reviews) * 20
    rest2 = max(0, rest - reviews_total)

    # ── content ──
    base_learn = (65 if level == "HL" else 50) * GRADE_FACTOR[cur]
    ideal = {t["code"]: min(maxcap, base_learn * size_of(t) * CONF_FACTOR.get(t["confidence"] or 3, 1.0)) for t in need_learn}
    content_budget = rest2 * mix[0] / max(1, mix[0] + mix[1])
    learn: dict[str, float] = {}
    tot_ideal = sum(ideal.values())
    if tot_ideal <= content_budget:
        learn = dict(ideal)
    elif tot_ideal > 0:
        k = content_budget / tot_ideal
        if all(v * k >= 20 for v in ideal.values()):
            learn = {c: v * k for c, v in ideal.items()}
        else:
            # Not enough time to re-learn everything: spend it on the weakest topics, the rest go straight to practice.
            remaining = content_budget
            for t in sorted(need_learn, key=lambda t: (t["confidence"] or 3)):
                m = max(25.0, ideal[t["code"]] * k)
                if remaining >= m:
                    learn[t["code"]] = m
                    remaining -= m
    learn = {c: r5(max(20, v)) for c, v in learn.items()}
    practice_budget = max(0, rest2 - sum(learn.values()))

    # ── topic practice (per topic when there is time, per unit when there is not) ──
    practice: dict[str, int] = {}
    unit_practice: list[tuple[str, str, int]] = []
    n_p = max(1, len(need_prac))
    per = practice_budget / n_p
    if need_prac and per >= 20:
        for t in need_prac:
            boost = 1.15 if (t["confidence"] or 3) <= 2 else 1.0
            practice[t["code"]] = r5(max(20, min(60, maxcap, per * max(0.8, min(1.25, size_of(t))) * boost)))
    elif need_prac:
        units: dict[str, dict] = {}
        for t in need_prac:
            u = units.setdefault(t["unit_code"], {"name": t["unit_name"], "weak": 9})
            u["weak"] = min(u["weak"], t["confidence"] or 3)
        todo_units = sorted(((c, u) for c, u in units.items() if (key, "practice", f"unit:{c}", 0) not in resolved), key=lambda x: x[1]["weak"])
        if todo_units:
            m = r5(max(20, min(60, maxcap, practice_budget / len(todo_units))))
            affordable = int(practice_budget // m) if m else 0
            keep = {c for c, _ in todo_units[:affordable]}
            unit_practice = [(c, u["name"], m) for c, u in units.items() if c in keep]
    leftover = practice_budget - sum(practice.values()) - sum(m for _, _, m in unit_practice)
    mixed = max(0, min(int(leftover // 45), int(weeks * 1.5))) if (topics and maxcap >= 45) else 0
    leftover -= mixed * 45
    while can_sit and next_sitting(spent + leftover):
        leftover = max(0, avail - spent - reviews_total - sum(learn.values()) - sum(practice.values()) - sum(m for _, _, m in unit_practice) - mixed * 45)

    content_minutes = sum(learn.values()) + sum(practice.values()) + sum(m for _, _, m in unit_practice) + reviews_total
    all_minutes = content_minutes + spent + mixed * 45 + finals
    f_end = LEARN_END[cur]
    if all_minutes > 0:
        f_end = min(0.88, max(f_end, content_minutes / all_minutes + 0.03))
    if n_days < 28:
        f_end = min(0.88, f_end + 0.1)
    drafts: list[Draft] = []
    tips = {"learn": "Read actively: try a few questions first, explain each idea in your own words, and finish with a 5-minute brain dump from memory.",
            "practice": "Exam questions on this topic. Mark with the markscheme and log every lost mark in your error log.",
            "practice_cold": "Start with a 5-minute brain dump of the topic, then exam questions. Re-read notes only for what you could not recall. Log every lost mark.",
            "review": "Closed-book retrieval: write everything you remember, check, then re-test the gaps.",
            "mixed": "Mixed questions from different topics. Decide which method each question needs before solving."}
    for i, t in enumerate(topics):
        code = t["code"]
        tname = f"{code} {t['name']}" if code and not t["name"].startswith(code) else t["name"]
        ideal_day = int((i / n) * f_end * last)
        parent: Draft | None = None
        if code in learn:
            parent = Draft(key, "learn", f"Learn: {tname}", learn[code], ideal_day, tips["learn"], code, {"phase": "content"}, last=last)
            drafts.append(parent)
        if code in practice:
            pr = Draft(key, "practice", f"Practise: {tname}", practice[code], ideal_day + 1, tips["practice" if parent else "practice_cold"], code, {"phase": "content"}, last=last)
            if parent:
                parent.children.append((1, pr))
            else:
                parent = pr
                drafts.append(pr)
        for kk in range(1, n_reviews + 1):
            if (key, "review", code, kk) in resolved:
                continue
            rv = Draft(key, "review", f"Review: {tname}", rev_len, ideal_day + gaps[kk - 1], tips["review"], code, {"phase": "review", "n": kk}, last=last)
            if parent:
                parent.children.append((gaps[kk - 1], rv))
            else:
                drafts.append(rv)
    for ucode, uname, rnd, pos in unit_reviews:
        base_day = int(((pos + 1) / n) * f_end * last)
        rv = Draft(key, "review", f"Review: {uname}", 20, base_day + unit_gaps[rnd - 1], tips["review"], f"unit:{ucode}", {"phase": "review", "n": rnd}, last=last)
        rv.earliest = min(last, base_day + 1)
        drafts.append(rv)
    for j, (ucode, uname, m) in enumerate(unit_practice):
        drafts.append(Draft(key, "practice", f"Practise: {uname}", m, int(((j + 0.5) / len(unit_practice)) * f_end * last), tips["practice_cold"], f"unit:{ucode}", {"phase": "content"}, last=last))

    # Timed papers: spread from once content is mostly covered until just before exams, newest last.
    jobs = []
    for c in comps:
        num = "".join(ch for ch in c["name"] if ch.isdigit())[:1]
        avail_s = sittings.get(num, [])
        need = sit_count[c["name"]]
        chosen = avail_s[-need:] if need else []
        for kk in range(need):
            off = kk - (need - len(chosen))
            jobs.append((kk, c, chosen[off] if off >= 0 and chosen else None))
    jobs.sort(key=lambda j: j[0])
    f0 = 0.15 if cur >= 6 else max(0.3, f_end * 0.6)
    if n_days < 21:
        f0 = 0.2
    for j, (kk, c, g) in enumerate(jobs):
        f = f0 + (0.94 - f0) * (j + 0.5) / max(1, len(jobs))
        label = f"{name} {c['name']}" + (f" · {_sitting_label(g)}" if g else "")
        meta = {"phase": "papers", "component": c["name"], "cycle": done_papers.get(c["name"], 0) + kk + 1}
        if g:
            meta.update(resources=g["resources"][:6], markschemes=g["markschemes"][:6], legacy=g["legacy"])
        detail = "Sit it under exam conditions. " + (c.get("detail") or "")
        if g and g["legacy"]:
            detail += " This paper is from the previous syllabus: skip questions on topics you do not study."
        if not g:
            detail += " No unused paper was found in the library for this slot: pick one from the subject's Past papers tab."
        parts = max(1, -(-c["minutes"] // max(30, maxcap)))  # split when no day is long enough for the whole paper
        part_len = r5(c["minutes"] / parts)
        first: Draft | None = None
        prev: Draft | None = None
        for pi in range(parts):
            title = f"Timed paper: {label}" + (f" (part {pi + 1} of {parts})" if parts > 1 else "")
            d_txt = detail.strip() + (f" Your days are shorter than this paper, so it is split: do part {pi + 1} against the clock ({part_len} of {c['minutes']} minutes)." if parts > 1 else " Sit it in one go.")
            pmeta = dict(meta) if pi == 0 else {**meta, "part": pi + 1}
            sit = Draft(key, "paper", title, part_len, int(f * last), d_txt, None, pmeta, last=last)
            if prev:
                prev.children.append((1, sit))
            else:
                first = sit
            prev = sit
        rev = Draft(key, "paper_review", f"Mark and review: {label}", review_len(c), 0,
                    "Mark strictly with the markscheme. Write one error-log line for every lost mark and redo those questions next week.", None, {**meta, "part": 0}, last=last)
        prev.children.append((0, rev))
        drafts.append(first)
    for m in range(mixed):
        f = f_end * 0.5 + (0.95 - f_end * 0.5) * (m + 0.5) / mixed
        drafts.append(Draft(key, "mixed", f"Mixed practice: {name}", 45, int(f * last), tips["mixed"], None, {"phase": "practice"}, last=last))
    for qn in range(n_final):
        f = (0.965, 0.985, 1.0)[3 - n_final + qn]
        drafts.append(Draft(key, "final", f"Final review: {name}", final_len, int(f * last),
                            "Error log, formula/data booklet, your three weakest topics. No new material. Early night.", None, {"phase": "final", "n": qn + 1}, last=last))
    if not comps:
        block = r5(min(75, max(20, maxcap)))
        blocks = max(1, int(min(weeks, max(1.0, leftover / block))))
        for b in range(blocks):
            drafts.append(Draft(key, "coursework", f"Coursework block: {name}", block, int((b + 0.5) / blocks * last),
                                "Work against the assessment criteria. Note what you did and what is next.", None, {"phase": "coursework"}, last=last))

    def total(ds: list[Draft]) -> int:
        return sum(d.minutes + total([c for _, c in d.children]) for d in ds)

    demand = total(drafts)
    # The least that still makes a sound programme: practice and one review per topic, half the usual content time,
    # two rounds of timed papers and the final reviews. Below about 60% of this the plan is too thin to trust.
    sound = (len(topics) * (25 + 15) + 0.5 * sum(base_learn * size_of(t) * CONF_FACTOR.get(t["confidence"] or 3, 1.0) for t in topics)
             + (2 * sum(c["minutes"] * 1.5 for c in comps) + 105 if comps else weeks * 45))
    typical = sound
    coverage = round(min(2.0, budget / sound), 2) if sound > 0 else 1.0
    return drafts, {"budget": int(budget), "demand": int(demand), "short": int(max(0, demand - budget)), "papers": sum(sit_count.values()), "reviews": n_reviews, "review_minutes": rev_len,
                    "split": list(mix), "topics": len(topics), "learn_tasks": len(learn), "practice_only": len(need_learn) - len(learn), "unit_practice": len(unit_practice), "unit_reviews": len(unit_reviews), "mixed": mixed,
                    "typical": int(typical), "coverage": coverage}


# ───────────────────────── scheduling ─────────────────────────
def generate(con: sqlite3.Connection, username: str, today: date | None = None, keep_pinned: bool = True) -> dict:
    """(Re)build the plan from today. Completed work and pinned/manual tasks are kept; everything else is rescheduled."""
    today = today or today_local()
    profile = load_profile(con, username)
    subs = profile["subjects"]
    start = max(today, parse_date(profile["settings"].get("start_date")) or today)
    ends = {s["subject"]: subject_end(profile, s) for s in subs}
    summary: dict = {"generated_at": datetime.now().isoformat(timespec="seconds"), "start": start.isoformat(), "subjects": {}, "tasks": 0, "dropped": 0}
    keep_sql = "status<>'todo' OR origin='manual'" + (" OR pinned=1" if keep_pinned else "")
    con.execute(f"DELETE FROM tasks WHERE username=? AND NOT ({keep_sql})", (username,))
    if not keep_pinned:
        con.execute("UPDATE tasks SET pinned=0 WHERE username=? AND status='todo'", (username,))
    if not subs or not ends or max(ends.values()) < start:
        db.set_meta(con, f"plan:{username}", summary)
        return summary
    horizon = max(ends.values())
    cap = capacity_map(con, username, profile, start, horizon)
    days = sorted(cap)
    idx = {d: i for i, d in enumerate(days)}
    used = [0] * len(days)
    per_subject_day: dict[tuple[int, str], int] = {}
    day_subjects: dict[int, set] = {}
    day_kinds: dict[tuple[int, str], set] = {}
    day_reviews: dict = {}
    kept = db.rows(con, "SELECT * FROM tasks WHERE username=?", (username,))
    resolved: set[tuple] = set()
    done_papers: dict[str, dict[str, int]] = {}
    for t in kept:
        meta = json.loads(t["meta"] or "{}")
        if t["kind"] in ("learn", "practice"):
            resolved.add((t["subject"], t["kind"], t["topic_code"], 0))
        elif t["kind"] == "review":
            resolved.add((t["subject"], "review", t["topic_code"], int(meta.get("n") or 1)))
        elif t["kind"] == "paper" and meta.get("component") and not meta.get("part"):
            done_papers.setdefault(t["subject"], {})
            done_papers[t["subject"]][meta["component"]] = done_papers[t["subject"]].get(meta["component"], 0) + 1
        if t["status"] == "todo":
            d = parse_date(t["date"])
            if d in idx:
                i = idx[d]
                used[i] += t["minutes"]
                per_subject_day[(i, t["subject"] or "")] = per_subject_day.get((i, t["subject"] or ""), 0) + 1
                if t["kind"] != "review":
                    day_subjects.setdefault(i, set()).add(t["subject"] or "")

    weights = {s["subject"]: subject_weight(s) for s in subs}
    wsum = sum(weights.values()) or 1.0
    all_drafts: list[Draft] = []
    for s in subs:
        end = ends[s["subject"]]
        if end < start:
            summary["subjects"][s["subject"]] = {"budget": 0, "demand": 0, "short": 0, "ended": True}
            continue
        n_days = idx[end] + 1
        free = sum(max(0, cap[days[i]] - used[i]) for i in range(n_days))
        maxcap = max((cap[days[i]] for i in range(n_days)), default=0)
        budget = int(free * 0.9 * weights[s["subject"]] / wsum)
        drafts, info = _subject_drafts(con, username, profile, s, n_days, budget, resolved, done_papers.get(s["subject"], {}), maxcap)
        summary["subjects"][s["subject"]] = info
        all_drafts += drafts

    now = datetime.now().isoformat(timespec="seconds")
    rows = []

    def fits(i: int, d: Draft, strict: bool) -> bool:
        c = cap[days[i]]
        if c <= 0 or used[i] + d.minutes > c + 10:
            return False
        if strict and d.kind == "review":
            # Short retrieval sessions are good warm-ups, but a day made only of them is fragmented.
            if day_reviews.get(i, 0) >= (3 if c <= 90 else 4) or day_reviews.get((i, d.subject), 0) >= 2:
                return False
        if strict and d.kind != "review":
            if per_subject_day.get((i, d.subject), 0) >= 2:
                return False
            if d.kind in ("final", "paper", "mixed", "coursework") and d.kind in day_kinds.get((i, d.subject), ()):
                return False
            # Limit context switching: at most 2 subjects on a short day, 3 on a normal one, 4 on a long one.
            subjects_today = day_subjects.get(i, set())
            if d.subject not in subjects_today and len(subjects_today) >= (2 if c <= 90 else 3 if c <= 150 else 4):
                return False
        return True

    def place(d: Draft, ideal: int) -> int | None:
        """Day index for a task. If no day has room, the task is shortened to the best remaining slot, or dropped (None)."""
        lo = max(0, min(d.earliest, d.last))
        ideal = max(lo, min(ideal, d.last))
        for strict in (True, False):
            for i in range(ideal, d.last + 1):
                if fits(i, d, strict):
                    return i
            for i in range(ideal - 1, lo - 1, -1):
                if fits(i, d, strict):
                    return i
        free_days = [(cap[days[i]] - used[i], -abs(i - ideal), i) for i in range(lo, d.last + 1) if cap[days[i]] > 0]
        if free_days:
            room, _, i = max(free_days)
            floor = 30 if d.kind == "paper" else 15
            if room >= floor:
                d.minutes = max(floor, (room // 5) * 5)
                return i
        return None

    def commit(d: Draft, ideal: int, queue: list | None = None) -> None:
        nonlocal seq
        i = place(d, ideal)
        if i is None:
            summary["dropped"] += 1 + len(d.children)
            return
        used[i] += d.minutes
        per_subject_day[(i, d.subject)] = per_subject_day.get((i, d.subject), 0) + 1
        if d.kind != "review":
            day_subjects.setdefault(i, set()).add(d.subject)
        else:
            day_reviews[i] = day_reviews.get(i, 0) + 1
            day_reviews[(i, d.subject)] = day_reviews.get((i, d.subject), 0) + 1
        day_kinds.setdefault((i, d.subject), set()).add(d.kind)
        rows.append((username, d.subject, d.kind, d.title[:200], d.detail[:600], d.topic_code, days[i].isoformat(), d.minutes, "todo", 0, "auto", json.dumps(d.meta), KIND_ORDER.get(d.kind, 9), now))
        for offset, child in d.children:
            # Follow-ups (practice after learning, reviews, marking a paper) may slip later, never earlier than their trigger.
            child.earliest = min(child.last, i + (1 if child.kind in ("review", "paper") else 0))
            if queue is None:
                commit(child, min(child.last, i + offset))
            else:
                heapq.heappush(queue, (min(child.last, i + offset), KIND_ORDER.get(child.kind, 9), seq, child))
                seq += 1

    seq = 0
    # Big rocks first: final reviews and timed papers need long, specific slots, so they claim their days before the small tasks.
    big = sorted((d for d in all_drafts if d.kind in ("final", "paper", "coursework")), key=lambda d: (0 if d.kind == "final" else 1, d.ideal))
    for d in big:
        commit(d, max(0, min(d.ideal, d.last)))
    heap: list[tuple[int, int, int, Draft]] = []
    for d in all_drafts:
        if d.kind not in ("final", "paper", "coursework"):
            heapq.heappush(heap, (max(0, min(d.ideal, d.last)), KIND_ORDER.get(d.kind, 9), seq, d))
            seq += 1
    while heap:
        ideal, _, _, d = heapq.heappop(heap)
        commit(d, ideal, heap)

    # Keep every subject warm: where the schedule leaves a subject untouched for too long, add a short retrieval session.
    for s in subs:
        key = s["subject"]
        end = ends[key]
        if end < start:
            continue
        end_i = idx[end]
        limit = 10 if s["level"] == "HL" else 13
        label = (catalog.get_subject(key) or {}).get("short", key)
        blocked: set[tuple[int, int]] = set()
        for _ in range(len(days)):
            mine = sorted({i for (i, k), n_ in per_subject_day.items() if k == key and n_ > 0 and i <= end_i})
            if not mine:
                break
            gap = next(((a, b) for a, b in zip(mine, mine[1:]) if b - a > limit and (a, b) not in blocked), None)
            if not gap:
                break
            length = 20
            cands = [i for i in range(gap[0] + 1, gap[1]) if cap[days[i]] > 0 and used[i] + 20 <= cap[days[i]] + 10]
            if not cands:
                length = 15
                cands = [i for i in range(gap[0] + 1, gap[1]) if cap[days[i]] > 0 and used[i] + 15 <= cap[days[i]] + 15]
            if not cands:
                blocked.add(gap)
                continue
            mid = (gap[0] + gap[1]) // 2
            i = min(cands, key=lambda i: abs(i - mid))
            used[i] += length
            per_subject_day[(i, key)] = per_subject_day.get((i, key), 0) + 1
            rows.append((username, key, "mixed", f"Quick retrieval: {label}", "No notes: brain-dump two topics you studied earlier, check them against your notes, then fix the gaps.",
                         None, days[i].isoformat(), length, "todo", 0, "auto", json.dumps({"phase": "review", "warm": True}), KIND_ORDER["mixed"], now))
    con.executemany("INSERT INTO tasks(username,subject,kind,title,detail,topic_code,date,minutes,status,pinned,origin,meta,sort,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    summary["tasks"] = len(rows)
    db.set_meta(con, f"plan:{username}", summary)
    return summary


# ───────────────────────── checks ─────────────────────────
def evaluate(con: sqlite3.Connection, username: str, today: date | None = None) -> dict:
    """Find problems in the current schedule. Each issue has a stable key so a dismissal sticks until the situation changes."""
    today = today or today_local()
    profile = load_profile(con, username)
    subs = {s["subject"]: s for s in profile["subjects"]}
    tasks = db.rows(con, "SELECT * FROM tasks WHERE username=? ORDER BY date, sort, id", (username,))
    todo = [t for t in tasks if t["status"] == "todo"]
    issues: list[dict] = []

    def add(key: str, severity: str, title: str, detail: str, fix: str, ident: str | None = None, amount: float = 1, **extra) -> None:
        # key: changes whenever the situation changes (so a dismissal expires). ident: stays the same while the problem exists.
        issues.append({"key": key, "ident": ident or key, "amount": amount, "severity": severity, "title": title, "detail": detail, "fix": fix, **extra})

    def sname(key: str | None) -> str:
        s = catalog.get_subject(key) if key else None
        return s["short"] if s else "General"

    ends = {k: subject_end(profile, s) for k, s in subs.items()}
    horizon = max(ends.values()) if ends else today
    future = [t for t in todo if t["date"] >= today.isoformat()]
    overdue = [t for t in todo if t["date"] < today.isoformat()]
    if overdue:
        mins = sum(t["minutes"] for t in overdue)
        add(f"overdue:{overdue[0]['date']}:{len(overdue)}", "high" if len(overdue) >= 5 else "medium", f"{len(overdue)} task{'s' if len(overdue) != 1 else ''} overdue",
            f"About {mins // 60} h {mins % 60} min of planned work is in the past and not marked done.",
            "Mark what you actually did, then press Re-plan to spread the rest over the coming weeks.", ident="overdue", amount=len(overdue), action="replan", task_ids=[t["id"] for t in overdue[:50]])

    end_cap = max(horizon, max((parse_date(t["date"]) or today for t in future), default=today))
    cap = capacity_map(con, username, profile, today, end_cap) if end_cap >= today else {}
    by_day: dict[str, list[dict]] = {}
    for t in future:
        by_day.setdefault(t["date"], []).append(t)
    for dstr, ts in sorted(by_day.items()):
        d = parse_date(dstr)
        planned = sum(t["minutes"] for t in ts)
        c = cap.get(d, 0)
        if c <= 0:
            add(f"blocked:{dstr}:{len(ts)}", "high", f"Tasks on a day off ({d.strftime('%a %d %b')})", f"{len(ts)} task(s) totalling {planned} min are scheduled on a day you marked as unavailable.",
                "Move them to another day or give this day some study time.", ident=f"blocked:{dstr}", amount=planned, date=dstr, task_ids=[t["id"] for t in ts])
        elif planned > c + 15:
            sev = "high" if planned > c * 1.5 + 30 else "medium"
            add(f"overload:{dstr}:{planned}", sev, f"{d.strftime('%a %d %b')} is overloaded", f"{planned} min planned but only {c} min available ({planned - c} min over).",
                "Move a task to a lighter day nearby, shorten one, or raise this day's available time.", ident=f"overload:{dstr}", amount=planned - c, date=dstr, task_ids=[t["id"] for t in ts])
        if planned > 420:
            add(f"longday:{dstr}:{planned // 30}", "low", f"Very long day ({d.strftime('%a %d %b')})", f"{planned // 60} h {planned % 60} min of study in one day. Returns drop sharply after about six focused hours.",
                "Spread the work across neighbouring days if you can.", ident=f"longday:{dstr}", amount=planned, date=dstr)

    for t in future:
        d = parse_date(t["date"])
        end = ends.get(t["subject"]) if t["subject"] else None
        if end and d and d > end:
            add(f"afterexam:{t['id']}:{t['date']}", "high", f"Scheduled after the exam: {t['title']}", f"{sname(t['subject'])} exams begin {(end + timedelta(days=1)).strftime('%d %b %Y')}; this task is dated {d.strftime('%d %b')}.",
                "Move it earlier or delete it.", ident=f"afterexam:{t['id']}", date=t["date"], task_ids=[t["id"]], subject=t["subject"])

    # Ordering and spacing within a topic.
    learn_at: dict[tuple, dict] = {}
    for t in tasks:
        if t["kind"] == "learn" and t["topic_code"]:
            learn_at[(t["subject"], t["topic_code"])] = t
    for t in future:
        if t["kind"] in ("practice", "review") and t["topic_code"]:
            lt = learn_at.get((t["subject"], t["topic_code"]))
            if lt and lt["status"] == "todo":
                if t["date"] < lt["date"]:
                    add(f"order:{t['id']}:{t['date']}:{lt['date']}", "medium", f"Out of order: {t['title']}", f"This is planned for {t['date']}, before you learn the topic ({lt['date']}).",
                        "Move it after the 'Learn' task for the same topic.", ident=f"order:{t['id']}", date=t["date"], task_ids=[t["id"], lt["id"]], subject=t["subject"])
                elif t["kind"] == "review" and t["date"] == lt["date"]:
                    add(f"spacing:{t['id']}:{t['date']}", "low", f"Review on the same day as learning: {t['title']}", "A review only strengthens memory after some forgetting. Same-day reviews add little.",
                        "Move the review at least two days after the 'Learn' task.", ident=f"spacing:{t['id']}", date=t["date"], task_ids=[t["id"]], subject=t["subject"])

    # Rest and consistency.
    if cap:
        streak, streak_start = 0, None
        d = today
        while d <= end_cap:
            if by_day.get(d.isoformat()):
                streak += 1
                streak_start = streak_start or d
                if streak == 14:
                    add(f"norest:{streak_start.isoformat()}", "low", "Two weeks with no day off", f"Every day from {streak_start.strftime('%d %b')} has study planned.",
                        "Keep at least one free day a week. Rest protects sleep, mood and memory.", ident="norest", date=streak_start.isoformat())
            else:
                streak, streak_start = 0, None
            d += timedelta(days=1)

    total_cap = sum(cap.values())
    total_planned = sum(t["minutes"] for t in future)
    if future and total_planned > total_cap + 60:
        over = total_planned - total_cap
        add(f"capacity:{over // 120}", "high", "More work than time", f"The remaining plan needs about {over // 60} h more than your availability before exams.",
            "Add study time on some days in Settings, lower a target, or re-plan to trim reviews and papers.", ident="capacity", amount=over, action="replan")

    weights = {k: subject_weight(s) for k, s in subs.items()}
    wsum = sum(weights.values()) or 1.0
    weeks_left = max(0.0, (horizon - today).days / 7.0)
    plan_meta = (db.get_meta(con, f"plan:{username}", {}) or {}).get("subjects", {})
    thin = {k: v for k, v in plan_meta.items() if k in subs and isinstance(v, dict) and v.get("coverage") is not None and v["coverage"] < 0.6 and ends.get(k, today) >= today}
    if thin:
        worst = sorted(thin.items(), key=lambda kv: kv[1]["coverage"])
        need = sum(max(0, v["typical"] - v["budget"]) for v in thin.values())
        per_week = need / 60 / max(1.0, weeks_left)
        names = ", ".join(f"{sname(k)} ({int(v['coverage'] * 100)}%)" for k, v in worst[:6])
        add(f"thin:{len(thin)}:{int(per_week)}", "high" if worst[0][1]["coverage"] < 0.35 else "medium", "Not enough time for these targets",
            f"Your available hours cover only part of the minimum these targets need (content, practice, a review and two rounds of papers): {names}. The plan has been thinned to fit: fewer papers and reviews, practice by unit instead of by topic.",
            f"Add roughly {max(1, round(per_week))} h a week in Settings and re-plan, or focus your targets on fewer subjects.", ident="thin", amount=len(thin), action="replan")
    for key, s in subs.items():
        mine = [t for t in future if t["subject"] == key]
        end = ends[key]
        if end < today:
            continue
        mins = sum(t["minutes"] for t in mine)
        fair = total_cap * 0.9 * weights[key] / wsum
        subj = catalog.get_subject(key) or {}
        has_exam = any(c["kind"] == "exam" for c in subj.get("assessment", {}).get(s["level"], []))
        if total_cap > 600 and mins < fair * 0.55 and weeks_left >= 2:
            add(f"under:{key}:{int(mins // 300)}", "medium", f"{sname(key)} is getting little time", f"{mins // 60} h planned against roughly {int(fair // 60)} h that its level and grade gap ({s['current_grade']}→{s['target_grade']}) suggest.",
                "Re-plan, or add sessions for this subject.", ident=f"under:{key}", amount=fair - mins, action="replan", subject=key)
        if mine:
            dates = sorted({t["date"] for t in mine})
            first = parse_date(dates[0])
            if first and (first - today).days > 21:
                add(f"latestart:{key}:{dates[0]}", "medium", f"{sname(key)} does not start for {(first - today).days} days", "A long gap before starting means forgetting what you know now and less time for spaced reviews.",
                    "Move a first session into the next two weeks.", ident=f"latestart:{key}", amount=(first - today).days, subject=key, date=dates[0])
            limit = 12 if s["level"] == "HL" else 16
            prev = first
            for dstr in dates[1:]:
                d = parse_date(dstr)
                if prev and d and (d - prev).days > limit:
                    add(f"gap:{key}:{prev.isoformat()}:{dstr}", "low", f"{(d - prev).days}-day gap in {sname(key)}", f"Nothing is planned between {prev.strftime('%d %b')} and {d.strftime('%d %b')}.",
                        "Add a short retrieval session in the gap so the subject stays warm.", ident=f"gap:{key}", amount=(d - prev).days, subject=key, date=prev.isoformat())
                    break
                prev = d
            last14 = sum(t["minutes"] for t in mine if (end - (parse_date(t["date"]) or end)).days < 14)
            if mins > 600 and weeks_left > 5 and last14 > mins * 0.45:
                add(f"cram:{key}:{int(last14 // 120)}", "medium", f"{sname(key)} is back-loaded", f"{int(100 * last14 / mins)}% of the remaining work sits in the final two weeks.",
                    "Pull some sessions earlier. Spaced work is remembered far better than crammed work.", ident=f"cram:{key}", amount=last14, subject=key)
            papers = [t for t in mine if t["kind"] == "paper"]
            done_p = [t for t in tasks if t["subject"] == key and t["kind"] == "paper" and t["status"] == "done"]
            if has_exam and weeks_left >= 4 and len(papers) + len(done_p) < 2 and key not in thin:
                add(f"papers:{key}:{len(papers)}", "medium", f"Too few timed papers for {sname(key)}", "Fewer than two full timed papers are planned. Exam-condition practice is the best predictor of exam performance.",
                    "Add timed papers from the subject's past papers tab, or re-plan.", ident=f"papers:{key}", amount=2 - len(papers) - len(done_p), subject=key, action="replan")
        elif has_exam and weeks_left >= 1:
            add(f"empty:{key}", "high", f"Nothing planned for {sname(key)}", "This subject has no upcoming sessions.", "Press Re-plan to schedule it.", action="replan", subject=key)

    dismissed = {r["key"] for r in db.rows(con, "SELECT key FROM dismissed_issues WHERE username=?", (username,))}
    order = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda i: (order[i["severity"]], i.get("date") or "9999"))
    live_keys = {i["key"] for i in issues}
    stale = dismissed - live_keys
    if stale:
        con.executemany("DELETE FROM dismissed_issues WHERE username=? AND key=?", [(username, k) for k in stale])
    return {"issues": [i for i in issues if i["key"] not in dismissed], "dismissed": [i for i in issues if i["key"] in dismissed]}


def stats(con: sqlite3.Connection, username: str, today: date | None = None) -> dict:
    """Progress numbers for the dashboard."""
    today = today or today_local()
    profile = load_profile(con, username)
    tasks = db.rows(con, "SELECT subject, kind, date, minutes, status, done_at FROM tasks WHERE username=?", (username,))
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    out = {"today": today.isoformat(), "exam_start": profile["exam_start"].isoformat(), "days_left": (profile["exam_start"] - today).days,
           "session": f"{profile['month']} {profile['year']}", "subjects": {}, "week": {"planned": 0, "done": 0}, "streak": 0, "total": {"planned": 0, "done": 0}}
    done_days = set()
    for t in tasks:
        s = out["subjects"].setdefault(t["subject"] or "", {"planned": 0, "done": 0, "todo_tasks": 0, "done_tasks": 0})
        if t["status"] == "skipped":
            continue
        s["planned"] += t["minutes"]
        out["total"]["planned"] += t["minutes"]
        if t["status"] == "done":
            s["done"] += t["minutes"]
            s["done_tasks"] += 1
            out["total"]["done"] += t["minutes"]
            if t["done_at"]:
                done_days.add(t["done_at"][:10])
        else:
            s["todo_tasks"] += 1
        if week_start.isoformat() <= t["date"] <= week_end.isoformat():
            out["week"]["planned"] += t["minutes"]
            if t["status"] == "done":
                out["week"]["done"] += t["minutes"]
    d = today
    if d.isoformat() not in done_days:
        d -= timedelta(days=1)
    while d.isoformat() in done_days:
        out["streak"] += 1
        d -= timedelta(days=1)
    return out
