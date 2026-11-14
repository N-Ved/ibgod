"""Schedule edits: every change must report the issues it creates; dismissals stick; re-planning keeps the right things."""
import sys, datetime, collections
sys.path.insert(0, "tests")
from client import *
from t02_plan import all_tasks, SUBS, WEEK

ok = True
def expect(cond, label, extra=""):
    global ok
    print(("  PASS " if cond else "  FAIL ") + label + (f"  [{extra}]" if extra and not cond else ""))
    ok = ok and bool(cond)

reset()
s, r = post("/api/setup", {"display_name": "Dev Tester", "session_month": "May", "session_year": 2027, "weekly_minutes": WEEK, "subjects": SUBS}); assert s == 200
s, me = get("/api/me"); today = me["today"]
tasks, days, plan = all_tasks(today)
expect(len(plan["issues"]) == 0, "fresh plan has no issues", plan["issues"][:2])
cap = {d["date"]: d["capacity"] for d in days}
by_day = collections.defaultdict(list)
for t in tasks: by_day[t["date"]].append(t)
future = sorted(d for d in by_day if d > today)

# 1. Move a task onto a busy day → overload issue reported as created by this change
busy = max(future[:30], key=lambda d: sum(t["minutes"] for t in by_day[d]))
src = next(t for d in future[5:40] if d != busy for t in by_day[d] if t["minutes"] >= 40)
s, r = call("PATCH", f"/api/tasks/{src['id']}", {"date": busy})
expect(s == 200 and any(i["ident"] == f"overload:{busy}" for i in r["created"]), "moving a task to a full day reports an overload", r.get("created"))
expect(r["task"]["pinned"] is True, "moved task is pinned")
ov = next(i for i in r["issues"] if i["ident"] == f"overload:{busy}")
# 2. Dismiss it → gone; still listed under dismissed
s, r2 = post("/api/issues/dismiss", {"key": ov["key"]})
expect(not any(i["key"] == ov["key"] for i in r2["issues"]) and any(i["key"] == ov["key"] for i in r2["dismissed"]), "dismissed issue moves to the dismissed list")
# 3. Make it worse → the issue comes back (new key) and is reported again
src2 = next(t for d in future[5:40] if d != busy for t in by_day[d] if t["minutes"] >= 30 and t["id"] != src["id"])
s, r3 = call("PATCH", f"/api/tasks/{src2['id']}", {"date": busy})
expect(any(i["ident"] == f"overload:{busy}" for i in r3["issues"]) and any(i["ident"] == f"overload:{busy}" for i in r3["created"]), "making a dismissed problem worse resurfaces it")
# 4. Move one away → not reported as created (it got better)
s, r4 = call("PATCH", f"/api/tasks/{src2['id']}", {"date": src2["date"]})
expect(not any(i["ident"] == f"overload:{busy}" for i in r4["created"]), "improving a day is not reported as a new issue", r4["created"])
# 5. Restore
s, r5 = post("/api/issues/restore", {"key": ov["key"]})
expect(s == 200, "restore works")
# 6. Day off with tasks on it → blocked issue
target = next(d for d in future[3:20] if by_day[d])
s, r6 = call("PUT", f"/api/days/{target}", {"minutes": 0, "note": "trip"})
expect(any(i["ident"] == f"blocked:{target}" for i in r6["created"]), "marking a day off with tasks on it reports them", r6["created"])
s, r7 = call("DELETE", f"/api/days/{target}")
expect(not any(i["ident"] == f"blocked:{target}" for i in r7["issues"]), "resetting the day clears it")
# 7. Review before its learn task → order issue ; same day → spacing
learn = next(t for d in future[10:60] for t in by_day[d] if t["kind"] == "learn")
rev = next(t for t in tasks if t["kind"] == "review" and t["subject"] == learn["subject"] and t["topic_code"] == learn["topic_code"])
before = (datetime.date.fromisoformat(learn["date"]) - datetime.timedelta(days=2)).isoformat()
s, r8 = call("PATCH", f"/api/tasks/{rev['id']}", {"date": before})
expect(any(i["ident"] == f"order:{rev['id']}" for i in r8["created"]), "review before learning reports an order issue", [i["ident"] for i in r8["created"]])
s, r9 = call("PATCH", f"/api/tasks/{rev['id']}", {"date": learn["date"]})
expect(any(i["ident"] == f"spacing:{rev['id']}" for i in r9["issues"]), "review on the learning day reports a spacing issue")
# 8. Task after the exam
late = (datetime.date.fromisoformat(plan["exam_start"]) + datetime.timedelta(days=3)).isoformat()
s, r10 = call("PATCH", f"/api/tasks/{rev['id']}", {"date": late})
expect(any(i["ident"] == f"afterexam:{rev['id']}" for i in r10["created"]), "task after the exam is reported")
# 9. Add manual task; too long day
s, r11 = post("/api/tasks", {"date": future[3], "title": "Chemistry test revision <b>x</b>", "minutes": 600, "subject": "chemistry"})
expect(s == 200 and r11["task"]["origin"] == "manual" and any(i["ident"].startswith(("overload", "longday")) for i in r11["created"]), "adding a 10-hour task reports overload")
manual_id = r11["task"]["id"]
# 10. Complete tasks: done + hard → extra review and lower confidence
t_today = by_day[today][0] if by_day[today] else by_day[future[0]][0]
first_learn = next(t for t in tasks if t["kind"] == "learn")
s, r12 = call("PATCH", f"/api/tasks/{first_learn['id']}", {"status": "done", "rating": "hard"})
expect(s == 200 and r12["task"]["status"] == "done" and r12["extra"] and r12["extra"]["kind"] == "review", "marking 'hard' adds an extra review", r12.get("extra"))
# 11. Validation
s, r = call("PATCH", f"/api/tasks/{first_learn['id']}", {"date": "2027-13-45"}); expect(s == 422, "bad date rejected", s)
s, r = call("PATCH", "/api/tasks/99999999", {"status": "done"}); expect(s == 404, "unknown task → 404", s)
s, r = post("/api/tasks", {"date": future[1], "title": "", "minutes": 30}); expect(s == 422, "empty title rejected", s)
s, r = post("/api/tasks", {"date": future[1], "title": "x", "minutes": 30, "subject": "biology"}); expect(s == 404, "task for a subject you do not take rejected", s)
# 12. Re-plan keeping pinned: manual + moved tasks stay, done stays, issues from auto tasks vanish
s, rp = post("/api/plan/replan", {"keep_pinned": True}); expect(s == 200, "replan ok", rp)
tasks2, _, plan2 = all_tasks(today)
ids2 = {t["id"]: t for t in tasks2}
expect(manual_id in ids2 and ids2[manual_id]["date"] == future[3], "manual task survives a re-plan in place")
expect(src["id"] in ids2 and ids2[src["id"]]["date"] == busy, "task I moved stays where I put it")
s, dash = get("/api/dashboard")
done_kept = [t for t in dash["today"] + dash["overdue"] if t["id"] == first_learn["id"]]
s, p0 = get(f"/api/plan?start={first_learn['date']}&days=1")
expect(any(t["id"] == first_learn["id"] and t["status"] == "done" for t in p0["tasks"]), "completed task is kept by a re-plan")
uniq = {t["id"]: t for t in tasks2 + p0["tasks"]}.values()
dup = collections.Counter((t["subject"], t["kind"], t["topic_code"], t["n"]) for t in uniq if t["kind"] in ("learn", "practice") and t["topic_code"])
expect(not [k for k, v in dup.items() if v > 1 and not (k[0] == first_learn["subject"] and k[2] == first_learn["topic_code"])], "re-plan does not duplicate topic tasks", [k for k, v in dup.items() if v > 1][:3])
expect(not any(t["kind"] == "learn" and t["subject"] == first_learn["subject"] and t["topic_code"] == first_learn["topic_code"] and t["status"] == "todo" for t in tasks2), "a completed topic is not scheduled again")
# 13. Re-plan from scratch (no pins): moved tasks are released, manual tasks stay
call("DELETE", f"/api/tasks/{manual_id}")
s, rp = post("/api/plan/replan", {"keep_pinned": False}); tasks3, _, plan3 = all_tasks(today)
expect(len(plan3["issues"]) == 0, "full re-plan returns to a clean plan", [(i["ident"]) for i in plan3["issues"]][:4])
# 14. Changing grades suggests a re-plan; confidence ratings change the plan
s, r = call("PATCH", "/api/subjects/physics", {"current_grade": 3, "target_grade": 7}); expect(s == 200 and r["replan_suggested"], "grade change suggests re-plan")
s, r = call("PUT", "/api/subjects/physics/topics/D.2", {"confidence": 1}); expect(s == 200, "confidence saved")
s, r = call("PUT", "/api/subjects/physics/topics/A.1", {"confidence": 5}); expect(s == 200, "confidence saved (5)")
s, rp = post("/api/plan/replan", {"keep_pinned": True}); tasks4, _, plan4 = all_tasks(today)
d2 = next((t for t in tasks4 if t["subject"] == "physics" and t["kind"] == "learn" and t["topic_code"] == "D.2"), None)
a2 = next((t for t in tasks4 if t["subject"] == "physics" and t["kind"] == "learn" and t["topic_code"] == "A.2"), None)
phys_learn = sorted((t for t in tasks4 if t["subject"] == "physics" and t["kind"] == "learn"), key=lambda t: t["date"])
expect(d2 is not None and a2 is not None and d2["minutes"] > a2["minutes"], "weak topic gets more time than an unrated one", (d2 and d2["minutes"], a2 and a2["minutes"]))
pos = [t["topic_code"] for t in phys_learn]
expect("D.2" in pos and pos.index("D.2") < pos.index("D.3"), "weak topic is pulled earlier than syllabus order", pos[:12])
h3 = sum(t["minutes"] for t in tasks4 if t["subject"] == "physics"); h_before = sum(t["minutes"] for t in tasks3 if t["subject"] == "physics")
expect(h3 > h_before, "a bigger grade gap gets more hours", (h_before, h3))
print("physics learn order:", pos[:14]); print("physics kinds:", dict(collections.Counter(t["kind"] for t in tasks4 if t["subject"] == "physics")))
print("ALL PASS" if ok else "SOME FAILED")
