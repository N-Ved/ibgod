// Subjects: the grade path, syllabus topics with matched materials, past papers and all resources.
import { html, useState, useEffect, useRef, api, useStore, useLoad, attempt, toast, Icon, Modal, Bar, Spinner, ErrorBox, GradePick, Confidence, ResourceLink, ResourceGroup,
  fmtMin, fmtDate, subjectClass, plural, pct, go, refreshMe } from './core.js';
import { createTask } from './tasks.js';
import { replanNow } from './today.js';

// Checklist levels: how far a topic has moved through learn -> retrieve -> space (see "Study methods").
export const STAGES = [
  { n: 0, name: 'Not started', plan: 'Learn it, practise it, then review it.' },
  { n: 1, name: 'Introduced', plan: 'Taught in class, not yet revised: a short consolidation, practice, then reviews.' },
  { n: 2, name: 'Familiar', plan: 'You follow the notes but cannot recall them unaided: retrieval practice, then reviews.' },
  { n: 3, name: 'Revised', plan: 'You have recalled it from memory and answered exam questions: spaced reviews only.' },
  { n: 4, name: 'Secure', plan: 'Recalled correctly on several days, including timed: one maintenance review.' },
];
const STAGE_TONE = ['', 'info', 'warn', 'primary', 'ok'];

function suggestReplan(text) {
  toast(text, { ms: 9000, action: { label: 'Re-plan now', run: () => replanNow(true) } });
}

export function Subjects() {
  const { me } = useStore();
  const { data } = useLoad(() => api('/api/dashboard'), []);
  const prog = Object.fromEntries(((data && data.subjects) || []).map((s) => [s.key, s]));
  return html`<div class="page">
    <div class="page-head"><div class="grow"><h1>Subjects</h1><div class="sub">Your path to the grade you want in each subject, with everything the library has for it.</div></div>
      <a class="btn" href="#/setup"><${Icon} name="pen" size=${16} /> Edit subjects</a></div>
    <div class="grid three">${me.subjects.map((s) => { const p = prog[s.subject] || {}; return html`<a class=${'card subject-card ' + subjectClass(s.subject)} href=${'#/subjects/' + encodeURIComponent(s.subject)} key=${s.subject}>
      <div class="row"><h3 class="grow">${s.name}</h3><span class="chip">${s.level}</span></div>
      <div class="gradeline"><span>${s.current_grade}</span><span class="arrow">→</span><span>${s.target_grade}</span>${s.target_grade > s.current_grade ? html`<span class="chip primary">+${s.target_grade - s.current_grade}</span>` : html`<span class="chip ok">on target</span>`}</div>
      <${Bar} value=${p.done || 0} max=${p.planned || 0} tone="ok" />
      <div class="hint">${p.planned ? html`${plural(p.done_tasks || 0, 'session')} done · ${p.todo_tasks || 0} to go` : 'Open to see your path'}</div>
    </a>`; })}</div>
    ${!me.subjects.length ? html`<div class="empty"><h3>No subjects yet</h3><a class="btn primary" href="#/setup">Set up your subjects</a></div>` : null}
  </div>`;
}

