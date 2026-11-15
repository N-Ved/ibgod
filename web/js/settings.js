// Settings: profile, exam session, weekly time, appearance, data controls and the admin panel.
import { html, useState, api, store, useStore, useLoad, attempt, toast, Icon, Spinner, fmtHours, fmtSize, applyTheme, refreshMe } from './core.js';
import { WeekEditor } from './onboarding.js';
import { replanNow } from './today.js';

function Admin() {
  const { data, reload } = useLoad(() => api('/api/admin/status'), []);
  const rescan = async () => { const r = await attempt(() => api('/api/admin/rescan', { method: 'POST' })); if (r) { toast('Rescan started. New and changed files will appear as they are indexed.'); setTimeout(reload, 2500); } };
  if (!data) return html`<div class="card"><${Spinner} label="Loading server status" /></div>`;
  const ix = data.index;
  return html`<div class="card stack">
    <div class="card-title"><${Icon} name="settings" /><h2 class="grow">Server (admins only)</h2><button class="btn sm" onClick=${reload}>Refresh</button><button class="btn sm primary" onClick=${rescan}>Rescan drive</button></div>
    <div class="row wrap small">
      <span class="chip ${ix.phase === 'idle' ? 'ok' : ix.phase === 'error' ? 'danger' : 'info'}">Indexer: ${ix.phase}</span>
      <span class="chip">${ix.text_done.toLocaleString()} / ${ix.text_total.toLocaleString()} files read</span>
      <span class="chip">Database ${fmtSize(data.db_bytes)}</span>
      <span class=${'chip ' + (data.access.error ? 'danger' : 'ok')} title=${data.access.error || ''}>FileBrowser access: ${data.access.error ? 'cannot read' : `${data.access.users} users, ${data.access.rules} rules`}</span>
      ${data.last_scan ? html`<span class="chip">Last scan ${new Date(data.last_scan.at * 1000).toLocaleString()}</span>` : null}
    </div>
    ${ix.error ? html`<div class="banner danger">${ix.error}</div>` : null}
    <div class="scroll-x"><table class="tbl"><thead><tr><th>Collection</th><th>Files</th><th>Text indexed</th><th>Pending</th><th>Unreadable</th></tr></thead>
      <tbody>${data.collections.map((c) => html`<tr key=${c.collection}><td>${c.collection}</td><td class="tnum">${c.files.toLocaleString()}</td><td class="tnum">${(c.indexed || 0).toLocaleString()}</td><td class="tnum">${c.pending || 0}</td><td class="tnum">${c.errors || 0}</td></tr>`)}</tbody></table></div>
    <div class="hint">Folders never indexed or served: ${data.excluded.join(', ') || 'none'}. "Unreadable" are mostly scanned PDFs without a text layer; they still appear in the library by name.</div>
    <div class="scroll-x"><table class="tbl"><thead><tr><th>User</th><th>Set up</th><th>Subjects</th><th>Last seen</th></tr></thead>
      <tbody>${data.users.map((u) => html`<tr key=${u.username}><td>${u.display_name || u.username} <span class="muted">(${u.username})</span></td><td>${u.onboarded ? 'yes' : 'no'}</td><td class="tnum">${u.subjects}</td><td>${u.last_seen ? u.last_seen.replace('T', ' ') : ''}</td></tr>`)}</tbody></table></div>
  </div>`;
}

