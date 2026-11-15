// Shared building blocks: API client, tiny store, formatting helpers and common components.
import { html, render, useState, useEffect, useRef, useMemo, useCallback } from '/vendor/preact-htm.js';
export { html, render, useState, useEffect, useRef, useMemo, useCallback };

// ───────── API ─────────
export class ApiError extends Error {
  constructor(status, detail) { super(detail); this.status = status; }
}

export async function api(path, { method = 'GET', body, form, signal, raw } = {}) {
  const headers = { 'X-IBGod': '1', Accept: 'application/json' };
  let payload;
  if (form) payload = form;
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body); }
  let res;
  try {
    res = await fetch(path, { method, headers, body: payload, credentials: 'same-origin', redirect: 'manual', signal });
  } catch (e) {
    if (e.name === 'AbortError') throw e;
    throw new ApiError(0, 'Could not reach the server. Check your connection and try again.');
  }
  // Authelia answers an expired session with a redirect (page loads) or 401 (background requests).
  if (res.type === 'opaqueredirect' || res.status === 401) {
    store.set({ sessionLost: true });
    throw new ApiError(401, 'Your session has expired.');
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const j = await res.json();
      if (typeof j.detail === 'string') detail = j.detail;
      else if (Array.isArray(j.detail)) detail = j.detail.map((d) => d.msg || '').filter(Boolean).join('; ') || detail;
    } catch { /* not JSON */ }
    throw new ApiError(res.status, detail);
  }
  if (raw) return res;
  return res.status === 204 ? null : res.json();
}

// ───────── store ─────────
const listeners = new Set();
let state = { me: null, toasts: [], sessionLost: false, created: null, media: null, issueCount: 0 };
export const store = {
  get: () => state,
  set(patch) { state = { ...state, ...patch }; listeners.forEach((l) => l(state)); },
  subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
};
export function useStore() {
  const [s, setS] = useState(state);
  useEffect(() => {
    // Effects run after paint. Anything stored between the first render and now (a fast /api/me reply) must not be missed.
    if (s !== state) setS(state);
    return store.subscribe(setS);
  }, []);
  return s;
}

let toastId = 0;
export function toast(text, { error = false, action, ms = 4500 } = {}) {
  const id = ++toastId;
  store.set({ toasts: [...state.toasts, { id, text, error, action }].slice(-2) });
  setTimeout(() => store.set({ toasts: state.toasts.filter((t) => t.id !== id) }), error ? 7000 : ms);
}
export function fail(e) {
  if (e && e.name === 'AbortError') return;
  if (e && e.status === 401) return;
  toast((e && e.message) || 'Something went wrong.', { error: true });
}

/** Run an async action, showing errors as toasts. Returns undefined on failure. */
export async function attempt(fn) {
  try { return await fn(); } catch (e) { fail(e); return undefined; }
}

export function useLoad(loader, deps = []) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    const ctl = new AbortController();
    setError(null);
    loader(ctl.signal).then((d) => { if (alive) setData(d); }).catch((e) => { if (alive && e.name !== 'AbortError') setError(e); });
    return () => { alive = false; ctl.abort(); };
  }, [...deps, tick]);
  return { data, error, setData, reload: () => setTick((t) => t + 1) };
}

// ───────── formatting ─────────
export const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
export const DAYS_LONG = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function parseISO(s) { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); }
export function toISO(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; }
export function addDays(iso, n) { const d = parseISO(iso); d.setDate(d.getDate() + n); return toISO(d); }
export function weekday(iso) { return (parseISO(iso).getDay() + 6) % 7; }
export function mondayOf(iso) { return addDays(iso, -weekday(iso)); }
export function fmtDate(iso, { year = false, day = true } = {}) {
  const d = parseISO(iso);
  return `${day ? DAYS[weekday(iso)] + ' ' : ''}${d.getDate()} ${MONTHS[d.getMonth()]}${year ? ' ' + d.getFullYear() : ''}`;
}
export function daysBetween(a, b) { return Math.round((parseISO(b) - parseISO(a)) / 86400000); }
export function fmtMin(m) {
  m = Math.round(m || 0);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60), r = m % 60;
  return r ? `${h} h ${r} min` : `${h} h`;
}
export function fmtHours(m) { const h = (m || 0) / 60; return (Math.round(h * 10) / 10).toString().replace(/\.0$/, '') + ' h'; }
export function fmtSize(b) { if (!b) return ''; return b > 1e9 ? (b / 1e9).toFixed(1) + ' GB' : b > 1e6 ? Math.round(b / 1e6) + ' MB' : Math.max(1, Math.round(b / 1e3)) + ' KB'; }
export function pct(a, b) { return b > 0 ? Math.max(0, Math.min(100, Math.round((100 * a) / b))) : 0; }
export function plural(n, word, many) { return `${n} ${n === 1 ? word : (many || word + 's')}`; }

