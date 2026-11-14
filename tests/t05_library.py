"""Library quality: what does the app actually hand a student for a topic, a search, a past-paper list?"""
import sys, collections
sys.path.insert(0, "tests")
from client import *

def show(label, items, n=4):
    print(f"   {label}: " + (" || ".join(f"{r['title'][:62]}{' p.' + str(r['page']) if r.get('page') else ''}{' [legacy]' if r.get('syllabus') == 'legacy' else ''}" for r in items[:n]) if items else "—"))

print("##### TOPIC RESOURCES")
for subj, code in [("physics", "C.5"), ("physics", "B.3"), ("physics", "A.4"), ("chemistry", "R3.1"), ("chemistry", "S2.2"), ("math_aa", "5.2"), ("math_aa", "1.5"), ("economics", "2.8"), ("economics", "4.5"),
                   ("lang_b:Spanish", "SK.1"), ("lang_a_ll:English", "P1.2")]:
    s, r = get(f"/api/subjects/{q(subj)}/topics/{q(code)}/resources")
    if s != 200: print(subj, code, "->", s, r); continue
    print(f"== {subj} {code}")
    for k in ("notes", "textbook", "videos", "questions", "pages"): show(k, r.get(k) or [])

print("\n##### SUBJECT PAGE"); s, d = get("/api/subjects/physics")
print(s, d["subject"]["name"], "| units:", len(d["units"]), "| assessment:", [(c["name"], c["weight"]) for c in d["assessment"]], "| textbook:", (d["textbook"] or {}).get("title"))
print("   path steps:", [(x["from"], x["to"], x["title"]) for x in d["path"]["steps"]], "| split:", d["path"]["time_split"]); print("   next:", d["path"]["next_actions"])
print("   overview counts:", {k: len(v) for k, v in d["overview"].items() if isinstance(v, list)})
for k in ("guides", "booklets", "question_banks", "revision_guides"): show(k, d["overview"][k], 3)

print("\n##### PAST PAPERS")
for subj in ("physics", "math_aa", "economics", "lang_b:Spanish"):
    s, r = get(f"/api/subjects/{q(subj)}/papers"); ps = r["papers"]
    qp = [p for p in ps if p["kind"] == "question_paper"]
    print(f"== {subj}: {len(ps)} files, {len(qp)} question papers, with markscheme {sum(1 for p in qp if p['pair_id'])}, current {sum(1 for p in qp if p['syllabus'] != 'legacy')}, years {sorted({p['year'] for p in qp if p['year']})[:1]}–{sorted({p['year'] for p in qp if p['year']})[-1:]}")
    for p in ps[:5]: print("    ", p["title"], "| ms:", bool(p["pair_id"]), "|", p["syllabus"], "|", p["lang"])

print("\n##### SEARCH")
for query, extra in [("doppler effect", "&subject=physics"), ("market failure externalities", "&subject=economics"), ("integration by parts", ""), ("le chatelier", ""), ("May 2023 physics paper 2", ""),
                     ("grade boundaries", ""), ("Tsokos", ""), ("extended essay reflection", ""), ("photosynthesis limiting factors", "&collection=notes"), ("", "&collection=videos"),
                     ("\" OR 1=1 --", ""), ("AND OR NOT ( *", ""), ("naïve café", "")]:
    s, r = get(f"/api/search?q={q(query)}{extra}")
    print(f"== '{query}' {extra} -> {s} {len(r['results']) if s == 200 else r}")
    if s == 200:
        for x in r["results"][:5]: print(f"     [{x['collection']}/{x['kind']}] {x['title'][:70]}{' p.' + str(x['page']) if x.get('page') else ''} | {x.get('subject_name') or ''} | {(x.get('snippet') or '')[:80]}")
