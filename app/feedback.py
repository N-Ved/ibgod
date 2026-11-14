"""Feedback writer for IB coursework (IA, EE, TOK): instant structural checks plus criterion-by-criterion AI comments.

Jobs run one at a time in a background thread because the model shares four CPU cores with everything else.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime

from . import config, db, llm
from .knowledge import ACADEMIC_INTEGRITY_NOTE, RUBRICS

log = logging.getLogger("ibgod.feedback")
_wake = threading.Event()
_thread: threading.Thread | None = None

SCHEMA = {
    "type": "object",
    "properties": {
        "level": {"type": "string", "enum": ["emerging", "developing", "secure", "strong"]},
        "strengths": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3},
        "improvements": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4},
        "evidence": {"type": "string"},
    },
    "required": ["level", "strengths", "improvements", "evidence"],
    "additionalProperties": False,
}
SYSTEM = """You are an experienced IB Diploma examiner giving formative feedback on a student's draft. Judge only what is on the page.
Be specific: refer to what the student actually wrote. Every improvement must be an action the student can take, never a rewritten sentence or paragraph.
Do not award marks. Do not praise vaguely. Write to the student as "you"."""

_WORDS = re.compile(r"\b[\w'’-]+\b", re.UNICODE)
_SENT = re.compile(r"[.!?]+[\s\n]+")


def word_count(text: str) -> int:
    return len(_WORDS.findall(text))


def structural_checks(text: str, rubric_key: str) -> list[dict]:
    """Fast, deterministic observations that do not need a model."""
    rub = RUBRICS[rubric_key]
    low = text.lower()
    n = word_count(text)
    out: list[dict] = []

    def add(status: str, title: str, detail: str) -> None:
        out.append({"status": status, "title": title, "detail": detail})

    limit = rub.get("words") or 0
    if limit:
        if n > limit * 1.02:
            add("warn", "Over the word limit", f"About {n:,} words against a limit of {limit:,}. Examiners stop reading at the limit, so anything after it earns nothing. (The count here includes everything you pasted: remove title page, bibliography and captions before trusting it.)")
        elif n < limit * 0.6:
            add("warn", "Well under the word limit", f"About {n:,} words; the limit is {limit:,}. Short pieces usually lack depth of analysis or evaluation.")
        else:
            add("ok", "Length", f"About {n:,} words (limit {limit:,}).")
    else:
        add("info", "Length", f"About {n:,} words.")
    paras = [p for p in re.split(r"\n\s*\n", text) if len(p.split()) > 5]
    if paras:
        longest = max(len(p.split()) for p in paras)
        if longest > 350:
            add("warn", "Very long paragraph", f"One paragraph runs to about {longest} words. Split it so each paragraph makes one point.")
    sents = [s for s in _SENT.split(text) if len(s.split()) > 2]
    if sents:
        avg = sum(len(s.split()) for s in sents) / len(sents)
        if avg > 32:
            add("warn", "Long sentences", f"Average sentence length is about {avg:.0f} words. Shorter sentences are easier to follow and to mark.")
    cites = len(re.findall(r"\([A-Z][A-Za-z'’\-]+(?: et al\.?| and [A-Z][A-Za-z]+| & [A-Z][A-Za-z]+)?,? \d{4}[a-z]?(?:, p+\.? ?\d+(?:[-–]\d+)?)?\)", text)) + len(re.findall(r"\[\d{1,3}\]", text))
    has_bib = bool(re.search(r"\b(bibliography|works cited|references|reference list)\b", low))
    if rubric_key.startswith(("ee_", "history_ia", "business_ia", "psychology_ia", "geography_ia", "lang_a", "tok_essay", "economics_ia", "science_ia")):
        if cites == 0:
            add("warn", "No in-text citations detected", "No (Author, year) or [n] citations were found. Every borrowed idea, figure or quotation needs one. Ignore this if you use footnotes, which this check cannot see.")
        else:
            add("ok", "Citations", f"{cites} in-text citation(s) detected.")
        if not has_bib and rubric_key not in ("tok_exhibition",):
            add("warn", "No bibliography heading found", "Add a bibliography / works cited list, formatted consistently.")
    if rubric_key.startswith("ee_") or rubric_key in ("history_ia", "business_ia", "geography_ia"):
        if not re.search(r"research question|\brq\b|to what extent|how (?:does|do|did|far|significant)|what (?:is|was|are) the (?:effect|impact|relationship|extent)", low):
            add("warn", "Research question not obvious", "State the research question explicitly, as a question, on the title page and in the introduction.")
        else:
            add("ok", "Research question", "A research question (or question-style focus) appears in the text.")
        if "conclusion" not in low:
            add("warn", "No conclusion heading", "No section called 'Conclusion' was found. Make sure the essay ends by answering the research question directly.")
    if rubric_key == "science_ia":
        for word, label, tip in (("uncertaint", "Uncertainties", "Record measurement uncertainties and propagate them through processed data."),
                                 ("variable", "Variables", "Name the independent, dependent and controlled variables and how each is controlled."),
                                 ("safety", "Safety / ethics / environment", "Address safety, ethical and environmental considerations, even if only to say none apply."),
                                 ("limitation", "Limitations", "Evaluate specific weaknesses of the method and their likely effect on the results.")):
            if word not in low and not (word == "safety" and ("ethic" in low or "risk" in low)):
                add("warn", f"{label} not mentioned", tip)
    if rubric_key == "math_ia":
        if "aim" not in low and "objective" not in low:
            add("warn", "Aim not stated", "State the aim of the exploration clearly in the introduction.")
        if not re.search(r"reflect|limitation|extension|further", low):
            add("warn", "Little visible reflection", "Reflect throughout: discuss what results mean, limitations, and possible extensions.")
    if rubric_key in ("tok_essay", "tok_exhibition"):
        if rubric_key == "tok_essay" and not re.search(r"however|on the other hand|counter ?claim|in contrast|conversely", low):
            add("warn", "No counter-arguments signalled", "The essay should weigh different points of view. Signal counterclaims explicitly.")
        if rubric_key == "tok_exhibition" and len(re.findall(r"\bobject\b", low)) < 3:
            add("warn", "Objects not clearly identified", "Identify each of the three objects and its specific real-world context.")
    first_person = len(re.findall(r"\b(i|my|me)\b", low))
    if rubric_key in ("math_ia",) and first_person == 0:
        add("info", "Personal voice", "No first-person statements found. Personal engagement is assessed: explain your own choices and reasoning.")
    return out


def create_job(username: str, rubric: str, subject: str | None, title: str, body: str) -> int:
    with db.tx() as con:
        cur = con.execute("INSERT INTO feedback_jobs(username, rubric, subject, title, body, words, status, progress, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                          (username, rubric, subject, title[:160], body, word_count(body), "queued", "Waiting in the queue", datetime.now().isoformat(timespec="seconds")))
        job_id = cur.lastrowid
    _wake.set()
    return job_id


def _trim(text: str, max_words: int) -> tuple[str, bool]:
    words = text.split()
    if len(words) <= max_words:
        return text, False
    head, tail = int(max_words * 0.65), int(max_words * 0.35)
    return " ".join(words[:head]) + "\n\n[... middle of the work omitted for length ...]\n\n" + " ".join(words[-tail:]), True


def _set(job_id: int, **kw) -> None:
    with db.tx() as con:
        con.execute(f"UPDATE feedback_jobs SET {','.join(k + '=?' for k in kw)} WHERE id=?", (*kw.values(), job_id))


def _process(job: dict) -> None:
    rub = RUBRICS[job["rubric"]]
    checks = structural_checks(job["body"], job["rubric"])
    result: dict = {"rubric": job["rubric"], "rubric_name": rub["name"], "checks": checks, "criteria": [], "priorities": [], "note": ACADEMIC_INTEGRITY_NOTE, "ai": False, "truncated": False}
    if not llm.available(force=True):
        result["ai_error"] = "The AI model is offline, so only the automatic checks are shown. Resubmit later for criterion-by-criterion comments."
        _set(job["id"], status="done", progress=None, result=json.dumps(result), finished_at=datetime.now().isoformat(timespec="seconds"))
        return
    essay, truncated = _trim(job["body"], config.MAX_FEEDBACK_WORDS)
    result["truncated"] = truncated
    prefix = f"STUDENT WORK ({rub['name']}):\n<<<\n{essay}\n>>>\n\n"
    crits = rub["criteria"]
    for i, (code, name, marks, descriptor) in enumerate(crits, start=1):
        _set(job["id"], status="running", progress=f"Criterion {i} of {len(crits)}: {name}")
        ask = (f"Give feedback on this work for ONE criterion only.\nCriterion {code}: {name}" + (f" ({marks} marks available)" if marks else "") +
               f"\nWhat the top band requires: {descriptor}\n\nReturn JSON with: level (how well the work meets the top band: emerging, developing, secure or strong), "
               "strengths (1-3 specific things done well for this criterion), improvements (1-4 specific actions to move up a band), "
               "evidence (one short phrase quoted from the work that best illustrates your judgement).")
        try:
            raw = llm.complete([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prefix + ask}], max_tokens=420, temperature=0.2, schema=SCHEMA)
            data = json.loads(raw)
            result["criteria"].append({"code": code, "name": name, "marks": marks, "descriptor": descriptor, "level": data.get("level"),
                                       "strengths": [str(x)[:400] for x in data.get("strengths", [])][:3], "improvements": [str(x)[:500] for x in data.get("improvements", [])][:4],
                                       "evidence": str(data.get("evidence", ""))[:300]})
            result["ai"] = True
        except Exception as e:
            log.warning("feedback criterion failed: %r", e)
            result["criteria"].append({"code": code, "name": name, "marks": marks, "descriptor": descriptor, "error": "The model could not produce feedback for this criterion."})
    good = [c for c in result["criteria"] if "error" not in c]
    if good:
        _set(job["id"], progress="Summarising priorities")
        digest = "\n".join(f"{c['name']} [{c['level']}]: " + "; ".join(c["improvements"]) for c in good)
        try:
            raw = llm.complete([{"role": "system", "content": SYSTEM},
                                {"role": "user", "content": f"Here are improvement notes per criterion for a {rub['name']} draft:\n{digest}\n\nReturn JSON: priorities = the three most valuable actions, most important first, each one sentence."}],
                               max_tokens=220, temperature=0.2,
                               schema={"type": "object", "properties": {"priorities": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3}}, "required": ["priorities"], "additionalProperties": False})
            result["priorities"] = [str(x)[:400] for x in json.loads(raw).get("priorities", [])][:3]
        except Exception as e:
            log.warning("feedback summary failed: %r", e)
    _set(job["id"], status="done", progress=None, result=json.dumps(result), finished_at=datetime.now().isoformat(timespec="seconds"))


def _run() -> None:
    # Anything left 'running' by a restart goes back in the queue.
    with db.tx() as con:
        con.execute("UPDATE feedback_jobs SET status='queued', progress='Waiting in the queue' WHERE status='running'")
    while True:
        with db.ro() as con:
            job = db.one(con, "SELECT * FROM feedback_jobs WHERE status='queued' ORDER BY id LIMIT 1")
        if not job:
            _wake.clear()
            _wake.wait(timeout=300)
            continue
        try:
            _process(job)
        except Exception as e:
            log.exception("feedback job %s failed", job["id"])
            _set(job["id"], status="error", progress=None, result=json.dumps({"error": "Feedback could not be generated. Please try again.", "detail": repr(e)[:200]}),
                 finished_at=datetime.now().isoformat(timespec="seconds"))


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _thread = threading.Thread(target=_run, name="feedback", daemon=True)
    _thread.start()
