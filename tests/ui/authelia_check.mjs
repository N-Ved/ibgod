import { chromium } from 'playwright';
const browser = await chromium.launch({ args: ['--no-sandbox'] });
for (const locale of ['en-US', 'en-GB']) {
  const page = await (await browser.newContext({ locale, viewport: { width: 390, height: 844 }, isMobile: true })).newPage();
  const errs = []; page.on('pageerror', (e) => errs.push(String(e)));
  const locs = []; page.on('response', (r) => { if (r.url().includes('/locales/')) locs.push(`${r.status()} ${new URL(r.url()).pathname}`); });
  await page.goto('https://auth.n-ved.com/', { waitUntil: 'networkidle' });
  console.log(locale, '| title:', await page.title(), '| locale files:', locs.join(', '), '| page errors:', errs.length);
  await page.screenshot({ path: `/out/auth-${locale}.png` });
}
await browser.close();
