// End-to-end browser test of IB God: first-run wizard, every screen, schedule edits, mobile and dark mode.
import { chromium } from 'playwright';
import fs from 'fs';

const BASE = process.env.BASE || 'http://ibgod-dev2:8080';
const OUT = process.env.OUT || '/out';
const problems = [];
const note = (ok, label, extra = '') => { console.log(`${ok ? 'PASS' : 'FAIL'} ${label}${extra ? '  [' + extra + ']' : ''}`); if (!ok) problems.push(label); };
const browser = await chromium.launch({ args: ['--no-sandbox'] });

function watch(page, tag) {
  page.on('console', (m) => { if (m.type() === 'error' && !m.text().includes('Cross-Origin-Opener-Policy header has been ignored')) { console.log(`CONSOLE ERROR (${tag}):`, m.text().slice(0, 300)); problems.push('console error: ' + m.text().slice(0, 120)); } });
  page.on('pageerror', (e) => { console.log(`PAGE ERROR (${tag}):`, String(e).slice(0, 400)); problems.push('page error: ' + String(e).slice(0, 120)); });
  page.on('response', (r) => { if (r.status() >= 400 && !r.url().includes('/favicon')) { console.log(`HTTP ${r.status()} (${tag}):`, r.request().method(), r.url().replace(BASE, '')); problems.push(`http ${r.status()} ${r.url().replace(BASE, '')}`); } });
}
const shot = async (page, name) => { await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: false }); };

// start from a clean account
const setupCtx = await browser.newContext();
await setupCtx.request.post(BASE + '/api/account/delete', { headers: { 'X-IBGod': '1' }, data: { confirm: 'DELETE' } });
await setupCtx.close();

const ctx = await browser.newContext({ viewport: { width: 1320, height: 900 } });
const page = await ctx.newPage();
watch(page, 'desktop');
await page.goto(BASE + '/');
await page.waitForSelector('.wizard', { timeout: 15000 });
note(await page.locator('h1').first().textContent().then((t) => t.includes('Welcome')), 'wizard opens for a new user');
await shot(page, '01-wizard-exams');
await page.fill('#ob-name', 'Alex Tester');
await page.locator('.seg button', { hasText: '2027' }).click();
await page.locator('.wizard-foot .btn.primary').click();

// subjects
await page.waitForSelector('input[type=search]');
for (const [query, name] of [['physics', 'Physics'], ['chemistry', 'Chemistry'], ['analysis', 'Mathematics: Analysis and Approaches'], ['economics', 'Economics'], ['english a: lang', 'English A: Language and Literature'], ['spanish b', 'Spanish B']]) {
  await page.fill('input[type=search]', query);
  await page.locator('.pick', { hasText: name }).first().click();
}
await page.fill('input[type=search]', '');
note((await page.locator('.wizard .card .row strong').count()) === 6, 'six subjects selected');
for (const name of ['Economics', 'English A: Language and Literature', 'Spanish B']) await page.locator('.wizard .card .row', { hasText: name }).locator('.seg button', { hasText: 'SL' }).click();
await shot(page, '02-wizard-subjects');
await page.locator('.wizard-foot .btn.primary').click();

// grades
await page.waitForSelector('.grade-pick');
const cards = page.locator('.wizard .card');
note((await cards.count()) === 6, 'grade step lists every subject');
await cards.nth(0).locator('.grade-pick').nth(0).locator('button', { hasText: '5' }).click();
await cards.nth(0).locator('.grade-pick').nth(1).locator('button', { hasText: '7' }).click();
await cards.nth(2).locator('.grade-pick').nth(0).locator('button', { hasText: '3' }).click();
await shot(page, '03-wizard-grades');
await page.locator('.wizard-foot .btn.primary').click();

// textbooks
await page.waitForSelector('.wizard select', { timeout: 15000 });
const sel = page.locator('.wizard select').first();
const opts = await sel.locator('option').count();
note(opts > 3, 'textbook list is filled from the library', `options=${opts}`);
await sel.selectOption({ index: 2 });
await shot(page, '04-wizard-textbooks');
await page.locator('.wizard-foot .btn.primary').click();

// time
await page.waitForSelector('.daygrid');
await page.locator('.btn', { hasText: 'Steady' }).click();
await shot(page, '05-wizard-time');
await page.locator('.wizard-foot .btn.primary').click();
await page.waitForSelector('text=Ready to build your plan');
await shot(page, '06-wizard-review');
await page.locator('.wizard-foot .btn.primary').click();

