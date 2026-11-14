import sys, json, collections
sys.path.insert(0, "tests")
from client import *

s, me = get("/api/me"); print("me", s, me["username"], "onboarded", me["onboarded"], "llm", me["llm"], "index", me["index"])
# CSRF checks
s, r = call("POST", "/api/plan/replan", {"keep_pinned": True}, headers={"X-IBGod": None}); print("no marker ->", s, r)
s, r = call("POST", "/api/plan/replan", {"keep_pinned": True}, headers={"Origin": "https://view.n-ved.com"}); print("foreign origin ->", s, r)
s, r = call("POST", "/api/plan/replan", {"keep_pinned": True}, headers={"Sec-Fetch-Site": "same-site"}); print("same-site ->", s, r)
s, cat = get("/api/catalog"); print("catalog", s, len(cat["subjects"]), "subjects; top by resources:", [(x["short"], x["resources"]) for x in sorted(cat["subjects"], key=lambda x: -x["resources"])[:8]])
s, tb = get("/api/textbooks?subject=physics&level=HL"); print("physics textbooks", s, len(tb["textbooks"])); [print("   ", t["id"], t["title"][:80], t["syllabus"]) for t in tb["textbooks"][:6]]
book = next((t["id"] for t in tb["textbooks"] if "Tsokos" in t["title"] and "2023" in t["title"]), None)
body = {"display_name": "Dev Tester", "session_month": "May", "session_year": 2027, "weekly_minutes": [90, 90, 90, 90, 60, 180, 120],
        "subjects": [
            {"subject": "physics", "level": "HL", "current_grade": 5, "target_grade": 7, "textbook_id": book},
            {"subject": "math_aa", "level": "HL", "current_grade": 4, "target_grade": 6},
            {"subject": "chemistry", "level": "HL", "current_grade": 5, "target_grade": 6},
            {"subject": "economics", "level": "SL", "current_grade": 6, "target_grade": 7},
            {"subject": "lang_a_ll:English", "level": "SL", "current_grade": 5, "target_grade": 6},
            {"subject": "lang_b:Spanish", "level": "SL", "current_grade": 6, "target_grade": 7}]}
s, r = post("/api/setup", body); print("setup", s, (r if s != 200 else {"tasks": r["plan"]["tasks"], "issues": len(r["issues"]["issues"])}))
if s == 200:
    for k, v in r["plan"]["subjects"].items(): print("   ", k, v)
    for i in r["issues"]["issues"][:12]: print("   ISSUE", i["severity"], i["title"], "|", i["detail"][:110])
