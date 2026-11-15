// First-run setup (and "edit my setup" later): session, subjects, grades, textbooks, weekly time.
import { html, useState, useEffect, useMemo, api, store, useStore, attempt, toast, Icon, GradePick, Spinner, DAYS, fmtHours, go, refreshMe } from './core.js';

const PRESETS = {
  Light: [45, 45, 45, 45, 0, 90, 90],
  Steady: [90, 90, 90, 90, 0, 180, 180],
  Intensive: [150, 120, 150, 120, 0, 270, 210],
};
const STEPS = ['Exams', 'Subjects', 'Grades', 'Taught so far', 'Textbooks', 'Time', 'Review'];

function defaultSession(today) {
  const d = new Date(today);
  const y = d.getFullYear(), m = d.getMonth() + 1;
  return m <= 2 ? { month: 'May', year: y } : m <= 8 ? { month: 'November', year: y } : { month: 'May', year: y + 1 };
}

export function WeekEditor({ value, onChange }) {
  const total = value.reduce((a, b) => a + b, 0);
  const bump = (i, d) => onChange(value.map((v, j) => (j === i ? Math.max(0, Math.min(720, v + d)) : v)));
  return html`<div class="stack tight">
    <div class="row wrap">${Object.entries(PRESETS).map(([name, v]) => html`<button type="button" class=${'btn sm' + (JSON.stringify(v) === JSON.stringify(value) ? ' primary' : '')} onClick=${() => onChange([...v])}>${name} · ${fmtHours(v.reduce((a, b) => a + b, 0))}/week</button>`)}</div>
    <div class="daygrid">${DAYS.map((d, i) => html`<div class="d" key=${d}>
      <b>${d}</b>
      <div class="stepper"><button type="button" aria-label=${`More time on ${d}`} onClick=${() => bump(i, 30)}>+</button>
        <span class="tnum small">${value[i] ? fmtHours(value[i]) : 'off'}</span>
        <button type="button" aria-label=${`Less time on ${d}`} onClick=${() => bump(i, -30)}>−</button></div>
    </div>`)}</div>
    <div class="hint">Total: <strong>${fmtHours(total)} per week</strong> outside lessons. Be honest: a plan you can keep beats an ambitious one you abandon. Leave at least one day lighter or off.</div>
  </div>`;
}

export function SubjectPicker({ catalog, selected, onToggle, onAddCustom }) {
  const [q, setQ] = useState('');
  const [custom, setCustom] = useState('');
  const needle = q.trim().toLowerCase();
  const groups = useMemo(() => {
    const g = {};
    for (const s of catalog) {
      if (needle && !(s.name.toLowerCase().includes(needle) || s.short.toLowerCase().includes(needle))) continue;
      (g[s.group] = g[s.group] || { name: s.group_name, items: [] }).items.push(s);
    }
    return g;
  }, [catalog, needle]);
  const sel = new Set(selected);
  return html`<div class="stack">
    <input class="input" type="search" placeholder="Search subjects, e.g. Physics, Spanish B, Economics" value=${q} onInput=${(e) => setQ(e.target.value)} aria-label="Search subjects" />
    ${Object.keys(groups).sort().map((gk) => {
      const g = groups[gk];
      const anySel = g.items.some((s) => sel.has(s.key));
      const big = g.items.length > 14 && !needle;
      const items = big ? g.items.filter((s) => sel.has(s.key) || s.resources > 150) : g.items;
      return html`<div key=${gk}>
        <div class="section-label">Group ${gk} · ${g.name}${anySel ? ' ✓' : ''}</div>
        <div class="pick-list">${items.map((s) => html`<button type="button" key=${s.key} class=${'pick' + (sel.has(s.key) ? ' on' : '')} onClick=${() => onToggle(s)}>
          <span class="grow"><div><strong>${s.name}</strong></div><div class="hint">${s.levels.join(' / ')}${s.resources ? ` · ${s.resources.toLocaleString()} resources` : ''}</div></span>
          ${sel.has(s.key) ? html`<${Icon} name="check" />` : null}</button>`)}</div>
        ${big ? html`<div class="hint">Showing the most common ${g.name.toLowerCase()} courses. Search above for any other language.</div>` : null}
      </div>`;
    })}
    ${!Object.keys(groups).length ? html`<div class="hint">No subject matches "${q}". Add it below.</div>` : null}
    <div class="row wrap">
      <input class="input grow" placeholder="Subject not listed? Type its name" maxlength="58" value=${custom} onInput=${(e) => setCustom(e.target.value)} />
      <button type="button" class="btn" disabled=${custom.trim().length < 2} onClick=${() => { onAddCustom(custom.trim()); setCustom(''); }}>Add</button>
    </div>
  </div>`;
}

