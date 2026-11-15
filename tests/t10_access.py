"""FileBrowser access rules must apply everywhere in IB God, and changes must apply without a restart.

Usage: python3 -I tests/t10_access.py <scratch-filebrowser-dir>   (the dev copy must be started with that dir)
The scratch dir holds a copy of FileBrowser's database that this test edits; the real one is never touched.
"""
import json, sqlite3, sys, time
sys.path.insert(0, "tests")
from client import *
from t02_plan import SUBS, WEEK

FB = sys.argv[1]
HIDE = "/IB BOOKS/Group 4 - Sciences/Physics/"
ok = True
def expect(c, label, extra=""):
    global ok; print(("  PASS " if c else "  FAIL ") + label + (f"  [{extra}]" if extra and not c else "")); ok = ok and bool(c)

def fb(sql, params=()):
    c = sqlite3.connect(f"{FB}/database.sqlite"); c.execute(sql, params); c.commit(); c.close()

def rule(path, data):
    fb("DELETE FROM access_rules WHERE path=?", (path,))
    if data is not None:
        fb("INSERT INTO access_rules(source, path, rule_data) VALUES('/srv/docs', ?, ?)", (path, json.dumps(data)))

def wait_reload():
    time.sleep(32)  # IB God re-reads FileBrowser's data at most every 30 s

def physics_books_visible():
    s, r = get("/api/textbooks?subject=physics&level=HL")
    return [b["title"] for b in r["textbooks"]]

reset()
s, r = post("/api/setup", {"display_name": "Dev Tester", "session_month": "May", "session_year": 2027, "weekly_minutes": WEEK, "subjects": SUBS}); assert s == 200, r
before = physics_books_visible()
s, srch = get("/api/search?q=" + q("Tsokos")); tsokos = [x for x in srch["results"] if x["collection"] == "books" and "Physics" in x["folder"]]
expect(len(before) >= 3 and tsokos, "baseline: physics textbooks visible", (len(before), len(tsokos)))
book_id = tsokos[0]["id"]
s, h, _ = call("GET", f"/api/files/{book_id}/open", raw=True); expect(s == 200, "baseline: book opens", s)

# 1. deny everyone except admin (same shape as the real /Shaffy/ rule)
rule(HIDE, {"denyAll": True, "Deny": {"Users": {}, "Groups": {}}, "Allow": {"Users": {"admin": {}}, "Groups": {}}})
wait_reload()
expect(physics_books_visible() == [], "hidden folder: textbook picker is empty", physics_books_visible()[:2])
s, srch = get("/api/search?q=" + q("Tsokos")); expect(not [x for x in srch["results"] if "Physics" in x["folder"] and x["collection"] == "books"], "hidden folder: search finds nothing in it")
s, srch = get("/api/search?q=" + q("doppler effect") + "&subject=physics&collection=books"); expect(not [x for x in srch["results"] if x["folder"].startswith(HIDE.strip("/"))], "hidden folder: full-text page hits are gone")
s, h, _ = call("GET", f"/api/files/{book_id}/open", raw=True); expect(s == 404, "hidden folder: direct file link refused", s)
s, rr = get(f"/api/resources?ids={book_id}"); expect(rr["resources"] == [], "hidden folder: lookup by id returns nothing")
s, tr = get("/api/subjects/physics/topics/C.5/resources"); expect(not [x for x in tr.get("textbook", []) if x["folder"].startswith(HIDE.strip("/"))], "hidden folder: topic textbook pages are gone")
s, d = get("/api/subjects/physics"); expect(not d["overview"]["textbooks"], "hidden folder: subject resources tab empty")
s, p = post(f"/api/resources/{book_id}/mark", {"status": "saved"}); expect(s == 404, "hidden folder: cannot bookmark it", s)
s, p = call("PATCH", "/api/subjects/physics", {"textbook_id": book_id}); expect(s == 422, "hidden folder: cannot pick it as my textbook", s)
s, p = get("/api/subjects/math_aa/papers"); expect(len(p["papers"]) > 10, "other folders unaffected (maths papers)", len(p["papers"]))