export function subjectClass(key) {
  const subs = (state.me && state.me.subjects) || [];
  const i = subs.findIndex((s) => s.subject === key);
  return i < 0 ? 's8' : `s${i % 10}`;
}
export function subjectShort(key) {
  const s = ((state.me && state.me.subjects) || []).find((x) => x.subject === key);
  return s ? s.short : '';
}

// ───────── icons ─────────
const ICONS = {
  home: 'M3 11.5 12 4l9 7.5M5.5 10v9.5h13V10',
  calendar: 'M4 6.5h16v13H4zM4 10.5h16M8 3.5v4M16 3.5v4',
  book: 'M5 4.5h10a3 3 0 0 1 3 3v12H8a3 3 0 0 1-3-3zM5 16.5a3 3 0 0 1 3-3h10',
  layers: 'M12 4 3.5 8.5 12 13l8.5-4.5zM3.5 12.5 12 17l8.5-4.5M3.5 16.5 12 21l8.5-4.5',
  search: 'M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13zM15.5 15.5 20 20',
  chat: 'M4.5 5.5h15v10.5h-8L7 19.5V16H4.5z',
  pen: 'M4.5 19.5l1-4 10-10 3 3-10 10zM13.5 7.5l3 3',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM12 3.5v2.5M12 18v2.5M3.5 12H6M18 12h2.5M6 6l1.8 1.8M16.2 16.2 18 18M6 18l1.8-1.8M16.2 7.8 18 6',
  check: 'M5 12.5l4.5 4.5L19 7.5',
  x: 'M6 6l12 12M18 6 6 18',
  plus: 'M12 5v14M5 12h14',
  left: 'M14.5 6 8.5 12l6 6',
  right: 'M9.5 6l6 6-6 6',
  down: 'M6 9.5l6 6 6-6',
  alert: 'M12 4 2.5 20h19zM12 10v4.5M12 17.2v.3',
  clock: 'M12 20.5a8.5 8.5 0 1 0 0-17 8.5 8.5 0 0 0 0 17zM12 7.5V12l3 2',
  play: 'M8 5.5v13l11-6.5z',
  file: 'M7 3.5h7l4 4v13H7zM14 3.5v4h4',
  link: 'M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1',
  star: 'M12 4l2.5 5.2 5.7.8-4.1 4 1 5.6L12 17l-5.1 2.6 1-5.6-4.1-4 5.7-.8z',
  trash: 'M5 7h14M9.5 7V4.5h5V7M7 7l1 12.5h8L17 7M10.5 10.5v6M13.5 10.5v6',
  refresh: 'M19.5 12a7.5 7.5 0 1 1-2.2-5.3M19.5 4.5v4h-4',
  pin: 'M9 4.5h6l-1 5 3 3H7l3-3zM12 12.5v7',
  logout: 'M14 4.5H6v15h8M10.5 12h9M16.5 8.5 20 12l-3.5 3.5',
  more: 'M5.5 12h.01M12 12h.01M18.5 12h.01',
  target: 'M12 20.5a8.5 8.5 0 1 0 0-17 8.5 8.5 0 0 0 0 17zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 12h.01',
  spark: 'M12 3.5l1.8 5.2L19 10.5l-5.2 1.8L12 17.5l-1.8-5.2L5 10.5l5.2-1.8zM18.5 15.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z',
  upload: 'M12 16V5M7.5 9.5 12 5l4.5 4.5M5 19.5h14',
  video: 'M4 6.5h11v11H4zM15 10.5l5-3v9l-5-3',
  audio: 'M5 10v4h3.5l4.5 4V6l-4.5 4zM16 9a4 4 0 0 1 0 6',
  bulb: 'M9 17.5h6M10 20.5h4M12 3.5a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2h5c0-.8.4-1.5 1-2A6 6 0 0 0 12 3.5z',
  user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4.5 20a7.5 7.5 0 0 1 15 0',
  moon: 'M19.5 14.5A8 8 0 0 1 9.5 4.5a8 8 0 1 0 10 10z',
  grid: 'M4.5 4.5h6v6h-6zM13.5 4.5h6v6h-6zM4.5 13.5h6v6h-6zM13.5 13.5h6v6h-6z',
};
export function Icon({ name, size = 20 }) {
  return html`<svg width=${size} height=${size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d=${ICONS[name] || ICONS.file} /></svg>`;
}