export function Onboarding({ editing }) {
  const { me } = useStore();
  const base = defaultSession(me.today);
  const [step, setStep] = useState(0);
  const [catalog, setCatalog] = useState(null);
  const [name, setName] = useState(me.display_name || '');
  const [month, setMonth] = useState(me.settings.session_month || base.month);
  const [year, setYear] = useState(me.settings.session_year || base.year);
  const [subs, setSubs] = useState(() => me.subjects.map((s) => ({ subject: s.subject, name: s.name, levels: ['HL', 'SL'], level: s.level, current_grade: s.current_grade, target_grade: s.target_grade,
    textbook_id: s.textbook_id, textbook_other: s.textbook_other || '', exam_date: s.exam_date })));
  const [week, setWeek] = useState(me.settings.weekly_minutes || PRESETS.Steady);
  const [books, setBooks] = useState({});
  const [units, setUnits] = useState({});
  const [busy, setBusy] = useState(false);

  useEffect(() => { attempt(() => api('/api/catalog')).then((d) => d && setCatalog(d.subjects)); }, []);
  useEffect(() => {
    if (step !== 3) return;
    subs.forEach((s) => {
      const k = s.subject + '|' + s.level;
      if (units[k] !== undefined || s.subject.startsWith('custom:')) return;
      api(`/api/catalog/units?subject=${encodeURIComponent(s.subject)}&level=${s.level}`).then((d) => setUnits((u) => ({ ...u, [k]: d.units }))).catch(() => setUnits((u) => ({ ...u, [k]: [] })));
    });
  }, [step, subs.length]);
  useEffect(() => {
    if (step !== 4) return;
    subs.forEach((s) => {
      const k = s.subject + '|' + s.level;
      if (books[k] !== undefined || s.subject.startsWith('custom:')) return;
      api(`/api/textbooks?subject=${encodeURIComponent(s.subject)}&level=${s.level}`).then((d) => setBooks((b) => ({ ...b, [k]: d.textbooks }))).catch(() => setBooks((b) => ({ ...b, [k]: [] })));
    });
  }, [step, subs.length]);

  const update = (key, patch) => setSubs((list) => list.map((s) => (s.subject === key ? { ...s, ...patch } : s)));
  const toggle = (c) => setSubs((list) => {
    if (list.some((s) => s.subject === c.key)) return list.filter((s) => s.subject !== c.key);
    if (list.length >= 10) { toast('You can add up to 10 subjects.', { error: true }); return list; }
    return [...list, { subject: c.key, name: c.name, levels: c.levels, level: c.levels.includes('HL') && list.filter((s) => s.level === 'HL').length < 3 ? 'HL' : c.levels[c.levels.length - 1], current_grade: 4, target_grade: 6, textbook_id: null, textbook_other: '' }];
  });
  const addCustom = (label) => {
    const clean = label.replace(/[^A-Za-z0-9 &'()+.,-]/g, '').trim().slice(0, 58);
    if (clean.length < 2) return;
    toggle({ key: 'custom:' + clean, name: clean, levels: ['HL', 'SL'] });
  };
  const years = [];
  for (let y = new Date(me.today).getFullYear(); y <= new Date(me.today).getFullYear() + 3; y++) years.push(y);
  const hl = subs.filter((s) => s.level === 'HL').length;
  const canNext = step === 1 ? subs.length > 0 : step === 5 ? week.reduce((a, b) => a + b, 0) >= 60 : true;

  const submit = async () => {
    setBusy(true);
    const body = { display_name: name.trim() || null, session_month: month, session_year: Number(year), weekly_minutes: week, exam_start: me.settings.exam_start || null,
      subjects: subs.map((s) => ({ subject: s.subject, level: s.level, current_grade: s.current_grade, target_grade: Math.max(s.target_grade, s.current_grade), textbook_id: s.textbook_id || null,
        textbook_other: s.textbook_other || null, exam_date: s.exam_date || null, covered_units: s.covered_units && s.covered_units.length ? s.covered_units : null })) };
    const res = await attempt(() => api('/api/setup', { method: 'POST', body }));
    setBusy(false);
    if (!res) return;
    store.set({ me: res.me, issueCount: res.issues.issues.length });
    toast(`Your plan is ready: ${res.plan.tasks} study sessions scheduled.`);
    go('#/today');
  };

  const pages = [
    () => html`<div class="stack">
      <div><h1>${editing ? 'Update your setup' : `Welcome to IB God${me.display_name ? ', ' + me.display_name.split(' ')[0] : ''}`}</h1>
        <p class="muted">${editing ? 'Change anything below. Your completed work is kept and the rest of the plan is rebuilt.' : 'Six quick steps and you will have a personal study plan built from everything in the library and from what research says works.'}</p></div>
      <div class="card stack">
        <div class="field"><label for="ob-name">What should we call you?</label><input id="ob-name" class="input" maxlength="80" value=${name} onInput=${(e) => setName(e.target.value)} /></div>
        <div class="field"><label>When are your final exams?</label>
          <div class="row wrap"><div class="seg">${['May', 'November'].map((m) => html`<button type="button" class=${month === m ? 'on' : ''} onClick=${() => setMonth(m)}>${m}</button>`)}</div>
          <div class="seg">${years.map((y) => html`<button type="button" class=${Number(year) === y ? 'on' : ''} onClick=${() => setYear(y)}>${y}</button>`)}</div></div>
          <div class="hint">The plan counts down to the first exams of the ${month} ${year} session (late ${month === 'May' ? 'April' : 'October'}). You can set exact dates per subject later.</div></div>
      </div></div>`,
    () => html`<div class="stack">
      <div><h1>Which subjects do you take?</h1><p class="muted">Pick all of them. ${subs.length ? html`<strong>${subs.length} selected</strong>${hl ? `, ${hl} at HL` : ''}.` : 'Most diploma students take six: three at HL and three at SL.'}</p></div>
      ${subs.length ? html`<div class="card stack tight">${subs.map((s) => html`<div class="row wrap" key=${s.subject}>
        <strong class="grow">${s.name}</strong>
        <div class="seg">${(s.levels || ['HL', 'SL']).map((l) => html`<button type="button" class=${s.level === l ? 'on' : ''} onClick=${() => update(s.subject, { level: l })}>${l}</button>`)}</div>
        <button type="button" class="btn ghost icon" aria-label=${'Remove ' + s.name} onClick=${() => setSubs(subs.filter((x) => x.subject !== s.subject))}><${Icon} name="x" /></button></div>`)}</div>` : null}
      ${catalog ? html`<${SubjectPicker} catalog=${catalog} selected=${subs.map((s) => s.subject)} onToggle=${toggle} onAddCustom=${addCustom} />` : html`<${Spinner} label="Loading subjects" />`}
    </div>`,
    () => html`<div class="stack">
      <div><h1>Where are you now, and where do you want to be?</h1><p class="muted">Use your latest predicted grade or report grade. Honest numbers make a better plan; you can update them any time.</p></div>
      ${subs.map((s) => html`<div class="card stack tight" key=${s.subject}>
        <div class="row"><strong class="grow">${s.name}</strong><span class="chip">${s.level}</span></div>
        <div class="row wrap"><span class="label" style=${{ minWidth: '108px' }}>Current grade</span><${GradePick} value=${s.current_grade} onChange=${(g) => update(s.subject, { current_grade: g, target_grade: Math.max(g, s.target_grade) })} /></div>
        <div class="row wrap"><span class="label" style=${{ minWidth: '108px' }}>Target grade</span><${GradePick} value=${s.target_grade} min=${s.current_grade} onChange=${(g) => update(s.subject, { target_grade: g })} /></div>
        ${s.target_grade - s.current_grade >= 3 ? html`<div class="hint">A jump of ${s.target_grade - s.current_grade} grades is a big ask. The plan will give this subject a lot of time; consider whether that is fair to your other subjects.</div>` : null}
      </div>`)}
    </div>`,
    () => html`<div class="stack">
      <div><h1>What has your class already taught?</h1><p class="muted">Tick the units you have covered in class so far. Your plan starts them with a short consolidation and practice instead of teaching them from scratch. Skip this if you are just starting the course. You can fine-tune each topic later in the subject's checklist.</p></div>
      ${subs.map((s) => { const list = units[s.subject + '|' + s.level]; const chosen = new Set(s.covered_units || []);
        const toggle = (code) => update(s.subject, { covered_units: chosen.has(code) ? [...chosen].filter((c) => c !== code) : [...chosen, code] });
        return html`<div class="card stack tight" key=${s.subject}>
        <div class="row"><strong class="grow">${s.name}</strong><span class="chip">${s.level}</span>
          ${list && list.length ? html`<button type="button" class="btn sm ghost" onClick=${() => update(s.subject, { covered_units: chosen.size === list.length ? [] : list.map((u) => u.code) })}>${chosen.size === list.length ? 'Clear' : 'All'}</button>` : null}</div>
        ${s.subject.startsWith('custom:') ? html`<div class="hint">Set this one up in its checklist after setup.</div>` : list === undefined ? html`<div class="hint"><span class="spinner"></span> Loading units…</div>` :
          html`<div class="pick-list">${list.map((u) => html`<button type="button" key=${u.code} class=${'pick' + (chosen.has(u.code) ? ' on' : '')} aria-pressed=${chosen.has(u.code)} onClick=${() => toggle(u.code)}>
            <span class="grow"><div><strong>${u.name}</strong></div><div class="hint">${u.topics} topic${u.topics === 1 ? '' : 's'}</div></span>${chosen.has(u.code) ? html`<${Icon} name="check" />` : null}</button>`)}</div>`}
      </div>`; })}
    </div>`,
    () => html`<div class="stack">
      <div><h1>Which textbooks do you use in class?</h1><p class="muted">The plan will point you to the right pages of your own book. Skip any you are unsure about.</p></div>
      ${subs.map((s) => { const list = books[s.subject + '|' + s.level]; return html`<div class="card stack tight" key=${s.subject}>
        <div class="row"><strong class="grow">${s.name}</strong><span class="chip">${s.level}</span></div>
        ${s.subject.startsWith('custom:') ? null : list === undefined ? html`<div class="hint"><span class="spinner"></span> Looking in the library…</div>` : list.length ? html`
          <select class="input" aria-label=${'Textbook for ' + s.name} value=${s.textbook_id || ''} onChange=${(e) => update(s.subject, { textbook_id: e.target.value ? Number(e.target.value) : null })}>
            <option value="">Not sure / none of these</option>
            ${list.map((b) => html`<option value=${b.id}>${b.title}</option>`)}
          </select>` : html`<div class="hint">No textbooks for this subject in the library yet.</div>`}
        <input class="input" placeholder="Using a different book? Type its name (optional)" maxlength="160" value=${s.textbook_other || ''} onInput=${(e) => update(s.subject, { textbook_other: e.target.value })} />
      </div>`; })}
    </div>`,
    () => html`<div class="stack">
      <div><h1>How much time can you study each day?</h1><p class="muted">Outside lessons and homework you already have to do. You can change single days later (holidays, trips, busy weeks).</p></div>
      <div class="card"><${WeekEditor} value=${week} onChange=${setWeek} /></div>
    </div>`,
    () => html`<div class="stack">
      <div><h1>Ready to build your plan</h1><p class="muted">Check the summary. You can change everything later in Settings, and re-plan whenever life gets in the way.</p></div>
      <div class="card stack tight">
        <div class="row"><span class="muted grow">Exam session</span><strong>${month} ${year}</strong></div>
        <div class="row"><span class="muted grow">Study time</span><strong>${fmtHours(week.reduce((a, b) => a + b, 0))} per week</strong></div>
        <hr class="divider" />
        ${subs.map((s) => html`<div class="row" key=${s.subject}><span class="grow">${s.name} <span class="chip">${s.level}</span>${s.covered_units && s.covered_units.length ? html` <span class="chip ok">${s.covered_units.length} unit${s.covered_units.length === 1 ? '' : 's'} taught</span>` : null}</span><strong class="tnum">${s.current_grade} → ${Math.max(s.target_grade, s.current_grade)}</strong></div>`)}
      </div>
      <div class="banner"><${Icon} name="bulb" /><div>The plan covers each topic once, practises it with real exam questions, brings it back at growing intervals (spaced retrieval), and moves to timed past papers as exams approach. Subjects with bigger grade gaps and HL subjects get more time.</div></div>
    </div>`,
  ];

  return html`<div class="wizard">
    <div class="row"><span class="brand-mark"><${Icon} name="spark" size=${18} /></span><strong>IB God</strong><span class="grow"></span><span class="hint">Step ${step + 1} of ${STEPS.length}: ${STEPS[step]}</span>
      ${editing ? html`<a class="btn sm" href="#/settings">Cancel</a>` : null}</div>
    <div class="wizard-steps">${STEPS.map((_, i) => html`<i class=${i <= step ? 'on' : ''}></i>`)}</div>
    ${pages[step]()}
    <div class="wizard-foot"><div>
      ${step > 0 ? html`<button class="btn" onClick=${() => { setStep(step - 1); window.scrollTo(0, 0); }}><${Icon} name="left" /> Back</button>` : null}
      <span class="grow"></span>
      ${step < STEPS.length - 1 ? html`<button class="btn primary" disabled=${!canNext} onClick=${() => { setStep(step + 1); window.scrollTo(0, 0); }}>Continue <${Icon} name="right" /></button>`
        : html`<button class="btn primary" disabled=${busy || !subs.length} onClick=${submit}>${busy ? html`<span class="spinner"></span> Building…` : editing ? 'Save and rebuild plan' : 'Create my plan'}</button>`}
    </div></div>
  </div>`;
}

export { refreshMe };
