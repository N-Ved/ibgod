// Task card and the actions that change the schedule. Every change reports the issues it created.
import { html, useState, useEffect, api, store, toast, attempt, Icon, ResourceLink, ResourceGroup, fmtMin, fmtDate, subjectClass, subjectShort, addDays } from './core.js';

const KIND = { learn: 'Learn', practice: 'Practise', review: 'Review', mixed: 'Mixed practice', paper: 'Timed paper', paper_review: 'Mark & review', coursework: 'Coursework', final: 'Final review', custom: 'Task' };

function report(res, what) {
  if (res && res.created && res.created.length) store.set({ created: { issues: res.created, what } });
  if (res && res.issues) store.set({ issueCount: res.issues.length });
}

export async function patchTask(id, body, what) {
  const res = await attempt(() => api(`/api/tasks/${id}`, { method: 'PATCH', body }));
  if (res) report(res, what);
  return res;
}
export async function deleteTask(id) {
  const res = await attempt(() => api(`/api/tasks/${id}`, { method: 'DELETE' }));
  if (res) report(res);
  return res;
}
export async function createTask(body) {
  const res = await attempt(() => api('/api/tasks', { method: 'POST', body }));
  if (res) report(res, 'Adding this task');
  return res;
}
export async function setDay(date, minutes, note) {
  const res = await attempt(() => api(`/api/days/${date}`, { method: 'PUT', body: { minutes, note: note || null } }));
  if (res) report(res, 'Changing this day');
  return res;
}
export async function resetDay(date) {
  const res = await attempt(() => api(`/api/days/${date}`, { method: 'DELETE' }));
  if (res) report(res, 'Changing this day');
  return res;
}

function TaskResources({ task }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const out = {};
        const ids = [...(task.resources || []), ...(task.markschemes || [])];
        if (ids.length) out.files = (await api(`/api/resources?ids=${ids.join(',')}`)).resources;
        if (task.topic_code && task.subject && !task.topic_code.startsWith('unit:')) out.topic = await api(`/api/subjects/${encodeURIComponent(task.subject)}/topics/${encodeURIComponent(task.topic_code)}/resources`);
        if (alive) setData(out);
      } catch { if (alive) setErr(true); }
    })();
    return () => { alive = false; };
  }, [task.id]);
  if (err) return html`<div class="hint">Could not load materials for this task.</div>`;
  if (!data) return html`<div class="hint"><span class="spinner"></span> Finding materials…</div>`;
  const t = data.topic || {};
  const papers = (data.files || []).filter((r) => r.kind !== 'markscheme');
  const schemes = (data.files || []).filter((r) => r.kind === 'markscheme');
  const practice = task.kind === 'practice' || task.kind === 'review';
  const groups = practice
    ? [['Exam questions', t.questions], ['Notes to check against', t.notes], ['Textbook', t.textbook], ['Videos', t.videos]]
    : [['Notes', t.notes], ['Textbook', t.textbook], ['Videos', t.videos], ['Exam questions', t.questions], ['Study site pages', t.pages]];
  const any = papers.length || schemes.length || groups.some(([, g]) => g && g.length);
  if (!any) {
    return html`<div class="hint">No matching material was found automatically. Try the <a href=${'#/library?subject=' + encodeURIComponent(task.subject || '')}>library search</a>.</div>`;
  }
  return html`<div class="stack tight">
    <${ResourceGroup} title="Paper" items=${papers} />
    <${ResourceGroup} title="Markscheme (open only after you finish)" items=${schemes} />
    ${groups.map(([title, items]) => html`<${ResourceGroup} key=${title} title=${title} items=${(items || []).slice(0, 4)} />`)}
  </div>`;
}

