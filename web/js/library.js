// Library: one search across every textbook, paper, note, question bank page and video on the drive.
import { html, useState, useEffect, useRef, api, useStore, useLoad, attempt, Icon, Spinner, ResourceLink, ResourceGroup, plural } from './core.js';

const COLLECTIONS = [['', 'Everything'], ['notes', 'Notes'], ['books', 'Textbooks and guides'], ['past_papers', 'Past papers'], ['questionbank', 'Question banks'], ['videos', 'Videos'],
  ['site', 'Study sites'], ['official', 'Official IB documents'], ['exemplars', 'Exemplars'], ['specimen', 'Specimen papers'], ['mocks', 'Mock papers'], ['practice', 'Practice sets'], ['extra', 'Other']];
const LABEL = Object.fromEntries(COLLECTIONS);

function SaveButton({ r }) {
  const [mark, setMark] = useState(r.mark || null);
  const toggle = async (e) => {
    e.preventDefault(); e.stopPropagation();
    const next = mark ? 'none' : 'saved';
    const res = await attempt(() => api(`/api/resources/${r.id}/mark`, { method: 'POST', body: { status: next } }));
    if (res) setMark(next === 'none' ? null : next);
  };
  return html`<button class="btn ghost icon" aria-label=${mark ? 'Remove from saved' : 'Save for later'} title=${mark ? 'Saved' : 'Save for later'} onClick=${toggle} style=${{ color: mark ? 'var(--warn)' : 'var(--faint)' }}><${Icon} name="star" size=${17} /></button>`;
}

