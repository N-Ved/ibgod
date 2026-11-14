// IB God — application shell, router and session handling.
import { html, render, useState, useEffect, api, store, useStore, Icon, Modal, isMedia, refreshMe } from './core.js';
import { IssueRow } from './tasks.js';
import { Onboarding } from './onboarding.js';
import { Today } from './today.js';
import { Plan } from './plan.js';
import { Subjects, SubjectPage } from './subjects.js';
import { Library } from './library.js';
import { Coach, Techniques } from './coach.js';
import { Feedback } from './feedback.js';
import { Settings } from './settings.js';

const NAV = [
  { path: 'today', label: 'Today', icon: 'home' },
  { path: 'plan', label: 'Plan', icon: 'calendar' },
  { path: 'subjects', label: 'Subjects', icon: 'target' },
  { path: 'library', label: 'Library', icon: 'layers' },
  { path: 'coach', label: 'Coach', icon: 'chat' },
  { path: 'techniques', label: 'Study methods', icon: 'bulb' },
  { path: 'feedback', label: 'Feedback writer', icon: 'pen' },
  { path: 'settings', label: 'Settings', icon: 'settings' },
];
const TABS = ['today', 'plan', 'subjects', 'library', 'more'];

function parseHash() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [pathPart, queryPart] = raw.split('?');
  const parts = pathPart.split('/').filter(Boolean).map(decodeURIComponent);
  const query = Object.fromEntries(new URLSearchParams(queryPart || ''));
  return { parts, query, page: parts[0] || 'today' };
}
function useRoute() {
  const [route, setRoute] = useState(parseHash());
  useEffect(() => {
    const on = () => { setRoute(parseHash()); window.scrollTo(0, 0); };
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
  return route;
}

// Keep the Authelia session alive only while the student is really using the page.
let lastActivity = Date.now();
['pointerdown', 'keydown', 'scroll', 'touchstart'].forEach((ev) => window.addEventListener(ev, () => { lastActivity = Date.now(); }, { passive: true, capture: true }));
setInterval(() => {
  const playing = [...document.querySelectorAll('video, audio')].some((m) => !m.paused);
  if (document.visibilityState === 'visible' && (playing || Date.now() - lastActivity < 4 * 60 * 1000) && !store.get().sessionLost) {
    api('/api/ping').catch(() => {});
  }
}, 110 * 1000);

function More() {
  const { me } = useStore();
  return html`<div class="page">
    <div class="page-head"><div><h1>More</h1></div></div>
    <div class="card pad0">${NAV.slice(4).map((n) => html`<a class="nav-item" href=${'#/' + n.path}><${Icon} name=${n.icon} /> ${n.label}</a>`)}
      <a class="nav-item" href=${me.links.docs} target="_blank" rel="noopener"><${Icon} name="file" /> File browser</a>
      <a class="nav-item" href=${me.links.logout}><${Icon} name="logout" /> Sign out</a>
    </div>
    <div class="hint center">Signed in as ${me.display_name} (${me.username})</div>
  </div>`;
}

function MediaPlayer({ r, onClose }) {
  const video = ['mp4', 'mov', 'webm'].includes(r.ext);
  return html`<${Modal} title=${r.title} onClose=${onClose} wide=${video}>
    ${video ? html`<video class="video" src=${r.url} controls autoplay playsinline></video>` : html`<audio src=${r.url} controls autoplay style=${{ width: '100%' }}></audio>`}
    <div class="hint">Tip: watch actively. Pause after each idea and say it back in your own words.</div>
  <//>`;
}

function CreatedIssues({ data, onClose }) {
  const [issues, setIssues] = useState(data.issues);
  useEffect(() => { if (!issues.length) onClose(); }, [issues.length]);
  return html`<${Modal} title=${`${data.what || 'This change'} created ${issues.length === 1 ? 'an issue' : issues.length + ' issues'}`} onClose=${onClose}
      footer=${html`<a class="btn" href="#/plan" onClick=${onClose}>Open plan</a><button class="btn primary" onClick=${onClose}>Keep it anyway</button>`}>
    <div class="hint">Your change was saved. You can fix these now, or dismiss the ones you are happy with.</div>
    <div class="stack tight">${issues.map((i) => html`<${IssueRow} key=${i.key} issue=${i} onChanged=${() => setIssues(issues.filter((x) => x.key !== i.key))} />`)}</div>
  <//>`;
}

function Shell() {
  const { me, toasts, sessionLost, created, media, issueCount } = useStore();
  const route = useRoute();
  useEffect(() => {
    if (me && me.onboarded) api('/api/dashboard').then((d) => store.set({ issueCount: d.issue_count })).catch(() => {});
  }, [me && me.onboarded]);

  if (!me) return html`<div class="boot"><div class="boot-logo">IB God</div><div class="boot-sub">Loading your study plan…</div></div><${Overlays} ...${{ toasts, sessionLost, created: null, media: null }} />`;
  let view;
  if (!me.onboarded || route.page === 'setup') {
    view = html`<${Onboarding} editing=${me.onboarded} />`;
    if (!me.onboarded) return html`${view}<${Overlays} ...${{ toasts, sessionLost, created, media }} />`;
  } else {
    const p = route.page;
    view = p === 'today' ? html`<${Today} />`
      : p === 'plan' ? html`<${Plan} query=${route.query} />`
      : p === 'subjects' ? (route.parts[1] ? html`<${SubjectPage} key=${route.parts[1]} subjectKey=${route.parts[1]} tab=${route.parts[2]} />` : html`<${Subjects} />`)
      : p === 'library' ? html`<${Library} query=${route.query} />`
      : p === 'coach' ? html`<${Coach} />`
      : p === 'techniques' ? html`<${Techniques} focus=${route.parts[1]} />`
      : p === 'feedback' ? html`<${Feedback} jobId=${route.parts[1]} />`
      : p === 'settings' ? html`<${Settings} />`
      : p === 'more' ? html`<${More} />`
      : html`<div class="page"><div class="empty"><h3>Page not found</h3><a href="#/today">Back to today</a></div></div>`;
  }
  const active = route.page;
  const indexing = me.index && me.index.phase !== 'idle' && me.index.text_total > 0 && me.index.text_done < me.index.text_total;
  return html`<div class="shell">
    <nav class="sidebar" aria-label="Main">
      <a class="brand" href="#/today"><span class="brand-mark"><${Icon} name="spark" size=${18} /></span> IB God</a>
      ${NAV.map((n) => html`<a class=${'nav-item' + (active === n.path ? ' active' : '')} href=${'#/' + n.path}><${Icon} name=${n.icon} /> ${n.label}${n.path === 'plan' && issueCount ? html`<span class="badge">${issueCount}</span>` : null}</a>`)}
      <div class="nav-foot">
        <div class="ellipsis">${me.display_name}</div>
        <a href=${me.links.docs} target="_blank" rel="noopener">File browser</a> · <a href=${me.links.logout}>Sign out</a>
      </div>
    </nav>
    <div>
      <header class="topbar"><a class="brand" href="#/today"><span class="brand-mark"><${Icon} name="spark" size=${18} /></span> IB God</a><span class="grow"></span><a class="btn ghost icon" href="#/settings" aria-label="Settings"><${Icon} name="user" /></a></header>
      <main class="main">
        ${indexing ? html`<div class="page"><div class="banner"><span class="spinner"></span><div>The library is still being indexed (${Math.round((100 * me.index.text_done) / me.index.text_total)}%). Search and topic materials fill in as it finishes.</div></div></div>` : null}
        ${view}
      </main>
    </div>
    <nav class="tabbar" aria-label="Main">
      ${TABS.map((t) => { const n = NAV.find((x) => x.path === t) || { path: 'more', label: 'More', icon: 'more' };
        const on = active === t || (t === 'more' && !TABS.includes(active));
        return html`<a class=${on ? 'active' : ''} href=${'#/' + n.path}><${Icon} name=${n.icon} size=${22} />${n.label}${t === 'plan' && issueCount ? html`<span class="badge">${issueCount}</span>` : null}</a>`; })}
    </nav>
    <${Overlays} ...${{ toasts, sessionLost, created, media }} />
  </div>`;
}

function Overlays({ toasts, sessionLost, created, media }) {
  return html`
    ${media && isMedia(media) ? html`<${MediaPlayer} r=${media} onClose=${() => store.set({ media: null })} />` : null}
    ${created ? html`<${CreatedIssues} key=${created.issues.map((i) => i.key).join('|')} data=${created} onClose=${() => store.set({ created: null })} />` : null}
    ${sessionLost ? html`<${Modal} title="You have been signed out" footer=${html`<button class="btn primary" onClick=${() => location.reload()}>Sign in again</button>`}>
      <p>For security, sign-ins expire after a period of inactivity. Your plan and progress are saved.</p><//>` : null}
    <div class="toasts" role="status" aria-live="polite">${toasts.map((t) => html`<div class=${'toast' + (t.error ? ' err' : '')} key=${t.id}><span class="grow">${t.text}</span>${t.action ? html`<button onClick=${t.action.run}>${t.action.label}</button>` : null}</div>`)}</div>`;
}

async function boot() {
  const root = document.getElementById('app');
  root.textContent = '';
  render(html`<${Shell} />`, root);
  try {
    await refreshMe();
  } catch (e) {
    if (e.status !== 401) {
      root.textContent = '';
      render(html`<div class="boot"><div class="boot-logo">IB God</div><div class="boot-sub">${e.message}</div><button class="btn primary" onClick=${() => location.reload()}>Reload</button></div>`, root);
    }
  }
}
boot();
window.addEventListener('unhandledrejection', (e) => { if (e.reason && e.reason.status === 401) e.preventDefault(); });
