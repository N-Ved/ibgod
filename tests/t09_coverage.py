"""Master checklist and clear-plan: covered topics must not be re-taught, and each level must schedule what it promises."""
import sys, collections, datetime
sys.path.insert(0, "tests")
from client import *
from t02_plan import all_tasks, SUBS, WEEK

ok = True
def expect(c, label, extra=""):
    global ok; print(("  PASS " if c else "  FAIL ") + label + (f"  [{extra}]" if extra and not c else "")); ok = ok and bool(c)

def kinds(tasks, subject, code):
    return sorted(t["kind"] for t in tasks if t["subject"] == subject and t["topic_code"] == code)

reset()
s, r = post("/api/setup", {"display_name": "Dev Tester", "session_month": "May", "session_year": 2027, "weekly_minutes": WEEK, "subjects": SUBS}); assert s == 200
s, me = get("/api/me"); today = me["today"]
tasks0, _, plan0 = all_tasks(today)
base_hours = sum(t["minutes"] for t in tasks0 if t["subject"] == "physics")
print("baseline physics hours:", base_hours / 60, "learn tasks:", sum(1 for t in tasks0 if t["subject"] == "physics" and t["kind"] == "learn"))
expect(kinds(tasks0, "physics", "A.1").count("learn") == 1, "level 0 topic gets a Learn task")

# one topic at each level
for code, lvl in (("A.2", 1), ("A.3", 2), ("B.1", 3), ("B.2", 4)):
    s, r = call("PUT", f"/api/subjects/physics/topics/{code}", {"coverage": lvl}); expect(s == 200, f"set {code} to level {lvl}")
s, r = call("PUT", "/api/subjects/physics/topics/A.1", {"coverage": 9}); expect(s == 422, "level 9 rejected", s)
s, r = call("PUT", "/api/subjects/physics/topics/ZZ", {"coverage": 2}); expect(s == 404, "unknown topic rejected", s)
s, d = get("/api/subjects/physics"); lv = {t["code"]: t["coverage"] for u in d["units"] for t in u["topics"]}
expect(lv["A.2"] == 1 and lv["B.2"] == 4 and lv["A.1"] == 0, "subject page returns the levels", {k: lv[k] for k in ("A.1", "A.2", "B.2")})
s, rp = post("/api/plan/replan", {"keep_pinned": True}); expect(s == 200 and rp["summary"]["subjects"]["physics"]["covered"] == 2, "summary counts covered topics", rp["summary"]["subjects"]["physics"].get("covered"))
tasks1, _, plan1 = all_tasks(today)
k = {c: kinds(tasks1, "physics", c) for c in ("A.1", "A.2", "A.3", "B.1", "B.2")}
print("   per-topic tasks:", k)
expect("learn" in k["A.1"] and "practice" in k["A.1"], "level 0: learn + practise")
expect(k["A.2"].count("learn") == 1 and "practice" in k["A.2"], "level 1: shorter consolidation + practise")
l_a1 = next(t for t in tasks1 if t["subject"] == "physics" and t["topic_code"] == "A.1" and t["kind"] == "learn")
l_a2 = next(t for t in tasks1 if t["subject"] == "physics" and t["topic_code"] == "A.2" and t["kind"] == "learn")
expect(l_a2["title"].startswith("Consolidate") and l_a2["minutes"] < l_a1["minutes"], "level 1 is titled Consolidate and shorter", (l_a1["minutes"], l_a2["minutes"]))
expect("learn" not in k["A.3"] and "practice" in k["A.3"] and "review" in k["A.3"], "level 2: no learn, practice + reviews")
expect(k["B.1"] and set(k["B.1"]) == {"review"}, "level 3: reviews only")
expect(k["B.2"] == ["review"], "level 4: exactly one maintenance review", k["B.2"])
rev3 = [t for t in tasks1 if t["subject"] == "physics" and t["topic_code"] == "B.1" and t["kind"] == "review"]
expect(len(rev3) >= 2, "level 3 keeps several spaced reviews", len(rev3))
expect(min(t["date"] for t in rev3) <= (datetime.date.fromisoformat(today) + datetime.timedelta(days=45)).isoformat(), "reviews of covered topics start early", min(t["date"] for t in rev3))
r4 = next(t for t in tasks1 if t["subject"] == "physics" and t["topic_code"] == "B.2" and t["kind"] == "review")
expect(r4["n"] == max(t["n"] or 0 for t in tasks1 if t["subject"] == "physics" and t["kind"] == "review"), "maintenance review is the widest-spaced round")
expect(len(plan1["issues"]) == 0, "plan with a checklist has no issues", [i["ident"] for i in plan1["issues"]])

