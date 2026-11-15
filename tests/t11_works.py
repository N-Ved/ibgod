"""My works (language subjects): uploads, type checks, privacy, checklist + planner integration, study guides, cleanup."""
import io, json, subprocess, sys, zipfile, urllib.request, urllib.parse
sys.path.insert(0, "tests")
import client
from client import *

OTHER = "http://127.0.0.1:18082"  # second test copy signed in as another user
ok = True
def expect(c, label, extra=""):
    global ok; print(("  PASS " if c else "  FAIL ") + label + (f"  [{extra}]" if extra and not c else "")); ok = ok and bool(c)

def upload(path, data, method="POST", base=None):
    req = urllib.request.Request((base or BASE) + path, data=data, method=method, headers={"X-IBGod": "1", "Content-Type": "application/octet-stream"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b"{}")

def zipped(files):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for n, c in files: z.writestr(n, c)
    return b.getvalue()

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
EPUB = zipped([("mimetype", "application/epub+zip"), ("OEBPS/c.xhtml", "<html/>")])
DOCX = zipped([("[Content_Types].xml", "<x/>"), ("word/document.xml", "<w:document/>")])
TXT = "Shall I compare thee to a summer's day?\n".encode()
def W(title, author="", kind="novel", part="paper2", subject="lang_a_ll:English", filename=None):
    q = urllib.parse.urlencode({k: v for k, v in dict(title=title, author=author, kind=kind, part=part, filename=filename or "").items()})
    return f"/api/subjects/{urllib.parse.quote(subject, safe='')}/works?{q}"

reset()
s, r = post("/api/setup", {"display_name": "Dev Tester", "session_month": "May", "session_year": 2027, "weekly_minutes": [90, 90, 90, 90, 0, 180, 180],
    "subjects": [{"subject": "lang_a_ll:English", "level": "HL", "current_grade": 5, "target_grade": 7}, {"subject": "lang_b:Spanish", "level": "SL", "current_grade": 5, "target_grade": 6},
                 {"subject": "physics", "level": "HL", "current_grade": 5, "target_grade": 6}]}); assert s == 200, r
s, d = get("/api/subjects/" + q("lang_a_ll:English")); expect(d["works_supported"] is True, "English A supports works")
s, d = get("/api/subjects/physics"); expect(d["works_supported"] is False, "Physics does not")

# add works
s, a = upload(W("The Great Gatsby", "F. Scott Fitzgerald", filename="gatsby.pdf"), PDF); expect(s == 200 and a["work"]["file_ext"] == "pdf", "add a work with a PDF", (s, a))
gatsby = a["work"]
expect(any("Gatsby" in g["title"] for g in gatsby["guides"]), "matched to the LitCharts guide on the drive", [g["title"] for g in gatsby["guides"]])
s, b = upload(W("Hamlet", "William Shakespeare", kind="drama", part="oral"), b""); expect(s == 200 and b["work"]["file_url"] is None, "add a work without a file")
hamlet = b["work"]
expect(all("Hamlet" in g["title"] for g in hamlet["guides"]), "guide matching is not loose", [g["title"] for g in hamlet["guides"]])
s, c = upload(W("Sonnets", kind="poetry", filename="sonnets.txt"), TXT); expect(s == 200 and c["work"]["file_ext"] == "txt", "plain text accepted")
s, e = upload(W("Novel E", filename="n.epub"), EPUB); expect(s == 200 and e["work"]["file_ext"] == "epub", "EPUB accepted")
s, f = upload(W("Essay F", kind="nonfiction", filename="f.docx"), DOCX); expect(s == 200 and f["work"]["file_ext"] == "docx", "Word document accepted")
s, x = upload(W("Novela", subject="lang_b:Spanish", part="class"), b""); expect(s == 200, "works also for Language B")

# refusals
s, r = upload(W("Bad", filename="evil.pdf"), b"MZ\x90\x00\x03" + b"\x00" * 100); expect(s == 415, "a program renamed to .pdf is refused", s)
s, r = upload(W("Zip", filename="x.epub"), zipped([("a.txt", "x")])); expect(s == 415, "a plain zip renamed to .epub is refused", s)
s, r = upload(W("Big", filename="big.pdf"), b"%PDF-1.4\n" + b"0" * (25 * 1024 * 1024)); expect(s == 413, "files over the size limit are refused", s)
s, r = upload(W("", filename="a.pdf"), PDF); expect(s == 422, "a title is required", s)
s, r = upload(W("T", kind="weird"), b""); expect(s == 422, "unknown form refused", s)
s, r = upload(W("T", subject="physics"), b""); expect(s == 404, "no works on non-language subjects", s)
s, r = upload(W("T", subject="biology"), b""); expect(s == 404, "no works on subjects you do not take", s)

# serving
s, h, body = call("GET", gatsby["file_url"], raw=True)
expect(s == 200 and h.get("content-type", "").startswith("application/pdf") and "sandbox" in h.get("content-security-policy", "") and body == PDF, "PDF opens inline, sandboxed, unchanged")
s, h, body = call("GET", c["work"]["file_url"], raw=True); expect(h.get("content-type", "").startswith("text/plain") and "inline" in h.get("content-disposition", ""), "text opens inline as plain text")
s, h, body = call("GET", e["work"]["file_url"], raw=True); expect("attachment" in h.get("content-disposition", ""), "EPUB is a download")
s, h, body = call("GET", f"/api/works/{hamlet['id']}/file", raw=True); expect(s == 404, "no file -> not found")

# privacy: another signed-in user
s, h, body = call("GET", gatsby["file_url"], raw=True, headers=None) if False else (None, None, None)
req = urllib.request.Request(OTHER + gatsby["file_url"], headers={"X-IBGod": "1"})
try: code = urllib.request.urlopen(req, timeout=20).status
except urllib.error.HTTPError as err: code = err.code
expect(code == 404, "another user cannot open your file", code)
s2, r2 = upload(f"/api/works/{gatsby['id']}", json.dumps({"title": "x"}).encode(), method="PATCH", base=OTHER); expect(s2 in (404, 422), "another user cannot edit your work", s2)
req = urllib.request.Request(OTHER + f"/api/works/{gatsby['id']}", method="DELETE", headers={"X-IBGod": "1"})
try: code = urllib.request.urlopen(req, timeout=20).status
except urllib.error.HTTPError as err: code = err.code
expect(code == 404, "another user cannot delete your work", code)

# edit, replace file
s, r = call("PATCH", f"/api/works/{hamlet['id']}", {"notes": "To be or not to be", "part": "paper2"}); expect(s == 200 and r["work"]["notes"] == "To be or not to be", "edit notes and part")
s, r = upload(f"/api/works/{hamlet['id']}/file?filename=hamlet.pdf", PDF, method="PUT"); expect(s == 200 and r["work"]["file_ext"] == "pdf", "attach a copy later")
s, r = upload(f"/api/works/{hamlet['id']}/file?filename=hamlet.txt", TXT, method="PUT"); expect(s == 200 and r["work"]["file_ext"] == "txt", "replace the copy")

# checklist + planner
s, d = get("/api/subjects/" + q("lang_a_ll:English"))
wk = next((u for u in d["units"] if u["code"] == "WK"), None)
expect(wk and {t["code"] for t in wk["topics"]} >= {f"W{gatsby['id']}", f"W{hamlet['id']}"}, "works appear in the checklist")
s, r = call("PUT", "/api/subjects/" + q("lang_a_ll:English") + f"/topics/W{hamlet['id']}", {"coverage": 3}); expect(s == 200, "set a work to Revised")
s, r = call("PUT", "/api/subjects/" + q("lang_a_ll:English") + f"/topics/W{x['work']['id']}", {"coverage": 3}); expect(s == 404, "a Spanish work is not an English topic", s)
s, rp = post("/api/plan/replan", {"keep_pinned": True}); expect(s == 200, "re-plan")
from t02_plan import all_tasks
s, me = get("/api/me"); tasks, _, plan = all_tasks(me["today"])
gt = [t for t in tasks if t["topic_code"] == f"W{gatsby['id']}"]; ht = [t for t in tasks if t["topic_code"] == f"W{hamlet['id']}"]
print("   gatsby tasks:", sorted({t["title"].split(":")[0] for t in gt}), "| hamlet tasks:", sorted({t["title"].split(":")[0] for t in ht}))
expect(any(t["title"].startswith("Read and annotate: The Great Gatsby") for t in gt) and any(t["title"].startswith("Write about: The Great Gatsby") for t in gt), "plan reads, then writes about, a new work")
expect(ht and all(t["kind"] == "review" for t in ht), "a revised work only gets reviews")
expect(len(plan["issues"]) == 0, "plan has no issues", [i["ident"] for i in plan["issues"]])
s, tr = get("/api/subjects/" + q("lang_a_ll:English") + f"/topics/W{gatsby['id']}/resources")
expect(tr["yours"] and tr["yours"][0]["url"] == gatsby["file_url"] and tr["notes"], "a work's task shows your copy and the study guide")

# delete
stored = subprocess.run(["docker", "exec", "ibgod-dev", "sh", "-c", "ls /data/works/*/ | wc -l"], capture_output=True, text=True).stdout.strip()
s, r = call("DELETE", f"/api/works/{gatsby['id']}"); expect(s == 200, "remove a work")
after = subprocess.run(["docker", "exec", "ibgod-dev", "sh", "-c", "ls /data/works/*/ | wc -l"], capture_output=True, text=True).stdout.strip()
expect(int(after) == int(stored) - 1, "its file is deleted from disk", (stored, after))
tasks2, _, _ = all_tasks(me["today"]); expect(not [t for t in tasks2 if t["topic_code"] == f"W{gatsby['id']}" and t["status"] == "todo"], "its planned sessions are removed")
s, r = get(f"/api/works/{gatsby['id']}/file"); expect(s == 404, "its link no longer works")

# limit on number of works
n = len(get("/api/subjects/" + q("lang_a_ll:English") + "/works")[1]["works"]) + 1
codes = [upload(W(f"Extra {i}"), b"")[0] for i in range(41 - n)]
expect(codes[-1] == 422 and all(c == 200 for c in codes[:-1]), "at most 40 works", codes[-3:])

# account deletion removes files
s, r = post("/api/account/delete", {"confirm": "DELETE"})
left = subprocess.run(["docker", "exec", "ibgod-dev", "sh", "-c", "ls /data/works/ 2>/dev/null | wc -l"], capture_output=True, text=True).stdout.strip()
expect(s == 200 and left == "0", "deleting the account deletes the uploaded files", left)
print("ALL PASS" if ok else "SOME FAILED")
