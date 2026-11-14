"""Coach quality: realistic student questions, streamed from the local model. Prints timing, sources and the full answer for review."""
import sys, json, time, urllib.request
sys.path.insert(0, "tests")
from client import *
from t02_plan import SUBS, WEEK

def ask(chat_id, text):
    req = urllib.request.Request(BASE + f"/api/coach/chats/{chat_id}/messages", data=json.dumps({"message": text}).encode(), method="POST",
                                 headers={"X-IBGod": "1", "Content-Type": "application/json", "Accept": "text/event-stream"})
    t0 = time.time(); first = None; out = []; sources = []; ev = None; done = None
    with urllib.request.urlopen(req, timeout=900) as r:
        for raw in r:
            line = raw.decode().rstrip("\n")
            if line.startswith("event:"): ev = line[6:].strip()
            elif line.startswith("data:"):
                d = json.loads(line[5:])
                if ev == "sources": sources = d["sources"]
                elif ev == "token":
                    first = first or time.time() - t0; out.append(d["text"])
                elif ev == "done": done = d
                elif ev == "error": out.append("[ERROR] " + d["detail"])
    return "".join(out), sources, first, time.time() - t0, done

if __name__ == "__main__":
    reset()
    s, r = post("/api/setup", {"display_name": "Dev Tester", "session_month": "May", "session_year": 2027, "weekly_minutes": WEEK, "subjects": SUBS}); assert s == 200
    questions = sys.argv[1:] or [
        "I keep forgetting what I revise. What should I change?",
        "How do I move from a 5 to a 7 in Physics HL? Be specific about what to do each week.",
        "Explain Le Chatelier's principle and give me a way to test myself on it.",
        "Can you write my Economics IA commentary for me? It's due tomorrow.",
    ]
    s, c = post("/api/coach/chats"); cid = c["id"]
    for qn in questions:
        text, sources, first, total, done = ask(cid, qn)
        print("=" * 100); print("Q:", qn)
        print(f"   first token {first and round(first,1)} s, total {total:.0f} s, {len(text.split())} words | sources: {[(x['type'], x['title'][:40], x.get('page')) for x in sources]}")
        print(text)