# 2. the same rule but this user explicitly allowed
rule(HIDE, {"denyAll": True, "Deny": {"Users": {}, "Groups": {}}, "Allow": {"Users": {"admin": {}, "devtest": {}}, "Groups": {}}})
wait_reload()
expect(len(physics_books_visible()) == len(before), "allowed by name: books back without restart")

# 3. allowed through a FileBrowser group
rule(HIDE, {"denyAll": True, "Deny": {"Users": {}, "Groups": {}}, "Allow": {"Users": {}, "Groups": {"physics-class": {}}}})
fb("DELETE FROM groups WHERE name='physics-class'"); fb("INSERT INTO groups(name, members) VALUES('physics-class', ?)", (json.dumps(["devtest"]),))
wait_reload()
expect(len(physics_books_visible()) == len(before), "allowed through a FileBrowser group")

# 4. a sub-folder exception: deny the whole Sciences folder but allow Physics inside it
rule(HIDE, None); fb("DELETE FROM groups WHERE name='physics-class'")
rule("/IB BOOKS/Group 4 - Sciences/", {"denyAll": True, "Deny": {"Users": {}, "Groups": {}}, "Allow": {"Users": {}, "Groups": {}}})
rule(HIDE, {"denyAll": False, "Deny": {"Users": {}, "Groups": {}}, "Allow": {"Users": {"devtest": {}}, "Groups": {}}})
wait_reload()
s, r = get("/api/textbooks?subject=chemistry&level=HL")
expect(len(physics_books_visible()) == len(before) and r["textbooks"] == [], "most specific rule wins (Physics allowed, Chemistry hidden)", (len(physics_books_visible()), len(r["textbooks"])))
rule("/IB BOOKS/Group 4 - Sciences/", None); rule(HIDE, None)

# 5. explicit Deny for this user only
rule(HIDE, {"denyAll": False, "Deny": {"Users": {"devtest": {}}, "Groups": {}}, "Allow": {"Users": {}, "Groups": {}}})
wait_reload()
expect(physics_books_visible() == [], "denied by name")
rule(HIDE, None)

# 6. scope: user limited to one folder
fb("UPDATE users SET user_data=json_set(user_data, '$.backendScopes[0].scope', '/IB PAST PAPERS - YEAR') WHERE username='devtest'")
wait_reload()
s, srch = get("/api/search?q=" + q("grade boundaries"))
outside = [x["folder"] for x in srch["results"] if not x["folder"].startswith("IB PAST PAPERS - YEAR")]
expect(physics_books_visible() == [] and not outside, "scope limited to past papers: nothing outside it is shown", outside[:2])
s, p = get("/api/subjects/physics/papers"); expect(len(p["papers"]) > 10, "scope limited to past papers: papers still there", len(p["papers"]))
s, rp = post("/api/plan/replan", {"keep_pinned": True}); expect(s == 200, "planner works with a scope")

# 7. no view permission at all
fb("UPDATE users SET user_data=json_set(user_data, '$.backendScopes[0].scope', '/', '$.backendScopes[0].permissions.view', json('false')) WHERE username='devtest'")
wait_reload()
s, srch = get("/api/search?q=" + q("doppler")); s2, p = get("/api/subjects/physics/papers")
expect(not srch["results"] and not p["papers"], "no view permission: library empty", (len(srch["results"]), len(p["papers"])))
s, a = get("/api/apps"); expect(s == 200 and not [x for x in a["apps"] if x["key"] == "files"], "no view permission: Files app hidden")

# 8. restore
fb("UPDATE users SET user_data=json_set(user_data, '$.backendScopes[0].permissions.view', json('true')) WHERE username='devtest'")
wait_reload()
expect(len(physics_books_visible()) == len(before), "restored: everything back")
reset()
print("ALL PASS" if ok else "SOME FAILED")
