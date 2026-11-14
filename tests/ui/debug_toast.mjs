import { chromium } from 'playwright';
const BASE = 'http://ibgod-dev2:8080';
const browser = await chromium.launch({ args: ['--no-sandbox'] });
const page = await (await browser.newContext()).newPage();
page.on('pageerror', (e) => console.log('PAGE ERROR', String(e)));
await page.goto(BASE + '/#/today');
await page.waitForSelector('.hero');
await page.evaluate(async () => { const m = await import('/js/core.js'); m.toast('hello toast'); window.__m = m; });
for (const t of [500, 3000, 6000]) { await page.waitForTimeout(t === 500 ? 500 : t - (t === 3000 ? 500 : 3000)); console.log(t, 'ms: toasts in DOM =', await page.locator('.toast').count(), '| in store =', await page.evaluate(() => window.__m.store.get().toasts.length)); }
await browser.close();
