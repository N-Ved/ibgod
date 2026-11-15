// Apps: every service on this server the signed-in person can open, as large tappable cards.
import { html, api, useLoad, Icon, Spinner, ErrorBox } from './core.js';

const GLYPHS = {
  folder: 'M3.5 6.5h6l2 2h9v10h-17z',
  flask: 'M9.5 3.5h5M10.5 3.5v6L5 18.5a1.5 1.5 0 0 0 1.3 2h11.4a1.5 1.5 0 0 0 1.3-2l-5.5-9v-6M7.5 14.5h9',
  map: 'M3.5 6.5l5.5-2.5 6 2.5 5.5-2.5v13.5l-5.5 2.5-6-2.5-5.5 2.5zM9 4v13.5M15 6.5V20',
  book: 'M5 4.5h10a3 3 0 0 1 3 3v12H8a3 3 0 0 1-3-3zM5 16.5a3 3 0 0 1 3-3h10',
  users: 'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM2.5 20a6.5 6.5 0 0 1 13 0M16 4.3a3.5 3.5 0 0 1 0 6.4M18 14.2a6.5 6.5 0 0 1 3.5 5.8',
  shield: 'M12 3.5l7.5 3v5.5c0 4.5-3.2 7.6-7.5 9-4.3-1.4-7.5-4.5-7.5-9V6.5zM8.8 12l2.2 2.2 4.2-4.4',
};

function Glyph({ name }) {
  return html`<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d=${GLYPHS[name] || GLYPHS.folder} /></svg>`;
}

export function Apps() {
  const { data, error, reload } = useLoad(() => api('/api/apps'), []);
  return html`<div class="page">
    <div class="page-head"><div class="grow"><h1>Apps</h1><div class="sub">Everything on this server that your account can open. They all use the same sign-in.</div></div></div>
    ${error ? html`<${ErrorBox} error=${error} retry=${reload} />` : !data ? html`<${Spinner} label="Checking what you can open" />` : html`
      <div class="app-grid">${data.apps.map((a) => html`<a class="app-card" key=${a.key} href=${a.url} target="_blank" rel="noopener" style=${{ '--app': a.color || 'var(--primary)' }}>
        <span class="app-icon"><${Glyph} name=${a.icon} /></span>
        <span class="app-text"><span class="app-name">${a.name}</span><span class="app-desc">${a.description}</span></span>
        <span class="app-go"><${Icon} name="right" size=${18} /></span>
      </a>`)}</div>
      ${data.apps.length <= 1 ? html`<div class="hint">Only your account settings are available. If you expected more, ask the server admin.</div>` : null}`}
  </div>`;
}
