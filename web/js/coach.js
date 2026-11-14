// AI coach (local model, streamed) and the evidence-based study methods library.
import { html, useState, useEffect, useRef, api, store, useLoad, attempt, fail, ApiError, Icon, Spinner, ErrorBox, RichText } from './core.js';

const STARTERS = [
  'I keep forgetting what I revise. What should I change?',
  'Give me a routine for the week before mock exams.',
  'How do I move from a 5 to a 6 in my weakest subject?',
  'What is the difference between "explain" and "evaluate" in exam questions?',
];

async function streamMessage(chatId, text, onEvent) {
  let res;
  try {
    res = await fetch(`/api/coach/chats/${chatId}/messages`, { method: 'POST', credentials: 'same-origin', redirect: 'manual',
      headers: { 'X-IBGod': '1', 'Content-Type': 'application/json', Accept: 'text/event-stream' }, body: JSON.stringify({ message: text }) });
  } catch { throw new ApiError(0, 'Could not reach the server.'); }
  if (res.type === 'opaqueredirect' || res.status === 401) { store.set({ sessionLost: true }); throw new ApiError(401, 'Session expired'); }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try { const j = await res.json(); if (typeof j.detail === 'string') detail = j.detail; } catch { /* ignore */ }
    throw new ApiError(res.status, detail);
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const chunk = buf.slice(0, i);
      buf = buf.slice(i + 2);
      let ev = 'message', data = '';
      for (const line of chunk.split('\n')) {
        if (line.startsWith('event:')) ev = line.slice(6).trim();
        else if (line.startsWith('data:')) data += line.slice(5).trim();
      }
      if (data) { try { onEvent(ev, JSON.parse(data)); } catch { /* skip malformed event */ } }
    }
  }
}

function Sources({ sources }) {
  if (!sources || !sources.length) return null;
  return html`<div class="msg-src">${sources.map((s, i) => s.type === 'technique'
    ? html`<a class="chip primary" key=${i} href=${'#/techniques/' + s.id}><${Icon} name="bulb" size=${12} /> ${s.title}</a>`
    : html`<a class="chip info" key=${i} href=${s.url} target="_blank" rel="noopener"><${Icon} name="file" size=${12} /> ${s.title}${s.page ? ` p.${s.page}` : ''}</a>`)}</div>`;
}