function PathTab({ d }) {
  const p = d.path;
  const guide = d.overview.guides[0];
  return html`<div class="stack">
    ${p.note ? html`<div class="banner warn"><${Icon} name="alert" /><div>${p.note}</div></div>` : null}
    <div class="grid two">
      <div class="card">
        <div class="card-title"><${Icon} name="target" /><h2>From ${p.current} to ${p.target}</h2></div>
        ${p.steps.map((s) => html`<div class="step" key=${s.from}>
          <div class="step-num">${s.from === s.to ? s.from : `${s.from}→${s.to}`}</div>
          <div><strong>${s.title}</strong><div class="small muted" style=${{ margin: '2px 0 6px' }}>${s.focus}</div><ul class="small">${s.actions.map((a) => html`<li>${a}</li>`)}</ul></div>
        </div>`)}
      </div>
      <div class="stack">
        <div class="card">
          <div class="card-title"><h2>Do next</h2></div>
          ${p.next_actions.length ? html`<ul>${p.next_actions.map((a) => html`<li>${a}</li>`)}</ul>` : html`<div class="hint">Follow today's sessions. You are on track.</div>`}
        </div>
        <div class="card">
          <div class="card-title"><h2>How to split your time at this grade</h2></div>
          <div class="split"><i class="a" style=${{ width: p.time_split.content + '%' }}></i><i class="b" style=${{ width: p.time_split.practice + '%' }}></i><i class="c" style=${{ width: p.time_split.papers + '%' }}></i></div>
          <div class="legend" style=${{ marginTop: '8px' }}><span class="a">Learning content ${p.time_split.content}%</span><span class="b">Topic questions ${p.time_split.practice}%</span><span class="c">Timed papers ${p.time_split.papers}%</span></div>
        </div>
        <div class="card">
          <div class="card-title"><${Icon} name="bulb" /><h2>Methods that matter most now</h2></div>
          <div class="stack tight">${p.techniques.map((t) => html`<a class="res" href=${'#/techniques/' + t.id} key=${t.id}><span class="grow"><div class="res-t">${t.title}</div><div class="res-s">${t.summary.slice(0, 150)}…</div></span><${Icon} name="right" size=${16} /></a>`)}</div>
        </div>
      </div>
    </div>
    ${p.family_tips ? html`<div class="card"><div class="card-title"><h2>${p.family_tips.title}: what examiners reward</h2></div><ul>${p.family_tips.tips.map((t) => html`<li>${t}</li>`)}</ul></div>` : null}
    <div class="card">
      <div class="card-title"><h2 class="grow">How ${d.subject.short} ${d.mine.level} is assessed</h2>${guide ? html`<a class="btn sm" href=${guide.url} target="_blank" rel="noopener">Subject guide</a>` : null}</div>
      <div class="scroll-x"><table class="tbl"><thead><tr><th>Component</th><th>Weight</th><th>Time</th><th>What it is</th></tr></thead><tbody>
        ${d.assessment.map((c) => html`<tr key=${c.name}><td><strong>${c.name}</strong></td><td class="tnum">${c.weight}%</td><td class="nowrap">${c.minutes ? fmtMin(c.minutes) : 'coursework'}</td><td class="muted">${c.detail}</td></tr>`)}
      </tbody></table></div>
      <div class="hint" style=${{ marginTop: '8px' }}>${p.coursework_weight ? `${p.coursework_weight}% of this subject is decided before the exam hall. ` : ''}Always confirm details with your teacher and the official subject guide${d.subject.syllabus_from > 2000 ? ` (this course was first examined in ${d.subject.syllabus_from})` : ''}.</div>
    </div>
    ${p.paper_scores.length ? html`<div class="card"><div class="card-title"><h2>Your timed paper scores</h2></div><div class="row wrap">${p.paper_scores.map((s, i) => html`<span class="chip primary" key=${i}>${s}%</span>`)}</div></div>` : null}
  </div>`;
}

function TopicRow({ subjectKey, t, done, onChange }) {
  const [open, setOpen] = useState(false);
  const [res, setRes] = useState(null);
  useEffect(() => {
    if (!open || res) return;
    api(`/api/subjects/${encodeURIComponent(subjectKey)}/topics/${encodeURIComponent(t.code)}/resources`).then(setRes).catch(() => setRes({}));
  }, [open]);
  const save = (body) => attempt(() => api(`/api/subjects/${encodeURIComponent(subjectKey)}/topics/${encodeURIComponent(t.code)}`, { method: 'PUT', body })).then((r) => r && onChange(body));
  const rename = () => {
    const name = prompt('Name for this topic (leave empty to restore the original):', t.name);
    if (name === null) return;
    save({ custom_name: name.trim() });
  };
  const any = res && Object.values(res).some((v) => v && v.length);
  return html`<div class=${'topic' + (t.enabled ? '' : ' off')}>
    ${t.optional ? html`<input type="checkbox" checked=${t.enabled} aria-label=${'I study ' + t.name} onChange=${(e) => save({ enabled: e.target.checked })} />` : null}
    <button class="topic-name" onClick=${() => setOpen(!open)} aria-expanded=${open}><span class="muted tnum">${t.code}</span> ${t.name.startsWith(t.code) ? t.name.slice(t.code.length) : t.name}
      ${t.hl_only ? html` <span class="chip">HL</span>` : null}${done ? html` <span class="chip ok">${plural(done, 'session')} done</span>` : null}</button>
    ${t.enabled ? html`<select class=${'input cov cov' + (t.coverage || 0)} aria-label=${'Coverage of ' + t.name} title=${STAGES[t.coverage || 0].plan} value=${t.coverage || 0}
      onChange=${(e) => save({ coverage: Number(e.target.value) })}>${STAGES.map((st) => html`<option value=${st.n}>${st.name}</option>`)}</select>` : null}
    ${t.enabled ? html`<${Confidence} value=${t.confidence || 0} onChange=${(c) => save({ confidence: c })} />` : null}
    ${open ? html`<div class="topic-res stack tight">
      ${!res ? html`<div class="hint"><span class="spinner"></span> Finding materials…</div>` : any ? html`
        <${ResourceGroup} title="Your copy" items=${res.yours} />
        <${ResourceGroup} title=${t.work ? 'Study guides' : 'Notes'} items=${res.notes} />
        <${ResourceGroup} title="In your textbook" items=${res.textbook} />
        <${ResourceGroup} title="Videos" items=${res.videos} />
        <${ResourceGroup} title="Exam questions on this topic" items=${res.questions} />
        <${ResourceGroup} title="Study site pages" items=${res.pages} />` : html`<div class="hint">Nothing matched automatically. <a href=${`#/library?subject=${encodeURIComponent(subjectKey)}&q=${encodeURIComponent(t.name)}`}>Search the library for "${t.name}"</a>.</div>`}
      <div class="row"><a class="btn sm" href=${`#/library?subject=${encodeURIComponent(subjectKey)}&q=${encodeURIComponent(t.name)}`}><${Icon} name="search" size=${14} /> Search more</a>
        ${t.work ? html`<a class="btn sm ghost" href=${'#/subjects/' + encodeURIComponent(subjectKey) + '/works'}>Edit in My works</a>` : html`<button class="btn sm ghost" onClick=${rename}>Rename</button>`}</div>
    </div>` : null}
  </div>`;
}

function TopicsTab({ d, setData }) {
  const [dirty, setDirty] = useState(false);
  const [replanning, setReplanning] = useState(false);
  const replan = async () => { setReplanning(true); const res = await replanNow(true); setReplanning(false); if (res) setDirty(false); };
  const rated = d.units.flatMap((u) => u.topics).filter((t) => t.enabled && t.confidence).length;
  const total = d.units.flatMap((u) => u.topics).filter((t) => t.enabled).length;
  const patch = (code, body) => {
    setData((cur) => ({ ...cur, units: cur.units.map((u) => ({ ...u, topics: u.topics.map((t) => (t.code !== code ? t : { ...t, ...(body.enabled !== undefined ? { enabled: body.enabled } : {}), ...(body.confidence !== undefined ? { confidence: body.confidence || null } : {}),
      ...(body.coverage !== undefined ? { coverage: body.coverage } : {}), ...(body.custom_name !== undefined ? { name: body.custom_name || t.default_name } : {}) })) })) }));
    if (body.enabled !== undefined || body.coverage !== undefined) setDirty(true);
  };
  const all = d.units.flatMap((u) => u.topics).filter((t) => t.enabled);
  const counts = STAGES.map((st) => all.filter((t) => (t.coverage || 0) === st.n).length);
  const bulk = async (unit, level) => {
    const res = await attempt(() => api(`/api/subjects/${encodeURIComponent(d.subject.key)}/coverage`, { method: 'PUT', body: { level, unit } }));
    if (!res) return;
    setData((cur) => ({ ...cur, units: cur.units.map((u) => (unit === null || u.code === unit ? { ...u, topics: u.topics.map((t) => (t.enabled ? { ...t, coverage: level } : t)) } : u)) }));
    setDirty(true);
  };
  return html`<div class="stack">
    <div class="card stack">
      <div class="card-title"><${Icon} name="check" /><h2 class="grow">Master checklist</h2>
        <select class="input" style=${{ width: 'auto' }} aria-label="Set every topic to" value="" onChange=${(e) => { if (e.target.value !== '') { bulk(null, Number(e.target.value)); e.target.value = ''; } }}>
          <option value="">Set all topics to…</option>${STAGES.map((st) => html`<option value=${st.n}>${st.name}</option>`)}</select></div>
      <div class="hint">Mark how far you have got with each topic. The next re-plan skips what you have already done and puts the time where it is still needed.</div>
      <div class="split">${counts.map((c, i) => html`<i key=${i} class=${'cov-seg cov' + i} style=${{ width: pct(c, all.length) + '%' }} title=${STAGES[i].name + ': ' + c}></i>`)}</div>
      <div class="legend">${STAGES.map((st, i) => html`<span class=${'cov-key cov' + i} key=${st.n}>${st.name} ${counts[i]}</span>`)}</div>
      ${dirty ? html`<div class="inline-note"><span class="grow">Checklist changed. Re-plan to apply it.</span><button class="btn sm primary" disabled=${replanning} onClick=${replan}>${replanning ? 'Re-planning…' : 'Re-plan now'}</button></div>` : null}
      <details><summary class="small muted" style=${{ cursor: 'pointer' }}>What each level means and what the plan does with it</summary>
        <div class="stack tight" style=${{ marginTop: '8px' }}>${STAGES.map((st) => html`<div class="small" key=${st.n}><span class=${'chip ' + STAGE_TONE[st.n]}>${st.name}</span> ${st.plan}</div>`)}
          <div class="hint">The levels follow how memory is built: first meet the idea, then retrieve it from memory (retrieval practice), then return to it at growing gaps (spaced relearning). Updating this honestly beats re-reading: mark a topic "Revised" only when you could recall it without the notes. Finishing a Learn or Practise session in the plan moves a topic up automatically.</div></div></details>
    </div>
    <div class="banner"><${Icon} name="bulb" /><div class="grow">Rate each topic from 1 (lost) to 5 (could teach it). The plan gives weak topics more time and puts them earlier. <strong>${rated} of ${total} rated.</strong> Tap a topic to see notes, textbook pages, videos and exam questions for it.</div>
      ${rated ? html`<button class="btn sm" onClick=${() => replanNow(true)}>Re-plan with ratings</button>` : null}</div>
    ${d.units.map((u) => html`<div class="card" key=${u.code}>
      <div class="card-title"><h3 class="grow">${u.name}</h3>
        <select class="input" style=${{ width: 'auto' }} aria-label=${'Set all of ' + u.name + ' to'} value="" onChange=${(e) => { if (e.target.value !== '') { bulk(u.code, Number(e.target.value)); e.target.value = ''; } }}>
          <option value="">Set unit to…</option>${STAGES.map((st) => html`<option value=${st.n}>${st.name}</option>`)}</select></div>
      ${u.topics.map((t) => html`<${TopicRow} key=${t.code} subjectKey=${d.subject.key} t=${t} done=${d.done_by_topic[t.code]} onChange=${(body) => patch(t.code, body)} />`)}
    </div>`)}
  </div>`;
}

function ScoreForm({ paper, onSaved, onClose }) {
  const [score, setScore] = useState('');
  const [max, setMax] = useState('');
  const save = async () => {
    const body = { score: score === '' ? null : Number(score), max_score: max === '' ? null : Number(max) };
    const res = await attempt(() => api(`/api/papers/${paper.id}/attempts`, { method: 'POST', body }));
    if (res) { toast('Attempt logged. This paper will not be scheduled again.'); onSaved(); onClose(); }
  };
  return html`<${Modal} title="Log your attempt" onClose=${onClose} footer=${html`<button class="btn" onClick=${onClose}>Cancel</button><button class="btn primary" onClick=${save}>Save</button>`}>
    <div class="muted small">${paper.title}</div>
    <div class="row"><div class="field grow"><label for="sc-a">Your marks</label><input id="sc-a" class="input" type="number" min="0" step="0.5" value=${score} onInput=${(e) => setScore(e.target.value)} /></div>
      <div class="field grow"><label for="sc-b">Out of</label><input id="sc-b" class="input" type="number" min="1" step="1" value=${max} onInput=${(e) => setMax(e.target.value)} /></div></div>
    <div class="hint">Mark strictly with the markscheme. Leave marks empty if you only want to record that you sat it.</div>
  <//>`;
}

function PlanPaper({ paper, subjectKey, minutes, today, onClose }) {
  const [date, setDate] = useState(today);
  const save = async () => {
    const res = await createTask({ date, title: 'Timed paper: ' + paper.title, minutes: minutes || 90, subject: subjectKey, kind: 'paper', resource_id: paper.id, detail: 'Sit it in one go under exam conditions, then mark it with the markscheme.' });
    if (res) { toast('Added to your plan.', { action: { label: 'Open plan', run: () => go('#/plan?date=' + date) } }); onClose(); }
  };
  return html`<${Modal} title="Add this paper to your plan" onClose=${onClose} footer=${html`<button class="btn" onClick=${onClose}>Cancel</button><button class="btn primary" onClick=${save}>Add</button>`}>
    <div class="muted small">${paper.title}</div>
    <div class="field"><label for="pp-d">Day</label><input id="pp-d" class="input" type="date" min=${today} value=${date} onInput=${(e) => setDate(e.target.value)} /></div>
  <//>`;
}

function PapersTab({ d }) {
  const { me } = useStore();
  const { data, error, reload } = useLoad(() => api(`/api/subjects/${encodeURIComponent(d.subject.key)}/papers`), [d.subject.key]);
  const [legacy, setLegacy] = useState(false);
  const [paperNo, setPaperNo] = useState('');
  const [limit, setLimit] = useState(8);
  const [modal, setModal] = useState(null);
  if (error) return html`<${ErrorBox} error=${error} retry=${reload} />`;
  if (!data) return html`<${Spinner} label="Loading past papers" />`;
  const all = data.papers;
  const hasLegacy = all.some((p) => p.syllabus === 'legacy');
  const hasCurrent = all.some((p) => p.syllabus !== 'legacy');
  const showLegacy = legacy || !hasCurrent;
  const list = all.filter((p) => (showLegacy || p.syllabus !== 'legacy') && (!paperNo || (p.paper || '').startsWith(paperNo)));
  const groups = [];
  for (const p of list) {
    const label = [p.session, p.year].filter(Boolean).join(' ') || (p.collection === 'specimen' ? 'Specimen papers' : p.collection === 'mocks' ? 'Mock papers' : 'Other');
    let g = groups[groups.length - 1];
    if (!g || g.label !== label) { g = { label, items: [], legacy: p.syllabus === 'legacy' }; groups.push(g); }
    g.items.push(p);
  }
  const numbers = [...new Set(all.map((p) => (p.paper || '')[0]).filter(Boolean))].sort();
  const minutesFor = (p) => { const c = d.assessment.find((x) => x.name.replace(/\D/g, '') === (p.paper || '')[0]); return c ? c.minutes : 90; };
  return html`<div class="stack">
    <div class="banner"><${Icon} name="clock" /><div>Sit papers timed and closed-book, mark strictly, then log your score here. Keep the newest two sessions for the last month before exams.${hasLegacy && hasCurrent ? ` Papers before ${d.subject.syllabus_from} follow the previous syllabus.` : ''}</div></div>
    <div class="row wrap">
      <div class="seg"><button class=${!paperNo ? 'on' : ''} onClick=${() => setPaperNo('')}>All</button>${numbers.map((n) => html`<button class=${paperNo === n ? 'on' : ''} onClick=${() => setPaperNo(n)}>Paper ${n}</button>`)}</div>
      ${hasLegacy && hasCurrent ? html`<label class="switch"><input type="checkbox" checked=${legacy} onChange=${(e) => setLegacy(e.target.checked)} /> Include older syllabus</label>` : null}
      <span class="hint right">${plural(list.length, 'file')}</span>
    </div>
    ${!groups.length ? html`<div class="empty"><h3>No papers found</h3><div>The library has no ${d.mine.level} papers for this subject${paperNo ? ' with that paper number' : ''}.</div></div>` : null}
    ${groups.slice(0, limit).map((g) => html`<div class="card" key=${g.label}>
      <div class="card-title"><h3 class="grow">${g.label}</h3>${g.legacy ? html`<span class="chip warn">older syllabus</span>` : null}</div>
      <div class="res-list">${g.items.map((p) => html`<div key=${p.id}>
        <${ResourceLink} r=${p} extra=${html`<span class="row" onClick=${(e) => e.preventDefault()}>
          ${p.attempts.length ? html`<span class="chip ok">${p.attempts.map((a) => (a.score != null && a.max_score ? Math.round((100 * a.score) / a.max_score) + '%' : 'sat')).join(', ')}</span>` : null}</span>`} />
        ${p.kind === 'question_paper' ? html`<div class="row wrap" style=${{ margin: '4px 0 8px 36px' }}>
          ${p.pair_id ? html`<a class="btn sm" href=${`/api/files/${p.pair_id}/open`} target="_blank" rel="noopener">Markscheme</a>` : html`<span class="hint">no markscheme in library</span>`}
          <button class="btn sm" onClick=${() => setModal({ type: 'score', paper: p })}>Log score</button>
          <button class="btn sm" onClick=${() => setModal({ type: 'plan', paper: p })}>Add to plan</button></div>` : null}
      </div>`)}</div>
    </div>`)}
    ${groups.length > limit ? html`<button class="btn" onClick=${() => setLimit(limit + 10)}>Show earlier sessions (${groups.length - limit} more)</button>` : null}
    ${modal && modal.type === 'score' ? html`<${ScoreForm} paper=${modal.paper} onClose=${() => setModal(null)} onSaved=${reload} />` : null}
    ${modal && modal.type === 'plan' ? html`<${PlanPaper} paper=${modal.paper} subjectKey=${d.subject.key} minutes=${minutesFor(modal.paper)} today=${me.today} onClose=${() => setModal(null)} />` : null}
  </div>`;
}

function Collapsible({ title, items, first = 6 }) {
  const [all, setAll] = useState(false);
  if (!items || !items.length) return null;
  return html`<div class="card"><div class="card-title"><h3 class="grow">${title}</h3><span class="hint">${items.length}</span></div>
    <div class="res-list">${(all ? items : items.slice(0, first)).map((r) => html`<${ResourceLink} key=${r.id} r=${r} />`)}</div>
    ${items.length > first ? html`<button class="btn sm ghost" style=${{ marginTop: '6px' }} onClick=${() => setAll(!all)}>${all ? 'Show fewer' : `Show all ${items.length}`}</button>` : null}</div>`;
}

function ResourcesTab({ d, reload }) {
  const o = d.overview;
  const setBook = async (id) => {
    const res = await attempt(() => api(`/api/subjects/${encodeURIComponent(d.subject.key)}`, { method: 'PATCH', body: id ? { textbook_id: Number(id) } : { clear_textbook: true } }));
    if (res) { toast('Textbook saved. Topic pages now point into this book.'); reload(); }
  };
  const empty = !o.textbooks.length && !o.revision_guides.length && !o.question_banks.length && !o.guides.length && !o.exemplars.length && !o.mocks.length && !o.site_homes.length;
  return html`<div class="stack">
    <div class="card"><div class="card-title"><${Icon} name="book" /><h3 class="grow">My textbook</h3></div>
      ${o.textbooks.length ? html`<select class="input" aria-label="My textbook" value=${d.mine.textbook_id || ''} onChange=${(e) => setBook(e.target.value)}>
        <option value="">Not chosen</option>${o.textbooks.map((b) => html`<option value=${b.id}>${b.title}${b.syllabus === 'legacy' ? ' (older syllabus)' : ''}</option>`)}</select>` : html`<div class="hint">No textbooks for this subject in the library.</div>`}
      ${d.textbook ? html`<div style=${{ marginTop: '8px' }}><${ResourceLink} r=${d.textbook} /></div>` : null}
      ${d.mine.textbook_other ? html`<div class="hint" style=${{ marginTop: '6px' }}>You also use: ${d.mine.textbook_other}</div>` : null}</div>
    <div class="grid two">
      <${Collapsible} title="Subject guide, booklets and case studies" items=${[...o.guides, ...o.booklets]} />
      <${Collapsible} title="Question banks and study sites" items=${[...o.question_banks, ...o.site_homes]} />
      <${Collapsible} title="Textbooks" items=${o.textbooks} />
      <${Collapsible} title="Revision guides and workbooks" items=${o.revision_guides} />
      <${Collapsible} title="Answers and worked solutions" items=${o.answers} />
      <${Collapsible} title="Mock papers and practice sets" items=${o.mocks} />
      <${Collapsible} title="Exemplars (IA and EE)" items=${o.exemplars} />
    </div>
    ${empty ? html`<div class="empty"><h3>Nothing filed under this subject yet</h3><div>Try the <a href=${'#/library?q=' + encodeURIComponent(d.subject.name)}>library search</a>.</div></div>` : null}
    <a class="btn" href=${'#/library?subject=' + encodeURIComponent(d.subject.key)}><${Icon} name="search" size=${16} /> Search everything for ${d.subject.short}</a>
  </div>`;
}

export function SubjectPage({ subjectKey, tab }) {
  const { data, error, reload, setData } = useLoad(() => api(`/api/subjects/${encodeURIComponent(subjectKey)}`), [subjectKey]);
  const [editing, setEditing] = useState(false);
  const [cur, setCur] = useState(4);
  const [target, setTarget] = useState(6);
  const [exam, setExam] = useState('');
  useEffect(() => { if (data) { setCur(data.mine.current_grade); setTarget(data.mine.target_grade); setExam(data.mine.exam_date || ''); } }, [data && data.mine.current_grade, data && data.mine.target_grade, data && data.mine.exam_date]);
  if (error) return html`<div class="page"><${ErrorBox} error=${error} retry=${reload} /><a href="#/subjects">Back to subjects</a></div>`;
  if (!data) return html`<div class="page"><${Spinner} label="Loading subject" /></div>`;
  const active = ['path', 'topics', 'works', 'papers', 'resources'].includes(tab) ? tab : 'path';
  const base = '#/subjects/' + encodeURIComponent(subjectKey);
  const save = async () => {
    const body = { current_grade: cur, target_grade: Math.max(cur, target) };
    if (exam) body.exam_date = exam; else body.clear_exam_date = true;
    const res = await attempt(() => api(`/api/subjects/${encodeURIComponent(subjectKey)}`, { method: 'PATCH', body }));
    if (!res) return;
    setEditing(false);
    await attempt(refreshMe);
    reload();
    if (res.replan_suggested) suggestReplan('Saved. Re-plan so your schedule reflects the change.');
  };
  const hasExam = data.assessment.some((c) => c.kind === 'exam');
  return html`<div class=${'page ' + subjectClass(subjectKey)}>
    <div class="page-head">
      <div class="grow"><a class="small" href="#/subjects">← Subjects</a><h1>${data.subject.name} <span class="chip">${data.mine.level}</span></h1>
        <div class="sub">Grade ${data.mine.current_grade} now · aiming for ${data.mine.target_grade}${hasExam ? ` · last study day ${fmtDate(data.exam_date, { year: true })}` : ''}</div></div>
      <button class="btn" onClick=${() => setEditing(true)}><${Icon} name="pen" size=${16} /> Update grades</button>
    </div>
    <div class="tabs" role="tablist">${[['path', 'My path'], ['topics', 'Topics'], ...(data.works_supported ? [['works', 'My works']] : []), ['papers', 'Past papers'], ['resources', 'Resources']].map(([k, label]) => html`<button role="tab" aria-selected=${active === k} class=${active === k ? 'on' : ''} onClick=${() => go(base + '/' + k)}>${label}</button>`)}</div>
    ${active === 'path' ? html`<${PathTab} d=${data} />` : active === 'topics' ? html`<${TopicsTab} d=${data} setData=${setData} />` : active === 'works' && data.works_supported ? html`<${WorksTab} d=${data} reloadSubject=${reload} />`
      : active === 'papers' ? html`<${PapersTab} d=${data} />` : html`<${ResourcesTab} d=${data} reload=${reload} />`}
    ${editing ? html`<${Modal} title=${'Update ' + data.subject.short} onClose=${() => setEditing(false)} footer=${html`<button class="btn" onClick=${() => setEditing(false)}>Cancel</button><button class="btn primary" onClick=${save}>Save</button>`}>
      <div class="field"><label>Current predicted grade</label><${GradePick} value=${cur} onChange=${(g) => { setCur(g); if (target < g) setTarget(g); }} /></div>
      <div class="field"><label>Target grade</label><${GradePick} value=${target} min=${cur} onChange=${setTarget} /></div>
      <div class="field"><label for="sp-exam">First exam date for this subject (optional)</label><input id="sp-exam" class="input" type="date" value=${exam} onInput=${(e) => setExam(e.target.value)} />
        <div class="hint">Leave empty to use the start of the exam session. Your school's exam timetable has the exact dates.</div></div>
      ${data.grades.length > 1 ? html`<div class="hint">Grade history: ${data.grades.map((g) => `${g.grade} (${fmtDate(g.date, { day: false })})`).join(' → ')}</div>` : null}
    <//>` : null}
  </div>`;
}

// ───────── My works (language subjects) ─────────
function fmtMB(b) { return b ? (b / 1048576 >= 1 ? (b / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB') : ''; }

function uploadWork(url, file) {
  return api(url + (url.includes('?') ? '&' : '?') + 'filename=' + encodeURIComponent(file ? file.name : ''), { method: url.endsWith('/file') || url.includes('/file?') ? 'PUT' : 'POST', form: file || new Blob([]) });
}

function WorkEditor({ work, meta, onClose, onSaved }) {
  const [f, setF] = useState({ title: work.title, author: work.author || '', kind: work.kind, part: work.part, notes: work.notes || '' });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    setBusy(true);
    const res = await attempt(() => api(`/api/works/${work.id}`, { method: 'PATCH', body: f }));
    setBusy(false);
    if (res) { onSaved(); onClose(); }
  };
  return html`<${Modal} title="Edit work" onClose=${onClose} footer=${html`<button class="btn" onClick=${onClose}>Cancel</button><button class="btn primary" disabled=${busy || !f.title.trim()} onClick=${save}>Save</button>`}>
    <div class="field"><label for="we-t">Title</label><input id="we-t" class="input" maxlength="160" value=${f.title} onInput=${set('title')} /></div>
    <div class="field"><label for="we-a">Author</label><input id="we-a" class="input" maxlength="120" value=${f.author} onInput=${set('author')} /></div>
    <div class="row wrap">
      <div class="field grow"><label for="we-k">Form</label><select id="we-k" class="input" value=${f.kind} onChange=${set('kind')}>${Object.entries(meta.kinds).map(([k, v]) => html`<option value=${k}>${v}</option>`)}</select></div>
      <div class="field grow"><label for="we-p">Using it for</label><select id="we-p" class="input" value=${f.part} onChange=${set('part')}>${Object.entries(meta.parts).map(([k, v]) => html`<option value=${k}>${v}</option>`)}</select></div>
    </div>
    <div class="field"><label for="we-n">Your notes</label><textarea id="we-n" class="input" maxlength="2000" placeholder="Key quotations, themes, the global issue you might link it to…" value=${f.notes} onInput=${set('notes')}></textarea></div>
  <//>`;
}

function WorkCard({ w, meta, subjectKey, onChanged, onReplanNeeded }) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef(null);
  const attach = async (e) => {
    const file = e.target.files[0]; e.target.value = '';
    if (!file) return;
    if (file.size > meta.max_mb * 1048576) { toast(`That file is over ${meta.max_mb} MB.`, { error: true }); return; }
    setBusy(true);
    const res = await attempt(() => uploadWork(`/api/works/${w.id}/file`, file));
    setBusy(false);
    if (res) { toast('Copy saved.'); onChanged(); }
  };
  const setCoverage = async (n) => {
    const res = await attempt(() => api(`/api/subjects/${encodeURIComponent(subjectKey)}/topics/${w.code}`, { method: 'PUT', body: { coverage: n } }));
    if (res) { onChanged(); onReplanNeeded(); }
  };
  const remove = async () => {
    if (!confirm(`Remove "${w.title}"${w.file_url ? ' and your uploaded copy' : ''}? Its planned sessions are removed too.`)) return;
    const res = await attempt(() => api(`/api/works/${w.id}`, { method: 'DELETE' }));
    if (res) { onChanged(); onReplanNeeded(); }
  };
  return html`<div class="card stack tight">
    <div class="row top">
      <div class="grow"><h3>${w.title}</h3>${w.author ? html`<div class="muted small">${w.author}</div>` : null}
        <div class="row wrap" style=${{ marginTop: '6px' }}><span class="chip">${meta.kinds[w.kind] || w.kind}</span><span class="chip primary">${meta.parts[w.part] || w.part}</span></div></div>
      <select class=${'input cov cov' + (w.coverage || 0)} aria-label=${'Progress on ' + w.title} title=${STAGES[w.coverage || 0].plan} value=${w.coverage || 0} onChange=${(e) => setCoverage(Number(e.target.value))}>
        ${STAGES.map((st) => html`<option value=${st.n}>${st.name}</option>`)}</select>
    </div>
    ${w.notes ? html`<div class="small" style=${{ whiteSpace: 'pre-wrap' }}>${w.notes}</div>` : null}
    <div class="row wrap">
      ${w.file_url ? html`<a class="btn sm primary" href=${w.file_url} target="_blank" rel="noopener"><${Icon} name="file" size=${14} /> Open your copy</a><span class="hint">${(w.file_ext || '').toUpperCase()} · ${fmtMB(w.file_size)}</span>` : html`<span class="hint">No copy uploaded</span>`}
      <input ref=${fileInput} type="file" class="hide" accept=".pdf,.epub,.docx,.txt,application/pdf,application/epub+zip" onChange=${attach} />
      <button class="btn sm" disabled=${busy} onClick=${() => fileInput.current.click()}>${busy ? html`<span class="spinner"></span> Uploading…` : w.file_url ? 'Replace copy' : 'Upload a copy'}</button>
      <button class="btn sm ghost" onClick=${() => setEditing(true)}>Edit</button>
      <button class="btn sm ghost danger" onClick=${remove}>Remove</button>
    </div>
    ${w.guides && w.guides.length ? html`<${ResourceGroup} title="Study guides from the library" items=${w.guides} />` : html`<div class="hint">No study guide for this title was found in the library.</div>`}
    ${editing ? html`<${WorkEditor} work=${w} meta=${meta} onClose=${() => setEditing(false)} onSaved=${onChanged} />` : null}
  </div>`;
}

