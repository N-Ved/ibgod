"""Does the feedback writer's judgement track real examiner marks? TOK essays with known marks from the drive."""
import sys, subprocess, time
sys.path.insert(0, "tests")
from client import *
ROOT = "/mnt/files/docs/theoryofknowledge.net/TOK Essay Exemplars/"
SETS = [("B", 3), ("E", 5), ("F", 8), ("D", 10)]
reset()
rows = []
for letter, mark in SETS:
    name = "Tok_essay_%s_en.pdf" % letter if letter == "A" else "tok_essay_%s_en.pdf" % letter
    text = subprocess.run(["pdftotext", "-enc", "UTF-8", "-q", ROOT + name, "-"], capture_output=True, timeout=120).stdout.decode("utf-8", "replace")
    t0 = time.time()
    s, r = post("/api/feedback/jobs", {"rubric": "tok_essay", "title": f"TOK exemplar {letter}", "text": text})
    if s != 200: print("submit failed", s, r); continue
    while True:
        s, j = get(f"/api/feedback/jobs/{r['id']}")
        if j["status"] in ("done", "error"): break
        time.sleep(5)
    res = j["result"]; c = (res.get("criteria") or [{}])[0]
    rows.append((letter, mark, c.get("level"), round(time.time() - t0)))
    print(f"=== Essay {letter}: examiner {mark}/10 → model level: {c.get('level')}  ({time.time()-t0:.0f} s, {j['words']} words)", flush=True)
    for x in c.get("strengths", []): print("   +", x[:230])
    for x in c.get("improvements", []): print("   >", x[:230])
    print("   evidence:", c.get("evidence")); print("   priorities:", res.get("priorities")); print("   checks:", [(k["status"], k["title"]) for k in res.get("checks", [])], flush=True)
print("SUMMARY (examiner mark → model level):", [(l, m, lv) for l, m, lv, _ in rows])