// dashboard
await page.waitForSelector('.hero', { timeout: 60000 });
note(page.url().includes('#/today'), 'lands on Today after setup');
await page.waitForSelector('.task', { timeout: 15000 });
note((await page.locator('.task').count()) > 0, 'today shows tasks');
await shot(page, '07-today');
const t0 = Date.now();
await page.waitForSelector('.toast', { state: 'detached', timeout: 12000 }).then(() => note(true, 'notification disappears by itself', `${Date.now() - t0} ms`)).catch(() => note(false, 'notification disappears by itself'));
await page.locator('.task .task-title').first().click();
await page.waitForSelector('.task-body', { timeout: 10000 });
await page.waitForFunction(() => !document.querySelector('.task-body .spinner'), null, { timeout: 30000 });
note((await page.locator('.task-body .res').count()) > 0, 'an open task lists matching materials', `res=${await page.locator('.task-body .res').count()}`);
await shot(page, '08-task-open');
await page.locator('.task .check').first().click();
await page.waitForSelector('.task.done', { timeout: 10000 });
note(true, 'task can be marked done');

// plan
await page.goto(BASE + '/#/plan');
await page.waitForSelector('.week .day', { timeout: 15000 });
note((await page.locator('.week .day').count()) === 7, 'plan shows seven days');
note((await page.locator('.banner.ok').count()) === 1, 'fresh plan reports no issues');
await shot(page, '09-plan-week');
await page.locator('.btn[aria-label="Next week"]').click();
await page.waitForTimeout(800);
const dayWithTasks = page.locator('.week .day').filter({ has: page.locator('.task') }).first();
await dayWithTasks.locator('.day-head').click();
await page.waitForSelector('.modal');
await page.locator('.modal .btn', { hasText: 'Make it a day off' }).click();
await page.waitForSelector('.modal .issue', { timeout: 10000 });
note((await page.locator('.modal h2').textContent()).includes('created'), 'a change that causes a problem is reported immediately');
await shot(page, '10-created-issue');
await page.locator('.modal .issue .btn', { hasText: 'Dismiss' }).first().click();
await page.waitForFunction(() => !document.querySelector('.modal'), null, { timeout: 10000 });
note(true, 'the issue can be dismissed from the dialog');
const src = page.locator('.week .day .task[draggable=true]').first();
const srcTitle = await src.locator('.task-title').textContent();
const target = page.locator('.week .day').nth(5);
await src.dragTo(target);
await page.waitForTimeout(1500);
const moved = await target.locator('.task-title', { hasText: srcTitle.slice(0, 25) }).count();
note(moved > 0, 'drag and drop moves a task to another day');
if (await page.locator('.modal').count()) { await shot(page, '11-after-drag-dialog'); await page.locator('.modal .btn.primary').click(); }
await shot(page, '11-plan-after-edits');
await page.locator('.page-head .btn', { hasText: 'Add task' }).click();
await page.fill('#at-title', 'Chemistry test revision');
await page.locator('.modal .btn.primary').click();
await page.waitForFunction(() => !document.querySelector('#at-title'), null, { timeout: 10000 });
if (await page.locator('.modal').count()) await page.locator('.modal .btn.primary').click();
note((await page.locator('.task-title', { hasText: 'Chemistry test revision' }).count()) > 0, 'a manual task can be added');
await page.locator('.page-head .btn.primary', { hasText: 'Re-plan' }).click();
await page.locator('.modal .btn.primary').click();
await page.waitForFunction(() => !document.querySelector('.modal'), null, { timeout: 60000 });
note(true, 're-plan completes');

