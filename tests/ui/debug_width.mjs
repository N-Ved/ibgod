import { chromium } from 'playwright';
const browser = await chromium.launch({ args: ['--no-sandbox'] });
const m = await (await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true })).newPage();
for (const route of ['/#/subjects/' + encodeURIComponent('lang_a_ll:English') + '/works', '/#/subjects/physics/path', '/#/today']) {
  await m.goto('http://ibgod-dev:8080' + route); await m.waitForTimeout(2500);
  const r = await m.evaluate(() => {
    const W = screen.width;
    const wide = [...document.querySelectorAll('body *')].filter((e) => e.getBoundingClientRect().right > W + 1 && !e.closest('.tabs'));
    // outermost offenders only
    const outer = wide.filter((e) => !wide.includes(e.parentElement)).slice(0, 6).map((e) => `${e.tagName.toLowerCase()}.${[...e.classList].join('.')} right=${Math.round(e.getBoundingClientRect().right)} w=${Math.round(e.getBoundingClientRect().width)}`);
    return { screen: W, inner: innerWidth, docW: document.documentElement.scrollWidth, outer };
  });
  console.log(route, JSON.stringify(r));
}
await browser.close();
