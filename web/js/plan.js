// The schedule: a week you can rearrange, the issues your changes create, and re-planning.
import { html, useState, useEffect, api, useStore, useLoad, Icon, Modal, Bar, Spinner, ErrorBox, fmtMin, fmtDate, fmtHours, addDays, mondayOf, DAYS_LONG, weekday, plural, go } from './core.js';
import { TaskCard, IssueRow, patchTask, createTask, setDay, resetDay } from './tasks.js';
import { replanNow } from './today.js';

function DayEditor({ day, onClose, onSaved }) {
  const [minutes, setMinutes] = useState(day.capacity);
  const [note, setNote] = useState(day.note || '');
  const [busy, setBusy] = useState(false);
  const save = async (m) => { setBusy(true); const res = await setDay(day.date, m, note); setBusy(false); if (res) { onSaved(); onClose(); } };
  const reset = async () => { setBusy(true); const res = await resetDay(day.date); setBusy(false); if (res) { onSaved(); onClose(); } };
  return html`<${Modal} title=${fmtDate(day.date, { year: true })} onClose=${onClose}
      footer=${html`${day.override ? html`<button class="btn" disabled=${busy} onClick=${reset}>Back to usual (${fmtMin(day.default)})</button>` : null}
        <button class="btn" disabled=${busy} onClick=${() => save(0)}>Make it a day off</button><button class="btn primary" disabled=${busy} onClick=${() => save(Number(minutes) || 0)}>Save</button>`}>
    <div class="field"><label for="de-min">Study time available this day (minutes)</label>
      <input id="de-min" class="input" type="number" min="0" max="720" step="15" value=${minutes} onInput=${(e) => setMinutes(e.target.value)} />
      <div class="hint">Your usual ${DAYS_LONG[weekday(day.date)]} is ${fmtMin(day.default)}. This only changes this one date. Use it for trips, events, mock exams or extra-free days.</div></div>
    <div class="field"><label for="de-note">Note (optional)</label><input id="de-note" class="input" maxlength="120" placeholder="e.g. school trip" value=${note} onInput=${(e) => setNote(e.target.value)} /></div>
  <//>`;
}

function AddTask({ date, onClose, onSaved }) {
  const { me } = useStore();
  const [form, setForm] = useState({ date, title: '', minutes: 45, subject: '', detail: '' });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const save = async () => {
    setBusy(true);
    const res = await createTask({ date: form.date, title: form.title.trim(), minutes: Number(form.minutes) || 30, subject: form.subject || null, detail: form.detail.trim() || null });
    setBusy(false);
    if (res) { onSaved(); onClose(); }
  };
  return html`<${Modal} title="Add a task" onClose=${onClose} footer=${html`<button class="btn" onClick=${onClose}>Cancel</button><button class="btn primary" disabled=${busy || !form.title.trim()} onClick=${save}>Add</button>`}>
    <div class="field"><label for="at-title">What will you do?</label><input id="at-title" class="input" maxlength="200" placeholder="e.g. Chemistry test revision, IA draft, flashcards" value=${form.title} onInput=${set('title')} /></div>
    <div class="row wrap">
      <div class="field grow"><label for="at-date">Day</label><input id="at-date" class="input" type="date" value=${form.date} onInput=${set('date')} /></div>
      <div class="field"><label for="at-min">Minutes</label><input id="at-min" class="input" type="number" min="5" max="600" step="5" value=${form.minutes} onInput=${set('minutes')} /></div>
    </div>
    <div class="field"><label for="at-sub">Subject</label><select id="at-sub" class="input" value=${form.subject} onChange=${set('subject')}><option value="">General / none</option>${me.subjects.map((s) => html`<option value=${s.subject}>${s.name}</option>`)}</select></div>
    <div class="field"><label for="at-detail">Notes (optional)</label><input id="at-detail" class="input" maxlength="600" value=${form.detail} onInput=${set('detail')} /></div>
    <div class="hint">Tasks you add yourself stay exactly where you put them when the plan is rebuilt.</div>
  <//>`;
}

