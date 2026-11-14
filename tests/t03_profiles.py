"""Plan invariants across very different students. A freshly generated plan must be internally consistent."""
import sys, collections, datetime
sys.path.insert(0, "tests")
from client import *
from t02_plan import all_tasks, SUBS, WEEK

def check(label, expect_issue_types=()):
    s, me = get("/api/me")
    today = me["today"]
    tasks, days, plan = all_tasks(today)
    cap = {d["date"]: d["capacity"] for d in days}
    errs = []
    learn = {(t["subject"], t["topic_code"]): t for t in tasks if t["kind"] == "learn"}
    by_title = collections.defaultdict(list)
    for t in tasks:
        if t["date"] < today: errs.append(f"task before today: {t['title']} {t['date']}")
        end = plan["exam_dates"].get(t["subject"])
        if end and t["date"] >= end: errs.append(f"task on/after exam: {t['title']} {t['date']} >= {end}")
        if t["kind"] in ("practice", "review") and (t["subject"], t["topic_code"]) in learn:
            l = learn[(t["subject"], t["topic_code"])]
            if t["date"] < l["date"] or (t["kind"] == "review" and t["date"] <= l["date"]): errs.append(f"{t['kind']} not after learn: {t['title']} {t['date']} vs {l['date']}")
        if t["kind"] in ("paper", "paper_review"): by_title[t["title"].split(": ", 1)[1]].append(t)
        if t["minutes"] < 5 or t["minutes"] > 300: errs.append(f"odd minutes {t['minutes']} {t['title']}")
    for k, ts in by_title.items():
        sit = [t for t in ts if t["kind"] == "paper"]; rev = [t for t in ts if t["kind"] == "paper_review"]
        if sit and rev and min(r["date"] for r in rev) < min(x["date"] for x in sit): errs.append(f"paper marked before sat: {k}")
    used_papers = [tuple(t["resources"]) for t in tasks if t["kind"] == "paper" and t["resources"] and "(part" not in t["title"]]
    dup = [k for k, v in collections.Counter(used_papers).items() if v > 1]
    if dup: errs.append(f"same paper scheduled twice: {len(dup)}")
    perday = collections.Counter()
    for t in tasks: perday[t["date"]] += t["minutes"]
    over = [(d, m, cap.get(d, 0)) for d, m in perday.items() if m > cap.get(d, 0) + 15]
    types = collections.Counter(i["key"].split(":")[0] for i in plan["issues"])
    unexpected = {k: v for k, v in types.items() if k not in expect_issue_types}
    mins = collections.Counter()
    for t in tasks: mins[t["subject_name"]] += t["minutes"]
    kinds = collections.Counter(t["kind"] for t in tasks)
    print(f"--- {label}: tasks={len(tasks)} hours={sum(mins.values())/60:.0f} span={plan['span']['first']}→{plan['span']['last']} exams={plan['exam_start']}")
    print("    kinds:", dict(kinds)); print("    hours:", {k: round(v / 60, 1) for k, v in mins.items()})
    print("    summary:", {k: (v.get("papers"), v.get("reviews"), v.get("learn_tasks"), v.get("practice_only"), v.get("unit_practice"), v.get("unit_reviews"), v.get("coverage")) for k, v in plan["summary"]["subjects"].items()}, "(papers, reviews, learn, practice-only, unit-practice, unit-reviews, coverage)")
    print(f"    issues: {dict(types)}  overloaded days: {len(over)}  invariant errors: {len(errs)}")
    for e in errs[:6]: print("      ERR", e)
    for i in plan["issues"][:5]: print("      ISSUE", i["severity"], i["title"], "|", i["detail"][:90])
    ok = not errs and not unexpected
    print("    RESULT:", "PASS" if ok else f"FAIL unexpected={unexpected}")
    return ok

def setup(month, year, week, subs, exam_start=None):
    body = {"display_name": "Dev Tester", "session_month": month, "session_year": year, "weekly_minutes": week, "subjects": subs}
    if exam_start: body["exam_start"] = exam_start
    s, r = post("/api/setup", body)
    assert s == 200, (s, r)

reset()
s, me = get("/api/me"); today = datetime.date.fromisoformat(me["today"])
results = []
setup("May", 2027, WEEK, SUBS); results.append(check("A standard: 6 subjects, 12 h/wk, May 2027"))
setup("May", 2027, [150, 150, 150, 150, 60, 300, 240], SUBS, (today + datetime.timedelta(days=35)).isoformat()); results.append(check("B exams in 5 weeks, 20 h/wk", expect_issue_types=("thin", "norest")))
setup("May", 2027, [30, 30, 30, 30, 0, 60, 60], SUBS); results.append(check("C only 4 h/wk", expect_issue_types=("thin",)))
setup("May", 2027, [240, 240, 240, 240, 120, 360, 360], SUBS[:3]); results.append(check("D 3 subjects, 30 h/wk", expect_issue_types=("norest",)))
setup("November", 2027, WEEK, SUBS); results.append(check("E November 2027 (a year out)"))
setup("May", 2028, WEEK, [{"subject": "visual_arts", "level": "HL", "current_grade": 5, "target_grade": 6}, {"subject": "custom:Marine Science", "level": "SL", "current_grade": 3, "target_grade": 5},
                          {"subject": "history", "level": "HL", "current_grade": 2, "target_grade": 5}, {"subject": "ab_initio:French", "level": "SL", "current_grade": 7, "target_grade": 7},
                          {"subject": "anthropology", "level": "SL", "current_grade": 4, "target_grade": 5}, {"subject": "biology", "level": "SL", "current_grade": 6, "target_grade": 7}]); results.append(check("F arts + custom + generic + May 2028"))
setup("May", 2027, WEEK, SUBS, (today + datetime.timedelta(days=4)).isoformat()); results.append(check("G exams in 4 days", expect_issue_types=("thin",)))
setup("May", 2026, WEEK, SUBS); results.append(check("H session already over"))
setup("May", 2027, [0, 0, 0, 0, 0, 0, 0][:6] + [0], SUBS[:2]) if False else None
print("ALL PASS" if all(results) else "SOME FAILED", results)