export function Settings() {
  const { me } = useStore();
  const [name, setName] = useState(me.display_name || '');
  const [month, setMonth] = useState(me.settings.session_month || 'May');
  const [year, setYear] = useState(me.settings.session_year || new Date().getFullYear() + 1);
  const [examStart, setExamStart] = useState(me.settings.exam_start || '');
  const [week, setWeek] = useState(me.settings.weekly_minutes || [90, 90, 90, 90, 0, 180, 180]);
  const [confirmText, setConfirmText] = useState('');
  const [busy, setBusy] = useState(false);
  const years = [];
  for (let y = new Date(me.today).getFullYear(); y <= new Date(me.today).getFullYear() + 3; y++) years.push(y);
  if (!years.includes(Number(year))) years.unshift(Number(year));

  const save = async (body, msg) => {
    setBusy(true);
    const res = await attempt(() => api('/api/settings', { method: 'PUT', body }));
    setBusy(false);
    if (!res) return;
    store.set({ me: res.me, issueCount: res.issues.issues.length });
    if (res.replan_suggested) toast((msg || 'Saved.') + ' Re-plan so your schedule uses the new settings.', { ms: 9000, action: { label: 'Re-plan now', run: () => replanNow(true) } });
    else toast(msg || 'Saved.');
  };
  const theme = me.settings.theme || 'auto';
  const setTheme = (t) => { applyTheme(t); save({ theme: t }, 'Appearance saved.'); };
  const removeSubject = async (s) => {
    if (!confirm(`Remove ${s.name}? Its unfinished sessions are deleted; completed work is kept.`)) return;
    const res = await attempt(() => api(`/api/subjects/${encodeURIComponent(s.subject)}`, { method: 'DELETE' }));
    if (res) { store.set({ me: res.me }); toast('Subject removed.', { ms: 9000, action: { label: 'Re-plan now', run: () => replanNow(true) } }); }
  };
  const wipe = async () => {
    const res = await attempt(() => api('/api/account/delete', { method: 'POST', body: { confirm: 'DELETE' } }));
    if (res) { toast('Your IB God data was deleted.'); await attempt(refreshMe); location.hash = '#/today'; }
  };

  return html`<div class="page">
    <div class="page-head"><div class="grow"><h1>Settings</h1><div class="sub">Signed in as ${me.display_name} (${me.username}) through the school login.</div></div>
      <a class="btn" href=${me.links.logout}><${Icon} name="logout" size=${16} /> Sign out</a></div>

    <div class="grid two">
      <div class="card stack">
        <div class="card-title"><${Icon} name="user" /><h2>Profile and exams</h2></div>
        <div class="field"><label for="st-name">Name</label><input id="st-name" class="input" maxlength="80" value=${name} onInput=${(e) => setName(e.target.value)} /></div>
        <div class="field"><label>Exam session</label><div class="row wrap">
          <div class="seg">${['May', 'November'].map((m) => html`<button class=${month === m ? 'on' : ''} onClick=${() => setMonth(m)}>${m}</button>`)}</div>
          <div class="seg">${years.map((y) => html`<button class=${Number(year) === y ? 'on' : ''} onClick=${() => setYear(y)}>${y}</button>`)}</div></div></div>
        <div class="field"><label for="st-exam">First exam date (optional)</label><input id="st-exam" class="input" type="date" value=${examStart} onInput=${(e) => setExamStart(e.target.value)} />
          <div class="hint">By default the plan runs to the usual start of the session (27 April or 27 October). Enter your school's first exam date for accuracy. Per-subject dates are set on each subject page.</div></div>
        <button class="btn primary" disabled=${busy} onClick=${() => save({ display_name: name.trim() || null, session_month: month, session_year: Number(year), ...(examStart ? { exam_start: examStart } : { clear_exam_start: true }) }, 'Profile saved.')}>Save</button>
      </div>

      <div class="card stack">
        <div class="card-title"><${Icon} name="clock" /><h2 class="grow">Weekly study time</h2><span class="chip">${fmtHours(week.reduce((a, b) => a + b, 0))}/week</span></div>
        <${WeekEditor} value=${week} onChange=${setWeek} />
        <button class="btn primary" disabled=${busy} onClick=${() => save({ weekly_minutes: week }, 'Study time saved.')}>Save study time</button>
        <div class="hint">For one-off changes (a trip, a free day), tap that day's header in the Plan instead.</div>
      </div>
    </div>

    <div class="card stack">
      <div class="card-title"><${Icon} name="target" /><h2 class="grow">Subjects</h2><a class="btn sm" href="#/setup"><${Icon} name="pen" size=${14} /> Edit subjects, levels and textbooks</a></div>
      ${me.subjects.map((s) => html`<div class="row" key=${s.subject}><a class="grow" href=${'#/subjects/' + encodeURIComponent(s.subject)}>${s.name}</a><span class="chip">${s.level}</span><span class="tnum small">${s.current_grade} → ${s.target_grade}</span>
        <button class="btn ghost icon" aria-label=${'Remove ' + s.name} onClick=${() => removeSubject(s)}><${Icon} name="trash" size=${16} /></button></div>`)}
    </div>

    <div class="grid two">
      <div class="card stack">
        <div class="card-title"><${Icon} name="moon" /><h2>Appearance</h2></div>
        <div class="seg">${[['auto', 'Match device'], ['light', 'Light'], ['dark', 'Dark']].map(([k, n]) => html`<button class=${theme === k ? 'on' : ''} onClick=${() => setTheme(k)}>${n}</button>`)}</div>
        <div class="hint">On a phone, use your browser's "Add to Home Screen" to install IB God like an app.</div>
      </div>
      <div class="card stack">
        <div class="card-title"><${Icon} name="file" /><h2>Your data</h2></div>
        <div class="row wrap"><a class="btn" href="/api/export" download>Download everything (JSON)</a></div>
        <div class="hint">Your plan, grades, chats and submitted drafts are stored only on this server and are visible only to you. Server admins can see that you have an account and when you last used it.</div>
        <hr class="divider" />
        <div class="field"><label for="st-del">Delete all my IB God data</label>
          <div class="row wrap"><input id="st-del" class="input grow" placeholder="Type DELETE to confirm" value=${confirmText} onInput=${(e) => setConfirmText(e.target.value)} />
            <button class="btn danger" disabled=${confirmText !== 'DELETE'} onClick=${wipe}>Delete</button></div>
          <div class="hint">Removes your plan, grades, checklist and progress permanently. Your school login is not affected.</div></div>
      </div>
    </div>

    ${me.is_admin ? html`<${Admin} />` : null}
  </div>`;
}
