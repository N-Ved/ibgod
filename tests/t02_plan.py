import sys, collections, datetime
sys.path.insert(0, "tests")
from client import *

WEEK = [90, 90, 90, 90, 0, 180, 180]
SUBS = [
    {"subject": "physics", "level": "HL", "current_grade": 5, "target_grade": 7},
    {"subject": "math_aa", "level": "HL", "current_grade": 4, "target_grade": 6},
    {"subject": "chemistry", "level": "HL", "current_grade": 5, "target_grade": 6},
    {"subject": "economics", "level": "SL", "current_grade": 6, "target_grade": 7},
    {"subject": "lang_a_ll:English", "level": "SL", "current_grade": 5, "target_grade": 6},
    {"subject": "lang_b:Spanish", "level": "SL", "current_grade": 6, "target_grade": 7}]


def setup(month="May", year=2027, week=WEEK, subs=SUBS):
    return post("/api/setup", {"display_name": "Dev Tester", "session_month": month, "session_year": year, "weekly_minutes": week, "subjects": subs})


def all_tasks(start):
    out, days = [], []
    d = datetime.date.fromisoformat(start)
    while True:
        s, p = get(f"/api/plan?start={d.isoformat()}&days=120")
        out += p["tasks"]; days += p["days"]
        if not p["span"]["last"] or (d + datetime.timedelta(days=120)).isoformat() > p["span"]["last"]:
            return out, days, p
        d += datetime.timedelta(days=120)


def report(label, show_days=10):
    s, me = get("/api/me")
    tasks, days, plan = all_tasks(me["today"])
    cap = {d["date"]: d["capacity"] for d in days}
    print(f"=== {label}: {len(tasks)} tasks, span {plan['span']['first']} → {plan['span']['last']}, exams {plan['exam_start']}")
    for k, v in plan["summary"]["subjects"].items(): print("   ", k, v)
    by = collections.defaultdict(lambda: collections.Counter()); mins = collections.Counter()
    for t in tasks:
        by[t["subject_name"]][t["kind"]] += 1; mins[t["subject_name"]] += t["minutes"]
    for sname, c in by.items(): print(f"    {sname:16s} {mins[sname]/60:5.1f} h  " + ", ".join(f"{k}={v}" for k, v in sorted(c.items())))
    weekly = collections.Counter(); wcap = collections.Counter()
    for t in tasks: weekly[datetime.date.fromisoformat(t["date"]).isocalendar()[:2]] += t["minutes"]
    for d in days: wcap[datetime.date.fromisoformat(d["date"]).isocalendar()[:2]] += d["capacity"]
    print("    weekly load (planned/cap h):", " ".join(f"{weekly[w]/60:.0f}/{wcap[w]/60:.0f}" for w in sorted(wcap) if wcap[w] or weekly[w]))
    perday = collections.defaultdict(list)
    for t in tasks: perday[t["date"]].append(t)
    over = [(d, sum(t["minutes"] for t in ts), cap.get(d, 0)) for d, ts in perday.items() if sum(t["minutes"] for t in ts) > cap.get(d, 0) + 15]
    print(f"    overloaded days: {len(over)} {over[:5]}  | max subjects/day: {max(len({t['subject'] for t in ts}) for ts in perday.values())}  | max tasks/day: {max(len(ts) for ts in perday.values())}")
    for d in sorted(perday)[:show_days]:
        print(f"    {d} ({sum(t['minutes'] for t in perday[d])}/{cap.get(d,0)} min): " + " | ".join(f"{t['title'][:44]} [{t['minutes']}]" for t in perday[d]))
    print("    ... last days:")
    for d in sorted(perday)[-4:]:
        print(f"    {d} ({sum(t['minutes'] for t in perday[d])}/{cap.get(d,0)} min): " + " | ".join(f"{t['title'][:44]} [{t['minutes']}]" for t in perday[d]))
    print(f"    issues: {len(plan['issues'])}")
    for i in plan["issues"][:10]: print("      ", i["severity"], "|", i["title"], "|", i["detail"][:100])
    return tasks, plan


if __name__ == "__main__":
    s, r = setup(); print("setup", s, r if s != 200 else r["plan"]["tasks"])
    report("6 subjects, 12 h/week, 23 weeks")