function WorksTab({ d, reloadSubject }) {
  const key = d.subject.key;
  const { data, error, reload } = useLoad(() => api(`/api/subjects/${encodeURIComponent(key)}/works`), [key]);
  const [form, setForm] = useState({ title: '', author: '', kind: 'novel', part: 'undecided' });
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [replanning, setReplanning] = useState(false);
  const fileInput = useRef(null);
  if (error) return html`<${ErrorBox} error=${error} retry=${reload} />`;
  if (!data) return html`<${Spinner} label="Loading your works" />`;
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const changed = () => { reload(); reloadSubject && reloadSubject(); };
  const add = async (e) => {
    e.preventDefault();
    if (file && file.size > data.max_mb * 1048576) { toast(`That file is over ${data.max_mb} MB.`, { error: true }); return; }
    setBusy(true);
    const q = new URLSearchParams({ title: form.title.trim(), author: form.author.trim(), kind: form.kind, part: form.part });
    const res = await attempt(() => uploadWork(`/api/subjects/${encodeURIComponent(key)}/works?${q}`, file));
    setBusy(false);
    if (!res) return;
    toast(`Added "${res.work.title}".`);
    setForm({ title: '', author: '', kind: form.kind, part: 'undecided' }); setFile(null); setDirty(true); changed();
  };
  const replan = async () => { setReplanning(true); const res = await replanNow(true); setReplanning(false); if (res) setDirty(false); };
  return html`<div class="stack">
    <form class="card stack" onSubmit=${add}>
      <div class="card-title"><${Icon} name="book" /><h2 class="grow">Add a work you are studying</h2></div>
      <div class="hint">Add every text you study for ${d.subject.short}. Each one goes into your checklist and plan (reading, writing practice, reviews), and is matched to study guides in the library.</div>
      <div class="row wrap">
        <div class="field grow"><label for="wk-t">Title</label><input id="wk-t" class="input" required maxlength="160" placeholder="e.g. The Great Gatsby" value=${form.title} onInput=${set('title')} /></div>
        <div class="field grow"><label for="wk-a">Author</label><input id="wk-a" class="input" maxlength="120" placeholder="e.g. F. Scott Fitzgerald" value=${form.author} onInput=${set('author')} /></div>
      </div>
      <div class="row wrap">
        <div class="field grow"><label for="wk-k">Form</label><select id="wk-k" class="input" value=${form.kind} onChange=${set('kind')}>${Object.entries(data.kinds).map(([k, v]) => html`<option value=${k}>${v}</option>`)}</select></div>
        <div class="field grow"><label for="wk-p">Using it for</label><select id="wk-p" class="input" value=${form.part} onChange=${set('part')}>${Object.entries(data.parts).map(([k, v]) => html`<option value=${k}>${v}</option>`)}</select></div>
      </div>
      <div class="row wrap">
        <input ref=${fileInput} type="file" class="hide" accept=".pdf,.epub,.docx,.txt,application/pdf,application/epub+zip" onChange=${(e) => setFile(e.target.files[0] || null)} />
        <button type="button" class="btn" onClick=${() => fileInput.current.click()}><${Icon} name="upload" size=${16} /> ${file ? 'Change file' : 'Attach your copy (optional)'}</button>
        <span class="hint grow">${file ? `${file.name} · ${fmtMB(file.size)}` : `PDF, EPUB, Word or text, up to ${data.max_mb} MB`}</span>
        <button class="btn primary" type="submit" disabled=${busy || !form.title.trim()}>${busy ? html`<span class="spinner"></span> Adding…` : 'Add work'}</button>
      </div>
      <div class="hint">Only you can see your works and files. ${data.used_mb} MB of ${data.quota_mb} MB used.</div>
    </form>
    ${dirty ? html`<div class="inline-note"><span class="grow">Your works changed. Re-plan to schedule them.</span><button class="btn sm primary" disabled=${replanning} onClick=${replan}>${replanning ? 'Re-planning…' : 'Re-plan now'}</button></div>` : null}
    ${data.works.length ? data.works.map((w) => html`<${WorkCard} key=${w.id} w=${w} meta=${data} subjectKey=${key} onChanged=${changed} onReplanNeeded=${() => setDirty(true)} />`)
      : html`<div class="empty"><h3>No works yet</h3><div>Add the texts you study in class, starting with the ones you might use for Paper 2 or your oral.</div></div>`}
  </div>`;
}