export function Library({ query }) {
  const { me } = useStore();
  const [q, setQ] = useState(query.q || '');
  const [subject, setSubject] = useState(query.subject || '');
  const [collection, setCollection] = useState(query.collection || '');
  const [level, setLevel] = useState('');
  const [currentOnly, setCurrentOnly] = useState(false);
  const [allLang, setAllLang] = useState(false);
  const [results, setResults] = useState(null);
  const [more, setMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const seq = useRef(0);
  const { data: overview } = useLoad(() => api('/api/library/overview'), []);

  useEffect(() => { setQ(query.q || ''); setSubject(query.subject || ''); if (query.collection !== undefined) setCollection(query.collection || ''); }, [query.q, query.subject, query.collection]);

  const active = q.trim().length >= 2 || subject || collection;
  const run = async (offset) => {
    const id = ++seq.current;
    setLoading(true);
    const p = new URLSearchParams({ q: q.trim(), offset: String(offset) });
    if (subject) p.set('subject', subject);
    if (collection) p.set('collection', collection);
    const mine = me.subjects.find((x) => x.subject === subject);
    if (level) p.set('level', level); else if (mine) p.set('level', mine.level);
    if (currentOnly) p.set('current_only', 'true');
    if (allLang) p.set('all_languages', 'true');
    const res = await attempt(() => api('/api/search?' + p.toString()));
    if (id !== seq.current) return;
    setLoading(false);
    if (!res) return;
    setMore(res.results.length >= 30);
    setResults((prev) => (offset ? [...(prev || []), ...res.results] : res.results));
  };
  useEffect(() => {
    if (!active) { setResults(null); return undefined; }
    const t = setTimeout(() => run(0), 320);
    return () => clearTimeout(t);
  }, [q, subject, collection, level, currentOnly, allLang]);

  const subjects = [...me.subjects.map((s) => [s.subject, s.name]), ['tok', 'Theory of Knowledge'], ['ee', 'Extended Essay']];
  return html`<div class="page">
    <div class="page-head"><div class="grow"><h1>Library</h1><div class="sub">${overview ? `${overview.counts.reduce((a, c) => a + c.n, 0).toLocaleString()} resources from the drive, searchable down to the page.` : 'Everything on the drive, searchable down to the page.'}</div></div></div>
    <div class="card stack">
      <div class="row"><${Icon} name="search" /><input class="input grow" type="search" autofocus placeholder="Search a topic, a question, a book, a paper… e.g. Doppler effect, market failure, May 2023" value=${q} onInput=${(e) => setQ(e.target.value)} aria-label="Search the library" /></div>
      <div class="row wrap">
        <select class="input" style=${{ width: 'auto', flex: '1 1 170px' }} aria-label="Subject" value=${subject} onChange=${(e) => setSubject(e.target.value)}><option value="">All subjects</option>${subjects.map(([k, n]) => html`<option value=${k}>${n}</option>`)}</select>
        <select class="input" style=${{ width: 'auto', flex: '1 1 170px' }} aria-label="Type" value=${collection} onChange=${(e) => setCollection(e.target.value)}>${COLLECTIONS.map(([k, n]) => html`<option value=${k}>${n}</option>`)}</select>
        <div class="seg">${[['', 'Any level'], ['HL', 'HL'], ['SL', 'SL']].map(([k, n]) => html`<button class=${level === k ? 'on' : ''} onClick=${() => setLevel(k)}>${n}</button>`)}</div>
      </div>
      <div class="row wrap small">
        <label class="switch"><input type="checkbox" checked=${currentOnly} onChange=${(e) => setCurrentOnly(e.target.checked)} /> Current syllabus only</label>
        <label class="switch"><input type="checkbox" checked=${allLang} onChange=${(e) => setAllLang(e.target.checked)} /> Include French, Spanish and other language versions</label>
      </div>
    </div>

    ${active ? html`<div class="stack tight">
      ${loading && !results ? html`<${Spinner} label="Searching" />` : null}
      ${results && !results.length && !loading ? html`<div class="empty"><h3>No matches</h3><div>Try fewer or different words, another subject, or switch off "current syllabus only".</div></div>` : null}
      ${results && results.length ? html`<div class="hint">${plural(results.length, 'result')}${more ? ' so far' : ''}${loading ? html` <span class="spinner"></span>` : ''}</div>` : null}
      <div class="res-list">${(results || []).map((r) => html`<${ResourceLink} key=${r.id + ':' + (r.page || 0)} r=${r} sub=${r.subject_name || null} extra=${html`<${SaveButton} r=${r} />`} />`)}</div>
      ${more && results && results.length ? html`<button class="btn" disabled=${loading} onClick=${() => run(results.length)}>Show more</button>` : null}
    </div>` : overview ? html`
      <div class="card"><div class="card-title"><h2>Browse by type</h2></div>
        <div class="row wrap">${overview.counts.map((c) => html`<button class="btn sm" key=${c.collection} onClick=${() => setCollection(c.collection)}>${LABEL[c.collection] || c.collection} <span class="muted">${c.n.toLocaleString()}</span></button>`)}</div></div>
      ${overview.saved.length ? html`<div class="card"><div class="card-title"><${Icon} name="star" /><h2>Saved for later</h2></div><div class="res-list">${overview.saved.map((r) => html`<${ResourceLink} key=${r.id} r=${r} extra=${html`<${SaveButton} r=${{ ...r, mark: 'saved' }} />`} />`)}</div></div>` : null}
      <div class="grid two">
        <div class="card stack"><div class="card-title"><h2>Exam essentials</h2></div>
          <${ResourceGroup} title="Grade boundaries" items=${overview.general.grade_boundaries.slice(0, 4)} />
          <${ResourceGroup} title="Exam schedules" items=${overview.general.exam_schedules.slice(0, 3)} />
          <${ResourceGroup} title="Grade descriptors" items=${overview.general.grade_descriptors.slice(0, 1)} />
          <${ResourceGroup} title="Calculator and exam rules" items=${[...overview.general.calculator_rules.slice(0, 1), ...overview.general.exam_conduct.slice(0, 1)]} /></div>
        <div class="card stack"><div class="card-title"><h2>Core: TOK and Extended Essay</h2></div>
          <div class="hint">TOK and the EE together are worth up to 3 diploma points.</div>
          <div class="row wrap"><button class="btn sm" onClick=${() => setSubject('tok')}>All TOK material (${overview.core.tok.length})</button><button class="btn sm" onClick=${() => setSubject('ee')}>All EE material (${overview.core.ee.length}${overview.core.ee.length >= 400 ? '+' : ''})</button>
            <a class="btn sm" href="#/feedback">Get feedback on a draft</a></div>
          <${ResourceGroup} title="TOK guides and exemplars" items=${overview.core.tok.filter((r) => ['subject_guide', 'tok_exemplar', 'textbook'].includes(r.kind)).slice(0, 5)} />
          <${ResourceGroup} title="Extended Essay guide and books" items=${overview.core.ee.filter((r) => ['subject_guide', 'textbook', 'coursework_guide', 'site_home', 'revision_guide'].includes(r.kind)).slice(0, 5)} /></div>
      </div>
      <div class="hint center">Prefer folders? The same files are in the <a href=${me.links.docs} target="_blank" rel="noopener">file browser</a>.</div>` : html`<${Spinner} />`}
  </div>`;
}