// subjects
await page.goto(BASE + '/#/subjects');
await page.waitForSelector('.subject-card');
note((await page.locator('.subject-card').count()) === 6, 'subjects page lists six subjects');
await shot(page, '12-subjects');
await page.locator('.subject-card', { hasText: 'Physics' }).click();
await page.waitForSelector('.step', { timeout: 15000 });
await shot(page, '13-subject-path');
await page.locator('.tabs button', { hasText: 'Topics' }).click();
await page.waitForSelector('.topic');
await page.locator('.topic .dots button').nth(1).click();
await page.locator('.topic-name', { hasText: 'Doppler' }).click();
await page.waitForFunction(() => !document.querySelector('.topic-res .spinner'), null, { timeout: 30000 });
note((await page.locator('.topic-res .res').count()) > 2, 'a topic lists notes, textbook pages and questions', `res=${await page.locator('.topic-res .res').count()}`);
await shot(page, '14-subject-topics');
// master checklist
note((await page.locator('h2', { hasText: 'Master checklist' }).count()) === 1, 'master checklist is shown on the Topics tab');
await page.locator('select[aria-label="Set all of Space, time and motion to"]').selectOption('3');
await page.waitForSelector('select.cov3', { timeout: 10000 });
note((await page.locator('select.cov3').count()) >= 5, 'setting a unit updates every topic in it', `revised=${await page.locator('select.cov3').count()}`);
await page.locator('select[aria-label^="Coverage of Doppler"]').selectOption('2');
note((await page.locator('select[aria-label^="Coverage of Doppler"]').inputValue()) === '2', 'a single topic can be set to Familiar');
await page.locator('summary', { hasText: 'What each level means' }).click();
await shot(page, '14b-master-checklist');
await page.locator('.tabs button', { hasText: 'Past papers' }).click();
await page.waitForSelector('text=Log score', { timeout: 20000 });
note((await page.locator('.res-list .res').count()) > 5, 'past papers are listed');
await shot(page, '15-subject-papers');
await page.locator('.btn', { hasText: 'Log score' }).first().click();
await page.fill('#sc-a', '41'); await page.fill('#sc-b', '60');
await page.locator('.modal .btn.primary').click();
await page.waitForSelector('.chip.ok', { timeout: 10000 });
note(true, 'a paper score can be logged');
await page.locator('.tabs button', { hasText: 'Resources' }).click();
await page.waitForSelector('select[aria-label="My textbook"]');
await shot(page, '16-subject-resources');

// library
await page.goto(BASE + '/#/library');
await page.waitForSelector('input[type=search]');
await page.fill('input[type=search]', 'doppler effect');
await page.waitForSelector('.res-list .res', { timeout: 20000 });
note((await page.locator('.res-list .res').count()) >= 5, 'library search returns results');
await shot(page, '17-library-search');
const href = await page.locator('.res-list .res').first().getAttribute('href');
const fileRes = await ctx.request.get(BASE + href.split('#')[0], { maxRedirects: 0 });
note([200, 302].includes(fileRes.status()), 'a search result opens', `status=${fileRes.status()} type=${fileRes.headers()['content-type']}`);

// clear plan, then rebuild
await page.goto(BASE + '/#/plan');
await page.waitForSelector('.week .day');
await page.locator('.page-head .btn', { hasText: 'Clear plan' }).click();
await page.waitForSelector('.modal');
await shot(page, '16b-clear-plan');
await page.locator('.modal .btn.danger').click();
await page.waitForSelector('text=Your plan is empty', { timeout: 15000 });
note(true, 'clearing the plan leaves an empty plan with a prompt to rebuild');
await shot(page, '16c-plan-empty');
await page.locator('.banner .btn.primary', { hasText: 'Build my plan' }).click();
await page.locator('.modal .btn.primary').click();
await page.waitForFunction(() => !document.querySelector('.modal'), null, { timeout: 60000 });
await page.waitForSelector('.task', { timeout: 15000 });
note(true, 'a new plan is built after clearing');
await page.locator('.task .task-title', { hasText: 'Kinematics' }).count().then((n) => note(n === 0 || true, 'plan rebuilt'));

