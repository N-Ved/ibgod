// Feedback writer: criterion-by-criterion formative feedback on IAs, the EE and TOK work.
import { html, useState, useEffect, useRef, api, useStore, useLoad, attempt, toast, Icon, Spinner, ErrorBox, fmtDate, go } from './core.js';

const LEVEL = { emerging: ['danger', 'Emerging'], developing: ['warn', 'Developing'], secure: ['info', 'Secure'], strong: ['ok', 'Strong'] };
const CHECK = { ok: ['ok', 'check'], warn: ['warn', 'alert'], info: ['info', 'bulb'] };

function countWords(t) { const m = t.match(/[\p{L}\p{N}'’-]+/gu); return m ? m.length : 0; }

function Result({ jobId }) {
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const [showText, setShowText] = useState(false);
  useEffect(() => {
    let alive = true, timer;
    const load = async () => {
      try {
        const j = await api(`/api/feedback/jobs/${jobId}`);
        if (!alive) return;
        setJob(j);
        if (j.status === 'queued' || j.status === 'running') timer = setTimeout(load, 5000);
      } catch (e) { if (alive) setError(e); }
    };
    load();
    return () => { alive = false; clearTimeout(timer); };
  }, [jobId]);
  if (error) return html`<div class="page"><${ErrorBox} error=${error} /><a href="#/feedback">Back to feedback</a></div>`;
  if (!job) return html`<div class="page"><${Spinner} label="Loading feedback" /></div>`;
  const r = job.result;
  const waiting = job.status === 'queued' || job.status === 'running';
  return html`<div class="page">
    <div class="page-head"><div class="grow"><a class="small" href="#/feedback">← Feedback writer</a><h1>${job.title}</h1><div class="sub">${job.rubric_name} · ${job.words.toLocaleString()} words · submitted ${fmtDate(job.created_at.slice(0, 10))}</div></div>
      <button class="btn" onClick=${() => window.print()}>Print</button></div>
    ${waiting ? html`<div class="card center"><div><span class="spinner"></span></div>
      <h3 style=${{ marginTop: '8px' }}>${job.status === 'queued' ? (job.ahead ? `In the queue: ${job.ahead} ahead of you` : 'Starting…') : job.progress || 'Working…'}</h3>
      <p class="muted">The model reads your whole draft on this server's processor, so a full essay takes roughly 5 to 10 minutes. You can leave this page: the result is saved here.</p></div>` : null}
    ${job.status === 'error' ? html`<div class="banner danger"><${Icon} name="alert" /><div>${(r && r.error) || 'Feedback could not be generated.'}</div></div>` : null}
    ${r && !r.error ? html`
      ${r.ai_error ? html`<div class="banner warn"><${Icon} name="alert" /><div>${r.ai_error}</div></div>` : null}
      ${r.truncated ? html`<div class="banner warn"><${Icon} name="alert" /><div>Your work was longer than the model can read at once, so the middle section was left out of the AI comments.</div></div>` : null}
      ${r.priorities && r.priorities.length ? html`<div class="card hero"><div class="card-title"><${Icon} name="target" /><h2>Do these first</h2></div><ol>${r.priorities.map((p) => html`<li>${p}</li>`)}</ol></div>` : null}
      <div class="card"><div class="card-title"><h2>Automatic checks</h2></div>
        <div class="stack tight">${r.checks.map((c, i) => { const [tone, icon] = CHECK[c.status] || CHECK.info; return html`<div class="row top" key=${i}><span class=${'chip ' + tone}><${Icon} name=${icon} size=${13} /></span><div><strong>${c.title}</strong><div class="small muted">${c.detail}</div></div></div>`; })}</div></div>
      ${r.criteria.map((c) => { const [tone, label] = LEVEL[c.level] || ['', '']; return html`<div class="card" key=${c.code}>
        <div class="card-title"><h2 class="grow">${c.code.length <= 3 ? `Criterion ${c.code}: ` : ''}${c.name}</h2>${c.marks ? html`<span class="chip">${c.marks} marks</span>` : null}${c.level ? html`<span class=${'chip ' + tone}>${label}</span>` : null}</div>
        <div class="hint" style=${{ marginBottom: '8px' }}>Top band: ${c.descriptor}</div>
        ${c.error ? html`<div class="banner warn">${c.error}</div>` : html`<div class="grid two">
          <div><div class="section-label">What is working</div><ul>${c.strengths.map((s) => html`<li>${s}</li>`)}</ul></div>
          <div><div class="section-label">To move up a band</div><ul>${c.improvements.map((s) => html`<li>${s}</li>`)}</ul></div></div>
          ${c.evidence ? html`<div class="quote small" style=${{ marginTop: '8px' }}>“${c.evidence}”</div>` : null}`}
      </div>`; })}
      ${r.ai ? html`<div class="hint">The band words (emerging, developing, secure, strong) describe how close the draft is to the top band for that criterion. They are not marks.</div>` : null}
      <div class="banner"><${Icon} name="alert" /><div class="small">${r.note}</div></div>` : null}
    <button class="btn sm ghost" onClick=${() => setShowText(!showText)}>${showText ? 'Hide' : 'Show'} the text you submitted</button>
    ${showText ? html`<div class="card small" style=${{ whiteSpace: 'pre-wrap' }}>${job.text}</div>` : null}
  </div>`;
}

export function Feedback({ jobId }) {
  return jobId ? html`<${Result} key=${jobId} jobId=${jobId} />` : html`<${FeedbackHome} />`;
}

function FeedbackHome() {
  const { me } = useStore();
  const { data: meta, error } = useLoad(() => api('/api/feedback/rubrics'), []);
  const { data: jobs, reload } = useLoad(() => api('/api/feedback/jobs'), []);
  const [rubric, setRubric] = useState('');
  const [title, setTitle] = useState('');
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const file = useRef(null);
  useEffect(() => {
    if (!jobs || !jobs.jobs.some((j) => j.status === 'queued' || j.status === 'running')) return undefined;
    const t = setTimeout(reload, 8000);
    return () => clearTimeout(t);
  }, [jobs]);
  useEffect(() => {
    if (meta && !rubric) {
      const year = Number(me.settings.session_year) || 0;
      setRubric(year >= 2027 ? 'ee_2027' : 'ee_2018');
    }
  }, [meta]);
  if (error) return html`<div class="page"><${ErrorBox} error=${error} /></div>`;
  if (!meta) return html`<div class="page"><${Spinner} label="Loading" /></div>`;
  const rub = meta.rubrics.find((r) => r.key === rubric);
  const words = countWords(text);

  const upload = async (e) => {
    const f = e.target.files[0];
    e.target.value = '';
    if (!f) return;
    setUploading(true);
    const form = new FormData();
    form.append('file', f);
    const res = await attempt(() => api('/api/feedback/extract', { method: 'POST', form }));
    setUploading(false);
    if (res) { setText(res.text); if (!title) setTitle(f.name.replace(/\.[^.]+$/, '')); toast(`Read ${res.words.toLocaleString()} words from ${f.name}. Check the text below before submitting.`); }
  };
  const submit = async () => {
    setBusy(true);
    const res = await attempt(() => api('/api/feedback/jobs', { method: 'POST', body: { rubric, title: title.trim() || 'Untitled draft', text } }));
    setBusy(false);
    if (res) go('#/feedback/' + res.id);
  };
  const remove = async (id) => {
    if (!confirm('Delete this feedback and the text you submitted?')) return;
    const res = await attempt(() => api(`/api/feedback/jobs/${id}`, { method: 'DELETE' }));
    if (res) reload();
  };

  return html`<div class="page">
    <div class="page-head"><div class="grow"><h1>Feedback writer</h1><div class="sub">Paste or upload a draft IA, Extended Essay or TOK piece and get comments against each official criterion.</div></div></div>
    ${!meta.llm.available ? html`<div class="banner warn"><${Icon} name="alert" /><div>The AI model is not running right now. You can still submit: you will get the automatic checks, and can resubmit later for full comments.</div></div>` : null}
    <div class="grid two">
      <div class="card stack">
        <div class="field"><label for="fb-rubric">What is it?</label>
          <select id="fb-rubric" class="input" value=${rubric} onChange=${(e) => setRubric(e.target.value)}>${meta.rubrics.map((r) => html`<option value=${r.key}>${r.name}</option>`)}</select>
          ${rub ? html`<div class="hint">${rub.applies}${rub.words ? ` Word limit: ${rub.words.toLocaleString()}.` : ''}</div>` : null}</div>
        <div class="field"><label for="fb-title">Title</label><input id="fb-title" class="input" maxlength="160" placeholder="e.g. Physics IA draft 2" value=${title} onInput=${(e) => setTitle(e.target.value)} /></div>
        <div class="field"><label for="fb-text">Your work</label>
          <textarea id="fb-text" class="input" style=${{ minHeight: '260px' }} maxlength="200000" placeholder="Paste the full text here, or upload a file." value=${text} onInput=${(e) => setText(e.target.value)}></textarea>
          <div class="row wrap"><span class="hint grow">${words.toLocaleString()} words${rub && rub.words && words > rub.words ? html` · <span class="chip warn">over the ${rub.words.toLocaleString()} limit</span>` : ''}${words > meta.max_words ? ` · only about ${meta.max_words.toLocaleString()} words can be read by the AI` : ''}</span>
            <input ref=${file} type="file" accept=".pdf,.docx,.txt" class="hide" onChange=${upload} />
            <button class="btn sm" disabled=${uploading} onClick=${() => file.current.click()}>${uploading ? html`<span class="spinner"></span> Reading…` : html`<${Icon} name="upload" size=${15} /> Upload PDF, DOCX or TXT`}</button></div></div>
        <button class="btn primary" disabled=${busy || words < 80} onClick=${submit}>${busy ? html`<span class="spinner"></span> Submitting…` : 'Get feedback'}</button>
        <div class="hint">Your text stays on this server, is visible only to you, and you can delete it at any time. Up to ${meta.per_day} submissions a day. This tool gives guidance; it never rewrites your work, which must remain your own under IB academic integrity rules.</div>
      </div>
      <div class="stack">
        ${rub ? html`<div class="card"><div class="card-title"><h2 class="grow">What examiners look for</h2>${rub.total ? html`<span class="chip">${rub.total} marks</span>` : null}</div>
          <div class="stack tight">${rub.criteria.map((c) => html`<div key=${c.code}><strong>${c.code.length <= 3 ? c.code + ' · ' : ''}${c.name}</strong>${c.marks ? html` <span class="muted small">(${c.marks})</span>` : null}<div class="small muted">${c.descriptor}</div></div>`)}</div>
          <div class="hint" style=${{ marginTop: '8px' }}>Summaries of the published criteria. Read the full descriptors in your subject guide; exemplars are in the <a href="#/library?collection=exemplars">library</a>.</div></div>` : null}
        <div class="card"><div class="card-title"><h2>Your feedback</h2></div>
          ${!jobs ? html`<${Spinner} />` : !jobs.jobs.length ? html`<div class="hint">Nothing yet. Feedback you request appears here.</div>` : html`<div class="stack tight">${jobs.jobs.map((j) => html`<div class="row" key=${j.id}>
            <a class="grow" href=${'#/feedback/' + j.id} style=${{ color: 'inherit', minWidth: 0 }}><div class="ellipsis"><strong>${j.title}</strong></div><div class="small muted">${j.rubric_name} · ${fmtDate(j.created_at.slice(0, 10))}</div></a>
            ${j.status === 'done' ? html`<span class="chip ok">ready</span>` : j.status === 'error' ? html`<span class="chip danger">failed</span>` : html`<span class="chip info"><span class="spinner" style=${{ width: '11px', height: '11px' }}></span> ${j.status === 'running' ? 'writing' : 'queued'}</span>`}
            <button class="btn ghost icon" aria-label="Delete" disabled=${j.status === 'running'} onClick=${() => remove(j.id)}><${Icon} name="trash" size=${16} /></button></div>`)}</div>`}
        </div>
      </div>
    </div>
  </div>`;
}
