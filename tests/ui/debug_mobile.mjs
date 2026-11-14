import { chromium } from 'playwright';
const BASE = 'http://ibgod-dev2:8080';
const browser = await chromium.launch({ args: ['--no-sandbox'] });
for (const mobile of [false, true]) {
  const ctx = await browser.newContext(mobile ? { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true } : { viewport: { width: 1320, height: 900 } });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => console.log('PAGE ERROR', String(e).slice(0, 500)));
  page.on('console', (m) => console.log('CONSOLE', m.type(), m.text().slice(0, 300)));
  page.on('requestfailed', (r) => console.log('REQ FAILED', r.url(), r.failure() && r.failure().errorText));
  page.on('request', (r) => { if (r.url().includes('/api/')) console.log('REQ', r.method(), r.url().replace(BASE, '')); });
  await page.goto(BASE + '/#/today');
  await page.waitForTimeout(4000);
  console.log(mobile ? 'MOBILE' : 'DESKTOP', 'body:', (await page.evaluate(() => document.body.innerText)).slice(0, 200).replace(/\n/g, ' | '));
  await ctx.close();
}
await browser.close();