// ───────── small components ─────────
export function Spinner({ label }) { return html`<div class="empty"><span class="spinner"></span>${label ? html` <span>${label}</span>` : null}</div>`; }
export function ErrorBox({ error, retry }) {
  return html`<div class="banner danger"><${Icon} name="alert" /><div class="grow">${(error && error.message) || 'Something went wrong.'}</div>${retry ? html`<button class="btn sm" onClick=${retry}>Try again</button>` : null}</div>`;
}
export function Modal({ title, onClose, wide, children, footer }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose && onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);
  return html`<div class="overlay" onMouseDown=${(e) => { if (e.target === e.currentTarget && onClose) onClose(); }}>
    <div class=${'modal' + (wide ? ' wide' : '')} role="dialog" aria-modal="true" aria-label=${title}>
      <div class="modal-head"><h2 class="grow">${title}</h2>${onClose ? html`<button class="btn ghost icon" aria-label="Close" onClick=${onClose}><${Icon} name="x" /></button>` : null}</div>
      ${children}
      ${footer ? html`<div class="modal-foot">${footer}</div>` : null}
    </div>
  </div>`;
}
export function Bar({ value, max, tone }) {
  return html`<div class=${'bar ' + (tone || '')} role="progressbar" aria-valuenow=${pct(value, max)} aria-valuemin="0" aria-valuemax="100"><i style=${{ width: pct(value, max) + '%' }}></i></div>`;
}
export function GradePick({ value, onChange, min = 1 }) {
  return html`<div class="grade-pick" role="radiogroup">${[1, 2, 3, 4, 5, 6, 7].map((g) => html`<button type="button" role="radio" aria-checked=${value === g} disabled=${g < min} class=${value === g ? 'on' : ''} onClick=${() => onChange(g)}>${g}</button>`)}</div>`;
}
export function Confidence({ value, onChange }) {
  const labels = ['', 'Lost', 'Shaky', 'OK', 'Good', 'Could teach it'];
  return html`<div class="dots" title="How confident are you? 1 = lost, 5 = could teach it">${[1, 2, 3, 4, 5].map((n) => html`<button type="button" aria-label=${`Confidence ${n}: ${labels[n]}`} class=${value === n ? `on c${n}` : ''} onClick=${() => onChange(value === n ? 0 : n)}>${n}</button>`)}</div>`;
}
export function Snippet({ text }) {
  if (!text) return null;
  const parts = text.split(/(\[\[.*?\]\])/g);
  return html`<span>${parts.map((p) => (p.startsWith('[[') && p.endsWith(']]') ? html`<mark>${p.slice(2, -2)}</mark>` : p))}</span>`;
}

const KIND_LABEL = {
  textbook: 'Textbook', revision_guide: 'Revision guide', workbook: 'Workbook', answers: 'Answers', coursework_guide: 'Coursework guide', extra: 'Extras',
  question_paper: 'Question paper', markscheme: 'Markscheme', booklet: 'Booklet', audio: 'Audio', topic_questions: 'Topic questions', qb_home: 'Question bank',
  notes: 'Notes', video: 'Video', page: 'Web page', site_home: 'Study site', subject_guide: 'Subject guide', data_booklet: 'Data booklet', grade_boundaries: 'Grade boundaries',
  exam_schedule: 'Exam schedule', grade_descriptors: 'Grade descriptors', text_types: 'Text types', case_study: 'Case study', ee_exemplar: 'EE exemplar',
  ia_exemplar: 'IA exemplar', tok_exemplar: 'TOK exemplar', lit_guide: 'Literature guide', literary_term: 'Literary term', worksheet: 'Worksheet',
  admissions_test: 'Admissions test', official_doc: 'Official document', document: 'Document', calculator_rules: 'Calculator rules', exam_conduct: 'Exam rules',
  teacher_support: 'Support material', paper_samples: 'Paper samples',
};
export function kindLabel(k) { return KIND_LABEL[k] || (k || 'File').replace(/_/g, ' '); }
function resIcon(r) {
  if (r.ext === 'mp4' || r.ext === 'mov' || r.kind === 'video') return 'video';
  if (r.ext === 'mp3' || r.kind === 'audio') return 'audio';
  if (r.kind === 'page' || r.kind === 'site_home' || r.kind === 'qb_home' || r.kind === 'topic_questions') return 'link';
  if (r.collection === 'books') return 'book';
  return 'file';
}
export function isMedia(r) { return ['mp4', 'mov', 'webm', 'mp3', 'm4a'].includes(r.ext); }