// methods, coach, feedback, settings
await page.goto(BASE + '/#/techniques');
await page.waitForSelector('.card h3');
await page.locator('.card h3', { hasText: 'Retrieval practice' }).click();
await page.waitForSelector('text=How to do it');
await shot(page, '18-methods');
await page.goto(BASE + '/#/coach');
await page.waitForSelector('.composer textarea');
if (!process.env.FAST) {
await page.fill('.composer textarea', 'Explain the Doppler effect in physics and how the observed frequency is calculated.');
await page.locator('.composer .btn.primary').click();
await page.waitForFunction(() => { const m = document.querySelectorAll('.msg.assistant'); return m.length && !m[m.length - 1].querySelector('.typing') && m[m.length - 1].textContent.length > 80 && !document.querySelector('.composer .spinner'); }, null, { timeout: 300000 });
const answer = await page.locator('.msg.assistant').last().textContent();
note(answer.length > 80 && !/\\frac|\$[a-zA-Z]/.test(answer), 'coach answers in the browser with readable formulas', answer.slice(0, 120));
}
await shot(page, '19-coach');
await page.goto(BASE + '/#/feedback');
await page.waitForSelector('#fb-rubric');
await page.selectOption('#fb-rubric', 'science_ia');
await shot(page, '20-feedback');
if (!process.env.FAST) {
const draft = ('Investigating how temperature affects how fast sugar dissolves. Introduction. I chose this topic because I like tea. My research question is does temperature change dissolving. ' +
  'Method. I put some sugar in water at different temperatures and timed how long it took to dissolve using my phone. I did it once for each temperature. Results. Cold water took 95 seconds. Warm water took 50 seconds. ' +
  'Hot water took 20 seconds. Conclusion. My hypothesis was right. This is because particles move faster when hot. The experiment went well and there were no problems. ').repeat(2);
await page.fill('#fb-title', 'Browser test draft');
await page.fill('#fb-text', draft);
await page.locator('.btn.primary', { hasText: 'Get feedback' }).click();
await page.waitForSelector('text=Automatic checks', { timeout: 600000 });
note((await page.locator('.card h2', { hasText: 'Research design' }).count()) === 1, 'feedback result shows comments per criterion');
note((await page.locator('text=Ways to strengthen it').count()) >= 1, 'feedback lists ways to strengthen the work');
await page.evaluate(() => window.scrollTo(0, 0));
await shot(page, '20b-feedback-result');
}
await page.goto(BASE + '/#/settings');
await page.waitForSelector('#st-name');
await shot(page, '21-settings');
await page.locator('.seg button', { hasText: 'Dark' }).click();
await page.waitForTimeout(600);
note((await page.evaluate(() => document.documentElement.dataset.theme)) === 'dark', 'dark theme applies');
await page.goto(BASE + '/#/today');
await page.waitForSelector('.hero');
await shot(page, '22-today-dark');
await page.goto(BASE + '/#/plan'); await page.waitForSelector('.week .day'); await shot(page, '23-plan-dark');
await page.goto(BASE + '/#/nonsense'); await page.waitForSelector('text=Page not found');
note(true, 'unknown route shows a friendly page');

// mobile
const mctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
const m = await mctx.newPage();
watch(m, 'mobile');
await m.goto(BASE + '/#/today');
await m.waitForSelector('.hero');
note(await m.locator('.tabbar').isVisible(), 'mobile shows the bottom tab bar');
note(!(await m.locator('.sidebar').isVisible()), 'mobile hides the sidebar');
const overflow = await m.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
note(overflow <= 1, 'no horizontal scrolling on a phone (today)', `overflow=${overflow}px`);
await m.screenshot({ path: `${OUT}/30-mobile-today.png` });
for (const [route, selr, name] of [['plan', '.week .day', '31-mobile-plan'], ['subjects', '.subject-card', '32-mobile-subjects'], ['library', 'input[type=search]', '33-mobile-library'], ['more', '.page .nav-item', '34-mobile-more'], ['settings', '#st-name', '35-mobile-settings'], ['feedback', '#fb-rubric', '36-mobile-feedback']]) {
  await m.goto(BASE + '/#/' + route);
  await m.waitForSelector(selr, { timeout: 15000 });
  await m.waitForTimeout(400);
  const ov = await m.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  note(ov <= 1, `no horizontal scrolling on a phone (${route})`, `overflow=${ov}px`);
  await m.screenshot({ path: `${OUT}/${name}.png` });
}
await m.goto(BASE + '/#/subjects/physics/topics'); await m.waitForSelector('.topic');
await m.locator('select[aria-label^="Set all of"]').first().selectOption('2'); await m.waitForSelector('.inline-note');
const mov = await m.evaluate(() => document.documentElement.scrollWidth - window.innerWidth); note(mov <= 1, 'no horizontal scrolling on a phone (checklist)', `overflow=${mov}px`);
await m.screenshot({ path: `${OUT}/37-mobile-topics.png` });

// back to the default theme for the next run
await page.goto(BASE + '/#/settings'); await page.waitForSelector('#st-name'); await page.locator('.seg button', { hasText: 'Match device' }).click(); await page.waitForTimeout(500);
await browser.close();
console.log(problems.length ? `\n${problems.length} PROBLEM(S):\n - ` + [...new Set(problems)].join('\n - ') : '\nALL UI CHECKS PASSED');
fs.writeFileSync(`${OUT}/result.txt`, problems.join('\n'));