function Replan({ onClose, onDone }) {
  const [keep, setKeep] = useState(true);
  const [busy, setBusy] = useState(false);
  const run = async () => { setBusy(true); const res = await replanNow(keep); setBusy(false); if (res) { onDone(); onClose(); } };
  return html`<${Modal} title="Re-plan from today" onClose=${onClose} footer=${html`<button class="btn" onClick=${onClose}>Cancel</button><button class="btn primary" disabled=${busy} onClick=${run}>${busy ? html`<span class="spinner"></span> Rebuilding…` : 'Rebuild my plan'}</button>`}>
    <p>Things rarely go exactly to plan, and that is fine. Re-planning takes everything that is not done yet and spreads it again between today and your exams, using your current grades, topic confidence ratings and available time.</p>
    <ul class="small muted"><li>Everything you have completed or skipped is kept.</li><li>Overdue sessions are rescheduled, not lost.</li><li>Past papers you logged as attempted are not scheduled again.</li></ul>
    <label class="switch"><input type="checkbox" checked=${keep} onChange=${(e) => setKeep(e.target.checked)} /> Keep tasks I moved or added myself where they are</label>
  <//>`;
}

export function Plan({ query }) {
  const { me } = useStore();
  const [start, setStart] = useState(mondayOf(query.date || me.today));
  const [modal, setModal] = useState(null);
  const [showAll, setShowAll] = useState(false);
  const [showDismissed, setShowDismissed] = useState(false);
  const [dragId, setDragId] = useState(null);
  const [dropDay, setDropDay] = useState(null);
  const { data, error, reload } = useLoad((signal) => api(`/api/plan?start=${start}&days=7`, { signal }), [start]);
  useEffect(() => { if (query.date) setStart(mondayOf(query.date)); }, [query.date]);

  if (error) return html`<div class="page"><${ErrorBox} error=${error} retry=${reload} /></div>`;
  if (!data) return html`<div class="page"><${Spinner} label="Loading your plan" /></div>`;
  const byDay = {};
  for (const t of data.tasks) (byDay[t.date] = byDay[t.date] || []).push(t);
  const issues = data.issues;
  const shown = showAll ? issues : issues.slice(0, 4);
  const issueDates = new Set(issues.filter((i) => i.date).map((i) => i.date));
  const examsOn = {};
  for (const [key, d] of Object.entries(data.exam_dates || {})) (examsOn[d] = examsOn[d] || []).push((me.subjects.find((s) => s.subject === key) || {}).short || key);
  const short = Object.entries((data.summary && data.summary.subjects) || {}).filter(([, v]) => v.short > 90);

  const drop = async (date) => {
    const id = dragId;
    setDragId(null); setDropDay(null);
    const t = data.tasks.find((x) => x.id === id);
    if (!t || t.date === date) return;
    const res = await patchTask(id, { date }, 'Moving this task');
    if (res) reload();
  };

  return html`<div class="page">
    <div class="page-head">
      <div class="grow"><h1>Plan</h1><div class="sub">${data.span.todo ? html`${plural(data.span.todo, 'session')} left, through ${fmtDate(data.span.last, { year: true, day: false })}` : 'No sessions scheduled'} · exams begin ${fmtDate(data.exam_start, { year: true, day: false })}</div></div>
      <button class="btn" onClick=${() => setModal({ type: 'add', date: start < data.today && addDays(start, 6) >= data.today ? data.today : start })}><${Icon} name="plus" size=${17} /> Add task</button>
      <button class="btn primary" onClick=${() => setModal({ type: 'replan' })}><${Icon} name="refresh" size=${17} /> Re-plan</button>
    </div>

    ${issues.length || data.dismissed.length ? html`<div class="card">
      <div class="card-title"><${Icon} name="alert" /><h2 class="grow">${issues.length ? plural(issues.length, 'issue') + ' in your plan' : 'No open issues'}</h2>
        ${data.dismissed.length ? html`<button class="btn sm ghost" onClick=${() => setShowDismissed(!showDismissed)}>${showDismissed ? 'Hide' : 'Show'} ${data.dismissed.length} dismissed</button>` : null}</div>
      <div class="stack tight">
        ${shown.map((i) => html`<div key=${i.key}><${IssueRow} issue=${i} onChanged=${reload} />${i.date && (i.date < start || i.date > addDays(start, 6)) ? html`<button class="btn sm ghost" onClick=${() => setStart(mondayOf(i.date))}>Go to ${fmtDate(i.date)}</button>` : null}</div>`)}
        ${issues.length > 4 ? html`<button class="btn sm ghost" onClick=${() => setShowAll(!showAll)}>${showAll ? 'Show fewer' : `Show all ${issues.length}`}</button>` : null}
        ${showDismissed ? data.dismissed.map((i) => html`<${IssueRow} key=${i.key} issue=${i} dismissed=${true} onChanged=${reload} />`) : null}
      </div>
    </div>` : html`<div class="banner ok"><${Icon} name="check" /><div>No issues. Your plan fits your time and covers every subject.</div></div>`}

    ${short.length ? html`<div class="banner warn"><${Icon} name="clock" /><div>The full programme does not fit in the time available for ${short.map(([k]) => (me.subjects.find((s) => s.subject === k) || {}).short || k).join(', ')}, so topics there get shorter sessions and fewer reviews. Adding study time in <a href="#/settings">Settings</a> and re-planning restores them.</div></div>` : null}

    <div class="row wrap">
      <button class="btn icon" aria-label="Previous week" onClick=${() => setStart(addDays(start, -7))}><${Icon} name="left" /></button>
      <button class="btn" onClick=${() => setStart(mondayOf(data.today))}>This week</button>
      <button class="btn icon" aria-label="Next week" onClick=${() => setStart(addDays(start, 7))}><${Icon} name="right" /></button>
      <strong class="grow">${fmtDate(start, { day: false })} – ${fmtDate(addDays(start, 6), { day: false, year: true })}</strong>
      <input class="input" style=${{ width: 'auto' }} type="date" aria-label="Jump to date" value=${start} onChange=${(e) => e.target.value && setStart(mondayOf(e.target.value))} />
    </div>

    <div class="week">
      ${data.days.map((d) => {
        const tasks = byDay[d.date] || [];
        const planned = tasks.filter((t) => t.status === 'todo').reduce((a, t) => a + t.minutes, 0);
        const done = tasks.filter((t) => t.status === 'done').reduce((a, t) => a + t.minutes, 0);
        const past = d.date < data.today;
        const over = !past && planned > d.capacity + 15;
        const cls = 'day' + (d.date === data.today ? ' today' : '') + (d.capacity === 0 ? ' off' : '') + (over ? ' over' : '') + (dropDay === d.date ? ' drop' : '') + (examsOn[d.date] ? ' exam' : '');
        return html`<div class=${cls} key=${d.date}
            onDragOver=${(e) => { if (dragId) { e.preventDefault(); setDropDay(d.date); } }} onDragLeave=${() => setDropDay((x) => (x === d.date ? null : x))} onDrop=${(e) => { e.preventDefault(); drop(d.date); }}>
          <button class="day-head" onClick=${() => setModal({ type: 'day', day: d })} title="Change the time available on this day">
            <div class="day-name"><span>${fmtDate(d.date)}</span>${issueDates.has(d.date) ? html`<span class="chip danger">!</span>` : d.override ? html`<span class="chip">${d.capacity ? 'custom' : 'off'}</span>` : null}</div>
            <div class="day-load">${d.capacity === 0 && !planned ? (d.note || 'Day off') : html`${fmtMin(planned + done)} of ${fmtMin(d.capacity)}${d.note ? ' · ' + d.note : ''}`}</div>
            <${Bar} value=${planned + done} max=${Math.max(d.capacity, 1)} tone=${over ? 'danger' : done && !planned ? 'ok' : ''} />
          </button>
          <div class="day-tasks">
            ${examsOn[d.date] ? html`<div class="chip warn">Exams begin: ${examsOn[d.date].length > 3 ? 'all subjects' : examsOn[d.date].join(', ')}</div>` : null}
            ${tasks.map((t) => html`<${TaskCard} key=${t.id} task=${t} compact=${true} today=${data.today} onChanged=${reload}
              dragProps=${t.status === 'todo' ? { draggable: true, onDragStart: (e) => { e.dataTransfer.setData('text/plain', String(t.id)); e.dataTransfer.effectAllowed = 'move'; setDragId(t.id); }, onDragEnd: () => { setDragId(null); setDropDay(null); } } : null} />`)}
            <button class="btn sm ghost" onClick=${() => setModal({ type: 'add', date: d.date })}><${Icon} name="plus" size=${14} /> Add</button>
          </div>
        </div>`;
      })}
    </div>
    <div class="hint">Drag a task to another day, or open it and choose "Move or resize". Tap a day's header to change how much time you have that day. Every change is checked, and any problem it causes is shown straight away.</div>

    ${modal && modal.type === 'day' ? html`<${DayEditor} day=${modal.day} onClose=${() => setModal(null)} onSaved=${reload} />` : null}
    ${modal && modal.type === 'add' ? html`<${AddTask} date=${modal.date} onClose=${() => setModal(null)} onSaved=${reload} />` : null}
    ${modal && modal.type === 'replan' ? html`<${Replan} onClose=${() => setModal(null)} onDone=${reload} />` : null}
  </div>`;
}

export { fmtHours, go };