export function ResourceLink({ r, sub, extra }) {
  const meta = [kindLabel(r.kind), r.level && r.level !== 'HLSL' ? r.level : null, r.publisher, r.year && !/\b(19|20)\d\d\b/.test(r.title) ? r.year : null,
    r.page ? `page ${r.page}` : null, r.pages && r.kind === 'topic_questions' ? plural(r.pages, 'question') : null, r.ext && !['pdf', 'html', 'htm'].includes(r.ext) ? r.ext.toUpperCase() : null]
    .filter(Boolean).join(' · ');
  const open = (e) => { if (isMedia(r)) { e.preventDefault(); store.set({ media: r }); } };
  return html`<a class="res" href=${r.url} target="_blank" rel="noopener" onClick=${open}>
    <span class="res-ico"><${Icon} name=${resIcon(r)} size=${16} /></span>
    <span class="grow">
      <div class="res-t">${r.title}</div>
      <div class="res-s">${meta}${r.syllabus === 'legacy' ? html` · <span class="chip warn" title=${r.note || ''}>older syllabus</span>` : null}${sub ? html` · ${sub}` : null}</div>
      ${r.snippet ? html`<div class="res-s"><${Snippet} text=${r.snippet} /></div>` : null}
    </span>
    ${extra || null}
  </a>`;
}
export function ResourceGroup({ title, items, empty }) {
  if (!items || !items.length) return empty ? html`<div><div class="section-label">${title}</div><div class="hint">${empty}</div></div>` : null;
  return html`<div><div class="section-label">${title}</div><div class="res-list">${items.map((r) => html`<${ResourceLink} key=${r.id + ':' + (r.page || 0)} r=${r} />`)}</div></div>`;
}

// The local model sometimes writes formulas in LaTeX. Turn the common cases into readable Unicode text.
const TEX = { alpha: 'α', beta: 'β', gamma: 'γ', delta: 'δ', Delta: 'Δ', epsilon: 'ε', varepsilon: 'ε', theta: 'θ', lambda: 'λ', mu: 'μ', nu: 'ν', pi: 'π', rho: 'ρ', sigma: 'σ', Sigma: 'Σ', tau: 'τ',
  phi: 'φ', varphi: 'φ', omega: 'ω', Omega: 'Ω', eta: 'η', kappa: 'κ', times: '×', cdot: '·', div: '÷', pm: '±', mp: '∓', approx: '≈', sim: '~', neq: '≠', ne: '≠', leq: '≤', le: '≤', geq: '≥', ge: '≥',
  ll: '≪', gg: '≫', rightarrow: '→', to: '→', leftarrow: '←', Rightarrow: '⇒', implies: '⇒', rightleftharpoons: '⇌', leftrightarrow: '↔', infty: '∞', propto: '∝', circ: '°', degree: '°', partial: '∂',
  int: '∫', sum: 'Σ', quad: ' ', qquad: '  ', ldots: '…', dots: '…', cdots: '⋯', angle: '∠', perp: '⊥', parallel: '∥', in: '∈', forall: '∀', exists: '∃', sin: 'sin', cos: 'cos', tan: 'tan', ln: 'ln', log: 'log',
  lim: 'lim', left: '', right: '', displaystyle: '', big: '', Big: '' };
