// Evidence-based study methods: what the research says, turned into steps. The planner is built on these.
import { html, useState, useEffect, useRef, api, useLoad, Icon, Spinner, ErrorBox } from './core.js';

const UTILITY = { high: ['ok', 'Strong evidence'], moderate: ['info', 'Good evidence'], practical: ['primary', 'Practical habit'], low: ['danger', 'Low value'] };

function Technique({ t, open, onToggle }) {
  const ref = useRef(null);
  useEffect(() => { if (open && ref.current) ref.current.scrollIntoView({ block: 'start', behavior: 'smooth' }); }, []);
  const [tone, label] = UTILITY[t.utility] || ['', ''];
  return html`<div class="card" ref=${ref} id=${'t-' + t.id}>
    <div class="row top" role="button" tabindex="0" onClick=${onToggle} onKeyDown=${(e) => { if (e.key === 'Enter') onToggle(); }} style=${{ cursor: 'pointer' }}>
      <div class="grow"><h3>${t.title}</h3><div class="row wrap" style=${{ margin: '5px 0' }}><span class=${'chip ' + tone}>${label}</span><span class="chip">${t.category}</span>${t.minutes !== '—' ? html`<span class="chip">${t.minutes}</span>` : null}</div>
        <p class="muted small">${t.summary}</p></div>
      <${Icon} name=${open ? 'down' : 'right'} />
    </div>
    ${open ? html`<div class="stack tight">
      <div><div class="section-label">How to do it</div><ol>${t.how.map((h) => html`<li>${h}</li>`)}</ol></div>
      <div><div class="section-label">When</div><div>${t.when}</div></div>
      <div><div class="section-label">Watch out for</div><ul>${t.pitfalls.map((h) => html`<li>${h}</li>`)}</ul></div>
      <div><div class="section-label">Evidence</div><ul class="small">${t.sources.map((s) => html`<li><a href=${s.url} target="_blank" rel="noopener noreferrer">${s.title}</a></li>`)}</ul></div>
    </div>` : null}
  </div>`;
}

export function Techniques({ focus }) {
  const { data, error, reload } = useLoad(() => api('/api/techniques'), []);
  const [open, setOpen] = useState(focus || null);
  useEffect(() => { if (focus) setOpen(focus); }, [focus]);
  if (error) return html`<div class="page"><${ErrorBox} error=${error} retry=${reload} /></div>`;
  if (!data) return html`<div class="page"><${Spinner} label="Loading study methods" /></div>`;
  const cats = [];
  for (const t of data.techniques) { let c = cats.find((x) => x.name === t.category); if (!c) { c = { name: t.category, items: [] }; cats.push(c); } c.items.push(t); }
  return html`<div class="page">
    <div class="page-head"><div class="grow"><h1>Study methods that work</h1><div class="sub">What decades of learning research say, turned into steps. Your plan is built on these. Each card links to its evidence.</div></div>
</div>
    <div class="banner"><${Icon} name="bulb" /><div>The short version: <strong>test yourself instead of re-reading, spread it out instead of cramming, mix topics, sit timed papers and study every lost mark, and sleep.</strong></div></div>
    ${cats.map((c) => html`<div class="stack tight" key=${c.name}><div class="section-label">${c.name}</div>
      ${c.items.map((t) => html`<${Technique} key=${t.id} t=${t} open=${open === t.id} onToggle=${() => setOpen(open === t.id ? null : t.id)} />`)}</div>`)}
    <div class="card"><div class="card-title"><h2>What each grade needs</h2></div>
      ${[3, 4, 5, 6].map((g) => { const b = data.bands[String(g)]; return html`<div class="step" key=${g}><div class="step-num">${g}→${g + 1}</div><div><strong>${b.title}</strong><div class="small muted">${b.focus}</div></div></div>`; })}
      <div class="hint">Open a subject to see the full path for your own grades.</div></div>
  </div>`;
}
