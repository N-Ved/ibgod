"""Feedback-writer quality: real exemplars from the drive plus a deliberately weak draft. Prints timing and the full feedback."""
import sys, subprocess, time, json
sys.path.insert(0, "tests")
from client import *

ROOT = "/mnt/files/docs/"
WEAK = ("""Investigating how temperature affects how fast sugar dissolves.

Introduction. I chose this topic because I like tea and I always wondered why sugar dissolves faster in hot tea. Sugar is a substance that dissolves in water. My research question is does temperature change dissolving.

Method. I put some sugar in water at different temperatures and timed how long it took to dissolve using my phone. I used cold water, warm water and hot water. I stirred it a bit each time. I did it once for each temperature.

Results. Cold water took 95 seconds. Warm water took 50 seconds. Hot water took 20 seconds. So hot water is the fastest.

Conclusion. My hypothesis was right and temperature makes sugar dissolve faster. This is because particles move faster when hot. The experiment went well and there were no problems. If I did it again I would use more sugar. Overall I learned a lot about dissolving and I think my results are very accurate and reliable because the pattern is clear. """ * 1).strip()

def pdf_text(rel, max_words=6000):
    out = subprocess.run(["pdftotext", "-enc", "UTF-8", "-q", ROOT + rel, "-"], capture_output=True, timeout=120).stdout.decode("utf-8", "replace")
    return " ".join(out.split()[:max_words]) if max_words else out

def run(rubric, title, text):
    t0 = time.time()
    s, r = post("/api/feedback/jobs", {"rubric": rubric, "title": title, "text": text})
    if s != 200: print("SUBMIT FAILED", s, r); return
    jid = r["id"]; last = None
    while True:
        s, j = get(f"/api/feedback/jobs/{jid}")
        if j["progress"] != last and j["progress"]: last = j["progress"]; print(f"   [{time.time()-t0:5.0f}s] {last}", flush=True)
        if j["status"] in ("done", "error"): break
        time.sleep(5)
    res = j["result"]
    print("=" * 110); print(f"{title} | {rubric} | {j['words']} words | {time.time()-t0:.0f} s | status {j['status']} | ai={res.get('ai')} truncated={res.get('truncated')}")
    print("PRIORITIES:"); [print("   -", p) for p in res.get("priorities", [])]
    print("CHECKS:"); [print(f"   [{c['status']}] {c['title']}: {c['detail'][:120]}") for c in res.get("checks", [])]
    for c in res.get("criteria", []):
        print(f"--- {c['code']} {c['name']} [{c.get('level')}]" + (f"  ERROR {c['error']}" if c.get("error") else ""))
        for x in c.get("strengths", []): print("   +", x)
        for x in c.get("improvements", []): print("   >", x)
        if c.get("evidence"): print("   “" + c["evidence"] + "”")

which = sys.argv[1] if len(sys.argv) > 1 else "all"
reset()
if which in ("all", "weak"): run("science_ia", "Weak chemistry IA draft", WEAK * 1 + "\n\n" + WEAK.replace("sugar", "salt"))
if which in ("all", "ia"): run("science_ia", "Physics IA exemplar (Clastify)", pdf_text("IB OFFICIAL EE EXEMPLARS/Clastify IA EXEMPLARS/Physics - The relationship between magnetic field on a magnet and its levitation distance.pdf", 3200))
if which in ("all", "tok"): run("tok_essay", "TOK essay exemplar A", pdf_text("theoryofknowledge.net/TOK Essay Exemplars/Tok_essay_A_en.pdf", 1700))