export function Coach() {
  const { data: list, reload: reloadList, error } = useLoad(() => api('/api/coach/chats'), []);
  const [chatId, setChatId] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const box = useRef(null);
  const scroll = () => { requestAnimationFrame(() => { if (box.current) box.current.scrollTop = box.current.scrollHeight; }); };

  const open = async (id) => {
    if (busy) return;
    setChatId(id);
    if (!id) { setMsgs([]); return; }
    const d = await attempt(() => api(`/api/coach/chats/${id}`));
    if (d) { setMsgs(d.messages); scroll(); }
  };
  const send = async (value) => {
    const q = (value || text).trim();
    if (!q || busy) return;
    setBusy(true);
    setText('');
    let id = chatId;
    try {
      if (!id) { id = (await api('/api/coach/chats', { method: 'POST' })).id; setChatId(id); }
      setMsgs((m) => [...m, { role: 'user', content: q }, { role: 'assistant', content: '', sources: [], pending: true }]);
      setStatus('Reading your question and searching the library…');
      scroll();
      const patchLast = (fn) => setMsgs((m) => m.map((x, i) => (i === m.length - 1 ? fn(x) : x)));
      await streamMessage(id, q, (ev, d) => {
        if (ev === 'sources') { patchLast((x) => ({ ...x, sources: d.sources })); setStatus('Thinking. The coach runs on this server, so the first words take up to a minute.'); }
        else if (ev === 'wait') setStatus(d.ahead > 0 ? `Waiting: ${d.ahead} other request${d.ahead === 1 ? '' : 's'} ahead of you.` : 'Almost your turn…');
        else if (ev === 'token') { setStatus(''); patchLast((x) => ({ ...x, content: x.content + d.text, pending: false })); scroll(); }
        else if (ev === 'error') { patchLast((x) => ({ ...x, content: d.detail, pending: false, failed: true })); }
      });
      patchLast((x) => ({ ...x, pending: false, content: x.content || 'No answer was produced. Please try again.' }));
      reloadList();
    } catch (e) {
      fail(e);
      setMsgs((m) => (m.length && m[m.length - 1].pending ? m.slice(0, -1) : m));
    } finally { setBusy(false); setStatus(''); }
  };
  const remove = async (id, e) => {
    e.stopPropagation();
    if (!confirm('Delete this conversation?')) return;
    const res = await attempt(() => api(`/api/coach/chats/${id}`, { method: 'DELETE' }));
    if (res) { if (id === chatId) { setChatId(null); setMsgs([]); } reloadList(); }
  };

  if (error) return html`<div class="page"><${ErrorBox} error=${error} retry=${reloadList} /></div>`;
  const llm = list && list.llm;
  return html`<div class="page">
    <div class="page-head"><div class="grow"><h1>Coach</h1><div class="sub">Ask about study methods, planning, exam technique or a topic. Answers draw on the research library and your own materials.</div></div>
      <a class="btn" href="#/techniques"><${Icon} name="bulb" size=${16} /> Study methods</a></div>
    ${llm && !llm.available ? html`<div class="banner warn"><${Icon} name="alert" /><div>The AI model is not running right now. You will still get the most relevant guidance from the knowledge base.</div></div>` : null}
    <div class="chat">
      <div class="chat-list">
        <button class="btn" onClick=${() => open(null)} disabled=${busy}><${Icon} name="plus" size=${16} /> New</button>
        ${list ? list.chats.map((c) => html`<button class=${'chat-item' + (c.id === chatId ? ' on' : '')} key=${c.id} onClick=${() => open(c.id)}><span class="grow ellipsis">${c.title}</span>
          <span role="button" tabindex="0" aria-label="Delete conversation" onClick=${(e) => remove(c.id, e)}><${Icon} name="trash" size=${14} /></span></button>`) : html`<${Spinner} />`}
      </div>
      <div class="card pad0 chat-main">
        <div class="msgs" ref=${box}>
          ${!msgs.length ? html`<div class="empty"><h3>What do you want help with?</h3>
            <div class="stack tight" style=${{ maxWidth: '520px', margin: '12px auto 0' }}>${STARTERS.map((s) => html`<button class="pick" key=${s} onClick=${() => send(s)}>${s}</button>`)}</div>
            <div class="hint" style=${{ marginTop: '14px' }}>${llm && llm.model ? `Runs privately on this server (${llm.model}). ` : 'Runs privately on this server. '}Nothing you type leaves it. It is a small model: good for methods and planning, and it can be wrong about subject facts, so check against your notes.</div></div>` : null}
          ${msgs.map((m, i) => html`<div class=${'msg ' + m.role} key=${i}>
            ${m.role === 'user' ? m.content : m.pending && !m.content ? html`<span class="typing"><i></i><i></i><i></i></span>` : html`<${RichText} text=${m.content} />`}
            ${m.role === 'assistant' ? html`<${Sources} sources=${m.sources} />` : null}</div>`)}
          ${status ? html`<div class="hint center">${status}</div>` : null}
        </div>
        <form class="composer" onSubmit=${(e) => { e.preventDefault(); send(); }}>
          <textarea class="input" rows="1" maxlength="2000" placeholder="Ask your coach…" value=${text} disabled=${busy} aria-label="Message"
            onInput=${(e) => setText(e.target.value)} onKeyDown=${(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}></textarea>
          <button class="btn primary" type="submit" disabled=${busy || !text.trim()}>${busy ? html`<span class="spinner"></span>` : 'Send'}</button>
        </form>
      </div>
    </div>
  </div>`;
}

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
      <a class="btn" href="#/coach"><${Icon} name="chat" size=${16} /> Ask the coach</a></div>
    <div class="banner"><${Icon} name="bulb" /><div>The short version: <strong>test yourself instead of re-reading, spread it out instead of cramming, mix topics, sit timed papers and study every lost mark, and sleep.</strong></div></div>
    ${cats.map((c) => html`<div class="stack tight" key=${c.name}><div class="section-label">${c.name}</div>
      ${c.items.map((t) => html`<${Technique} key=${t.id} t=${t} open=${open === t.id} onToggle=${() => setOpen(open === t.id ? null : t.id)} />`)}</div>`)}
    <div class="card"><div class="card-title"><h2>What each grade needs</h2></div>
      ${[3, 4, 5, 6].map((g) => { const b = data.bands[String(g)]; return html`<div class="step" key=${g}><div class="step-num">${g}→${g + 1}</div><div><strong>${b.title}</strong><div class="small muted">${b.focus}</div></div></div>`; })}
      <div class="hint">Open a subject to see the full path for your own grades.</div></div>
  </div>`;
}