export function TaskCard({ task, compact, onChanged, today, dragProps }) {
  const [open, setOpen] = useState(false);
  const [moving, setMoving] = useState(false);
  const [date, setDate] = useState(task.date);
  const [minutes, setMinutes] = useState(task.minutes);
  const [busy, setBusy] = useState(false);
  const done = task.status === 'done', skipped = task.status === 'skipped';
  const cls = `task ${subjectClass(task.subject)}${done || skipped ? ' done' : ''}${compact ? ' compact' : ''}`;

  const act = async (body, what) => {
    if (busy) return;
    setBusy(true);
    const res = await patchTask(task.id, body, what);
    setBusy(false);
    if (res) {
      if (res.extra) toast(`Added an extra review on ${fmtDate(res.extra.date)} because that felt hard.`);
      onChanged && onChanged(res);
    }
    return res;
  };
  const toggle = (e) => { e.stopPropagation(); act({ status: done || skipped ? 'todo' : 'done', rating: 'ok' }); };
  const remove = async () => {
    if (!confirm('Delete this task from your plan?')) return;
    const res = await deleteTask(task.id);
    if (res) onChanged && onChanged(res);
  };
  const saveMove = async () => {
    const body = {};
    if (date !== task.date) body.date = date;
    if (Number(minutes) !== task.minutes) body.minutes = Number(minutes);
    if (!Object.keys(body).length) { setMoving(false); return; }
    const res = await act(body, 'Moving this task');
    if (res) setMoving(false);
  };
  const rateable = ['learn', 'review', 'practice'].includes(task.kind) && task.topic_code;

  return html`<div class=${cls} ...${dragProps || {}}>
    <button class=${'check' + (done ? ' on' : skipped ? ' skip' : '')} aria-label=${done ? 'Mark as not done' : 'Mark as done'} onClick=${toggle} disabled=${busy}><${Icon} name=${skipped ? 'x' : 'check'} size=${compact ? 13 : 15} /></button>
    <div class="grow">
      <div class="task-title" role="button" tabindex="0" onClick=${() => setOpen(!open)} onKeyDown=${(e) => { if (e.key === 'Enter') setOpen(!open); }}>${task.title}</div>
      <div class="task-meta">
        ${!compact && task.subject_name ? html`<span class="chip">${task.subject_name}</span>` : null}
        <span><${Icon} name="clock" size=${12} /> ${fmtMin(task.minutes)}</span>
        ${task.legacy ? html`<span class="chip warn">older syllabus</span>` : null}
        ${task.pinned ? html`<span title="You placed this task. Re-planning keeps it where it is."><${Icon} name="pin" size=${12} /></span>` : null}
        ${today && task.date < today && task.status === 'todo' ? html`<span class="chip danger">was due ${fmtDate(task.date)}</span>` : null}
      </div>
      ${open ? html`<div class="task-body">
        ${task.detail ? html`<div class="small muted">${task.detail}</div>` : null}
        ${task.status === 'todo' ? html`<${TaskResources} task=${task} />` : null}
        ${moving ? html`<div class="row wrap">
          <div class="field"><label>Day</label><input class="input" type="date" value=${date} onInput=${(e) => setDate(e.target.value)} /></div>
          <div class="field"><label>Minutes</label><input class="input" type="number" min="5" max="600" step="5" value=${minutes} onInput=${(e) => setMinutes(e.target.value)} /></div>
          <div class="row"><button class="btn primary sm" onClick=${saveMove} disabled=${busy}>Save</button><button class="btn sm" onClick=${() => setMoving(false)}>Cancel</button></div>
        </div>` : html`<div class="task-actions">
          ${task.status === 'todo' && rateable ? html`
            <button class="btn sm" disabled=${busy} onClick=${() => act({ status: 'done', rating: 'hard' })}>Done, it was hard</button>
            <button class="btn sm primary" disabled=${busy} onClick=${() => act({ status: 'done', rating: 'ok' })}>Done</button>
            <button class="btn sm" disabled=${busy} onClick=${() => act({ status: 'done', rating: 'easy' })}>Done, easy</button>` : null}
          ${task.status === 'todo' && !rateable ? html`<button class="btn sm primary" disabled=${busy} onClick=${() => act({ status: 'done' })}>Done</button>` : null}
          ${task.status === 'todo' ? html`
            <button class="btn sm" onClick=${() => { setDate(task.date); setMinutes(task.minutes); setMoving(true); }}>Move or resize</button>
            <button class="btn sm" disabled=${busy} onClick=${() => act({ date: addDays(today || task.date, 1) }, 'Moving this task')}>Tomorrow</button>
            <button class="btn sm" disabled=${busy} onClick=${() => act({ status: 'skipped' })}>Skip</button>` : html`<button class="btn sm" disabled=${busy} onClick=${() => act({ status: 'todo' })}>Reopen</button>`}
          ${task.pinned && task.origin === 'auto' ? html`<button class="btn sm" disabled=${busy} title="Let re-planning move this task again" onClick=${() => act({ pinned: false })}>Unpin</button>` : null}
          <button class="btn sm danger" onClick=${remove}>Delete</button>
        </div>`}
      </div>` : null}
    </div>
  </div>`;
}

export function IssueRow({ issue, onChanged, dismissed }) {
  const [busy, setBusy] = useState(false);
  const call = async (path) => {
    setBusy(true);
    const res = await attempt(() => api(path, { method: 'POST', body: { key: issue.key } }));
    setBusy(false);
    if (res) { store.set({ issueCount: res.issues.length }); onChanged && onChanged(res); }
  };
  return html`<div class=${'issue ' + issue.severity}>
    <div class="grow">
      <div class="issue-title">${issue.title}</div>
      <div class="small muted">${issue.detail}</div>
      <div class="small"><strong>Fix:</strong> ${issue.fix}</div>
    </div>
    ${dismissed ? html`<button class="btn sm" disabled=${busy} onClick=${() => call('/api/issues/restore')}>Restore</button>`
      : html`<button class="btn sm" disabled=${busy} onClick=${() => call('/api/issues/dismiss')}>Dismiss</button>`}
  </div>`;
}

export { KIND, subjectShort };