# bulk: unit and whole subject
s, r = call("PUT", "/api/subjects/physics/coverage", {"level": 3, "unit": "A"}); expect(s == 200 and r["topics"] == 5, "bulk set a unit", r)
s, r = call("PUT", "/api/subjects/physics/coverage", {"level": 3, "unit": "nope"}); expect(s == 404, "bulk unknown unit rejected", s)
s, r = call("PUT", "/api/subjects/physics/coverage", {"level": 7}); expect(s == 422, "bulk bad level rejected", s)
s, r = call("PUT", "/api/subjects/biology/coverage", {"level": 3}); expect(s == 404, "bulk on a subject you do not take rejected", s)
s, r = call("PUT", "/api/subjects/physics/coverage", {"level": 4}); expect(s == 200, "bulk whole subject to Secure")
s, rp = post("/api/plan/replan", {"keep_pinned": True}); tasks2, _, plan2 = all_tasks(today)
ph = [t for t in tasks2 if t["subject"] == "physics"]
cnt = collections.Counter(t["kind"] for t in ph)
print("   everything secure ->", dict(cnt), "hours", sum(t["minutes"] for t in ph) / 60)
expect(cnt["learn"] == 0 and cnt["practice"] == 0, "all-secure subject has no learn/practice")
expect(cnt["review"] >= 20 and cnt["paper"] >= 2, "all-secure subject still gets maintenance reviews and papers")
expect(sum(t["minutes"] for t in ph) <= base_hours * 1.15, "time not inflated beyond the budget", (base_hours, sum(t["minutes"] for t in ph)))
others = sum(t["minutes"] for t in tasks2 if t["subject"] != "physics"); others0 = sum(t["minutes"] for t in tasks0 if t["subject"] != "physics")
expect(len(plan2["issues"]) <= 1, "all-secure plan has no real issues", [i["ident"] for i in plan2["issues"]])

# completing work moves the checklist up and never down
call("PUT", "/api/subjects/chemistry/coverage", {"level": 0})
tasks3, _, _ = all_tasks(today)
learn = next(t for t in tasks3 if t["subject"] == "chemistry" and t["kind"] == "learn")
call("PATCH", f"/api/tasks/{learn['id']}", {"status": "done", "rating": "ok"})
s, d = get("/api/subjects/chemistry"); lv = {t["code"]: t["coverage"] for u in d["units"] for t in u["topics"]}
expect(lv[learn["topic_code"]] == 2, "finishing a Learn session marks the topic Familiar", lv[learn["topic_code"]])
prac = next(t for t in tasks3 if t["subject"] == "chemistry" and t["kind"] == "practice" and t["topic_code"] == learn["topic_code"])
call("PATCH", f"/api/tasks/{prac['id']}", {"status": "done", "rating": "ok"})
s, d = get("/api/subjects/chemistry"); lv = {t["code"]: t["coverage"] for u in d["units"] for t in u["topics"]}
expect(lv[learn["topic_code"]] == 3, "finishing Practise marks it Revised", lv[learn["topic_code"]])
call("PUT", f"/api/subjects/chemistry/topics/{learn['topic_code']}", {"coverage": 4}); call("PATCH", f"/api/tasks/{learn['id']}", {"status": "todo"}); call("PATCH", f"/api/tasks/{learn['id']}", {"status": "done"})
s, d = get("/api/subjects/chemistry"); lv = {t["code"]: t["coverage"] for u in d["units"] for t in u["topics"]}
expect(lv[learn["topic_code"]] == 4, "completing work never lowers the level", lv[learn["topic_code"]])

# clear plan
call("PUT", "/api/subjects/physics/topics/A.1", {"confidence": 2})
s, r = post("/api/plan/clear", {"reset_topics": False}); expect(s == 200 and r["removed"] > 100, "clear plan removes the sessions", r.get("removed"))
tasks4, _, plan4 = all_tasks(today)
expect(len(tasks4) == 0 and plan4["span"]["todo"] == 0, "no sessions remain after clearing")
s, me = get("/api/me"); expect(len(me["subjects"]) == 6 and me["onboarded"], "subjects and setup are kept")
s, d = get("/api/subjects/chemistry"); lv = {t["code"]: t["coverage"] for u in d["units"] for t in u["topics"]}
expect(lv[learn["topic_code"]] == 4, "checklist is kept when only the plan is cleared")
s, dash = get("/api/dashboard"); expect(s == 200 and dash["stats"]["total"]["planned"] == 0 and dash["stats"]["streak"] == 0, "dashboard shows a clean slate")
s, rp = post("/api/plan/replan", {"keep_pinned": True}); tasks5, _, plan5 = all_tasks(today)
expect(len(tasks5) > 100, "a new plan can be built after clearing", len(tasks5))
expect(not any(t["subject"] == "chemistry" and t["topic_code"] == learn["topic_code"] and t["kind"] in ("learn", "practice") for t in tasks5), "the rebuilt plan does not re-teach the covered topic")
s, r = post("/api/plan/clear", {"reset_topics": True}); expect(s == 200, "clear with checklist reset")
s, d = get("/api/subjects/chemistry"); lv = {t["code"]: t["coverage"] for u in d["units"] for t in u["topics"]}
expect(set(lv.values()) == {0}, "reset puts every topic back to Not started")
s, r = post("/api/plan/clear", {"reset_topics": False}); expect(s == 200 and r["removed"] == 0, "clearing an empty plan is harmless")
print("ALL PASS" if ok else "SOME FAILED")
