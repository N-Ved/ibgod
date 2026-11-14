// Dashboard: what to do today, how the week is going, and what needs attention.
import { html, useState, api, useStore, useLoad, attempt, toast, store, Icon, Bar, Spinner, ErrorBox, fmtMin, fmtDate, fmtHours, pct, plural, subjectClass } from './core.js';
import { TaskCard, IssueRow } from './tasks.js';

export async function replanNow(keepPinned = true) {
  const res = await attempt(() => api('/api/plan/replan', { method: 'POST', body: { keep_pinned: keepPinned } }));
  if (res) {
    store.set({ issueCount: res.issues.length });
    toast(`Plan rebuilt: ${res.summary.tasks} sessions scheduled from today.`);
  }
  return res;
}

function greeting() {
  const h = new Date().getHours();
  return h < 5 ? 'Still up' : h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
}

export function Today() {
  const { me } = useStore();
  const { data, error, reload } = useLoad(() => api('/api/dashboard'), []);
  const [busy, setBusy] = useState(false);
  if (error) return html`<div class="page"><${ErrorBox} error=${error} retry=${reload} /></div>`;
  if (!data) return html`<div class="page"><${Spinner} label="Loading today" /></div>`;
  const st = data.stats;
  const todo = data.today.filter((t) => t.status === 'todo');
  const planned = data.today.filter((t) => t.status !== 'skipped').reduce((a, t) => a + t.minutes, 0);
  const doneMin = data.today.filter((t) => t.status === 'done').reduce((a, t) => a + t.minutes, 0);
  const replan = async () => { setBusy(true); await replanNow(true); setBusy(false); reload(); };
  const first = (me.display_name || '').split(' ')[0];
  const maxUp = Math.max(60, ...data.upcoming.map((u) => Math.max(u.minutes, u.capacity)));

  return html`<div class="page">
    <div class="card hero">
      <div class="row wrap top">
        <div class="grow">
          <div class="muted">${greeting()}${first ? ', ' + first : ''} · ${fmtDate(st.today, { year: true })}</div>
          ${st.days_left > 0 ? html`<div class="big">${st.days_left} days</div><div class="muted">until your ${st.session} exams begin (${fmtDate(st.exam_start, { year: true, day: false })})</div>`
            : html`<div class="big">Exam season</div><div class="muted">Your ${st.session} exams have started. Sleep well, trust your preparation.</div>`}
        </div>
        <div class="row" style=${{ gap: '22px' }}>
          <div class="stat"><b>${st.streak}</b><span class="muted small">day streak</span></div>
          <div class="stat"><b>${fmtHours(st.total.done)}</b><span class="muted small">studied so far</span></div>
        </div>
      </div>
      <div style=${{ marginTop: '14px' }}>
        <div class="row small" style=${{ marginBottom: '5px' }}><span>This week</span><span class="right">${fmtHours(st.week.done)} of ${fmtHours(st.week.planned)}</span></div>
        <${Bar} value=${st.week.done} max=${st.week.planned} />
      </div>
    </div>

    ${data.checkin_due ? html`<div class="banner"><${Icon} name="target" /><div class="grow">It has been a few weeks since you updated your grades. If a test or report changed your predicted grade, update it so the plan stays accurate.</div><a class="btn sm" href="#/subjects">Update grades</a></div>` : null}

    <div class="grid two">
      <div class="stack">
        <div class="card">
          <div class="card-title"><h2 class="grow">Today</h2><span class="muted small">${fmtMin(doneMin)} done of ${fmtMin(planned)}${data.capacity_today ? ` · ${fmtMin(data.capacity_today)} available` : ''}</span></div>
          ${data.today.length ? html`<div class="stack tight">${data.today.map((t) => html`<${TaskCard} key=${t.id} task=${t} today=${st.today} onChanged=${reload} />`)}</div>`
            : html`<div class="empty"><h3>Nothing scheduled today</h3><div>${data.capacity_today ? 'Take the rest, or pull a session forward from the plan.' : 'A day off. Rest is part of the plan.'}</div><a class="btn sm" href="#/plan" style=${{ marginTop: '10px' }}>Open plan</a></div>`}
          ${data.today.length && !todo.length ? html`<div class="banner ok" style=${{ marginTop: '10px' }}><${Icon} name="check" /><div>All done for today. Stop here, or get ahead on tomorrow's first task.</div></div>` : null}
        </div>
        ${data.overdue.length ? html`<div class="card">
          <div class="card-title"><h2 class="grow">Overdue</h2><button class="btn sm primary" disabled=${busy} onClick=${replan}><${Icon} name="refresh" size=${15} /> Re-plan</button></div>
          <div class="hint" style=${{ marginBottom: '8px' }}>Tick off what you actually did. Re-plan spreads everything else over the coming weeks, with no guilt attached.</div>
          <div class="stack tight">${data.overdue.slice(0, 6).map((t) => html`<${TaskCard} key=${t.id} task=${t} today=${st.today} onChanged=${reload} />`)}</div>
          ${data.overdue.length > 6 ? html`<div class="hint" style=${{ marginTop: '8px' }}>and ${data.overdue.length - 6} more.</div>` : null}
        </div>` : null}
      </div>

      <div class="stack">
        ${data.issue_count ? html`<div class="card">
          <div class="card-title"><h2 class="grow">Needs attention</h2><a class="small" href="#/plan">All ${data.issue_count} in plan</a></div>
          <div class="stack tight">${data.issues.slice(0, 3).map((i) => html`<${IssueRow} key=${i.key} issue=${i} onChanged=${reload} />`)}</div>
        </div>` : null}
        <div class="card">
          <div class="card-title"><h2 class="grow">Your subjects</h2><a class="small" href="#/subjects">Open</a></div>
          <div class="stack tight">${data.subjects.map((s) => html`<a class=${'row ' + subjectClass(s.key)} href=${'#/subjects/' + encodeURIComponent(s.key)} style=${{ color: 'inherit' }} key=${s.key}>
            <span class="swatch"></span>
            <span class="grow"><div class="row"><strong class="grow ellipsis">${s.short} <span class="muted small">${s.level}</span></strong><span class="tnum small">${s.current} → ${s.target}</span></div>
              <${Bar} value=${s.done} max=${s.planned} tone="ok" /></span></a>`)}</div>
          ${!data.subjects.length ? html`<div class="hint">No subjects yet. <a href="#/setup">Finish setup</a>.</div>` : null}
        </div>
        ${data.upcoming.length ? html`<div class="card">
          <div class="card-title"><h2 class="grow">Next 7 days</h2><a class="small" href="#/plan">Plan</a></div>
          <div class="stack tight">${data.upcoming.map((u) => html`<div class="row small" key=${u.date}><span style=${{ width: '74px' }}>${fmtDate(u.date)}</span>
            <span class="grow"><${Bar} value=${u.minutes} max=${maxUp} tone=${u.minutes > u.capacity + 15 ? 'danger' : ''} /></span><span class="tnum muted" style=${{ width: '70px', textAlign: 'right' }}>${fmtMin(u.minutes)}</span></div>`)}</div>
        </div>` : null}
        <div class="card">
          <div class="card-title"><${Icon} name="bulb" /><h2 class="grow">Method of the day</h2></div>
          <strong>${data.tip.title}</strong>
          <p class="muted small" style=${{ marginTop: '4px' }}>${data.tip.summary}</p>
          <a class="small" href=${'#/techniques/' + data.tip.id}>How to do it</a>
        </div>
      </div>
    </div>
    ${!data.stats.total.planned ? html`<div class="banner warn"><${Icon} name="alert" /><div class="grow">You have no plan yet.</div><button class="btn sm primary" disabled=${busy} onClick=${replan}>Build my plan</button></div>` : null}
    <div class="hint center">${plural(data.subjects.reduce((a, s) => a + s.todo_tasks, 0), 'session')} left in your plan.</div>
  </div>`;
}