const SUP = { 0: '⁰', 1: '¹', 2: '²', 3: '³', 4: '⁴', 5: '⁵', 6: '⁶', 7: '⁷', 8: '⁸', 9: '⁹', '+': '⁺', '-': '⁻', n: 'ⁿ' };
const SUB = { 0: '₀', 1: '₁', 2: '₂', 3: '₃', 4: '₄', 5: '₅', 6: '₆', 7: '₇', 8: '₈', 9: '₉', a: 'ₐ', e: 'ₑ', o: 'ₒ', x: 'ₓ', s: 'ₛ', n: 'ₙ', m: 'ₘ', t: 'ₜ', p: 'ₚ', k: 'ₖ', h: 'ₕ', l: 'ₗ', i: 'ᵢ', r: 'ᵣ', u: 'ᵤ', v: 'ᵥ' };
function script(text, map, mark) {
  const chars = [...text];
  if (chars.every((c) => map[c] !== undefined)) return chars.map((c) => map[c]).join('');
  return /^[A-Za-z0-9]+$/.test(text) ? mark + text : `${mark}(${text})`;
}
export function delatex(text) {
  if (!text || !/[\\$^_]/.test(text)) return text || '';
  // Inline maths markers first, while the LaTeX inside them is still recognisable (so "$5 and $10" is left alone).
  let s = text.replace(/\$\$([^$]+)\$\$/g, '$1')
    .replace(/\$([^$\s][^$\n]{0,238}[^$\s]|[^$\s])\$/g, (m, inner) => (/[\\^_=+*/<>-]/.test(inner) || (!/\s/.test(inner) && inner.length <= 10) ? inner : m));
  for (let i = 0; i < 4; i++) s = s.replace(/\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g, (m, a, b) => `(${a})/(${b})`);
  s = s.replace(/\\sqrt\s*\{([^{}]*)\}/g, '√($1)').replace(/\\(?:text|mathrm|mathbf|mathit|operatorname|vec|hat|bar|overline)\s*\{([^{}]*)\}/g, '$1');
  s = s.replace(/\\([A-Za-z]+)/g, (m, name) => (TEX[name] !== undefined ? TEX[name] : name)).replace(/Δ (?=[A-Za-zα-ω])/g, 'Δ');
  s = s.replace(/\\[,;:! ]/g, ' ').replace(/\\([%#&{}_$])/g, '$1');
  s = s.replace(/\^\{([^{}]*)\}/g, (m, a) => script(a, SUP, '^')).replace(/\^(-?[0-9n])/g, (m, a) => script(a, SUP, '^'));
  s = s.replace(/_\{([^{}]*)\}/g, (m, a) => script(a, SUB, '_')).replace(/([A-Za-zα-ωΑ-Ω)])_([0-9]+)/g, (m, base, a) => base + script(a, SUB, '_'))
    .replace(/([A-Za-zα-ωΑ-Ω])_([a-z])(?![A-Za-z0-9])/g, (m, base, a) => base + script(a, SUB, '_'));
  return s.replace(/[{}]/g, '').replace(/ {2,}/g, ' ');
}

/** Minimal, safe Markdown for coach answers: paragraphs, bold, bullet and numbered lists. Builds elements, never HTML strings. */
function inline(text) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((p) => (p.startsWith('**') && p.endsWith('**') && p.length > 4 ? html`<strong>${p.slice(2, -2)}</strong>` : p));
}
export function RichText({ text }) {
  const blocks = [];
  let list = null;
  for (const raw of delatex(text || '').split('\n')) {
    const line = raw.trimEnd();
    const ol = line.match(/^\s*(\d+)[.)]\s+(.*)$/);
    const ul = line.match(/^\s*[-*•]\s+(.*)$/);
    if (ol || ul) {
      const type = ol ? 'ol' : 'ul';
      if (!list || list.type !== type) { list = { type, items: [] }; blocks.push(list); }
      list.items.push(ol ? ol[2] : ul[1]);
    } else if (!line.trim()) {
      list = null;
    } else {
      const h = line.match(/^#{1,4}\s+(.*)$/);
      if (list && /^\s{2,}/.test(raw)) { list.items[list.items.length - 1] += ' ' + line.trim(); continue; }
      list = null;
      blocks.push(h ? { type: 'h', text: h[1] } : { type: 'p', text: line });
    }
  }
  return html`<div>${blocks.map((b) => b.type === 'p' ? html`<p>${inline(b.text)}</p>` : b.type === 'h' ? html`<p><strong>${inline(b.text)}</strong></p>`
    : b.type === 'ol' ? html`<ol>${b.items.map((i) => html`<li>${inline(i)}</li>`)}</ol>` : html`<ul>${b.items.map((i) => html`<li>${inline(i)}</li>`)}</ul>`)}</div>`;
}

export function go(hash) { location.hash = hash; }

export function applyTheme(theme) {
  const root = document.documentElement;
  if (theme === 'light' || theme === 'dark') root.dataset.theme = theme; else delete root.dataset.theme;
}
export async function refreshMe() {
  const me = await api('/api/me');
  store.set({ me });
  applyTheme(me.settings.theme);
  return me;
}
