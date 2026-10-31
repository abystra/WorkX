// Browser check for the new account screens against the development adapter (pnpm dev:fidelity).
// Usage: node tests/e2e/account-screens.mjs [--base http://127.0.0.1:5173] [--shots <dir>]
// Exits non-zero on the first failed expectation. Screenshots (1440x900 and 1280x800, en and zh-CN)
// are written for design review when --shots is given.
import { createRequire } from 'node:module';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';

// Uses the machine's Playwright install (not an app dependency), so resolve it like require() does.
const { chromium } = createRequire(import.meta.url)('playwright');

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, value, i, all) => (value.startsWith('--') ? [...acc, [value.slice(2), all[i + 1]]] : acc), []));
const base = args.base || 'http://127.0.0.1:5173';
const shots = args.shots;
const VIEWPORTS = { desktop: { width: 1440, height: 900 }, laptop: { width: 1280, height: 800 } };
const results = [];
const expect = (name, ok, detail = '') => { results.push({ name, ok }); console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}${ok ? '' : ' ' + detail}`); if (!ok) process.exitCode = 1; };

const browser = await chromium.launch();
async function fresh(locale = 'en', viewport = VIEWPORTS.desktop) {
  const context = await browser.newContext({ viewport, locale: locale === 'en' ? 'en-US' : 'zh-CN' });
  await context.addInitScript(value => { try { localStorage.setItem('workx-locale', value); } catch { /* ignore */ } }, locale);
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto(`${base}/__test__/seed?fixture=prototype&next=${encodeURIComponent('/login')}`);
  await page.waitForSelector('.wx-auth-card');
  return { page, context, errors };
}

{
  const { page, context, errors } = await fresh();
  expect('login renders title', (await page.textContent('#auth-title')) === 'Sign in to WorkX');
  expect('login shows development adapter notice', await page.isVisible('.wx-auth-note.is-dev'));
  await page.click('[data-action="auth-continue"]');
  await page.waitForURL(/\/t\/[^/]+\/home$/);
  expect('login continue opens the workspace (development adapter)', /\/t\/wx-demo\/home$/.test(page.url()), page.url());

  await page.goto(`${base}/login?return_to=${encodeURIComponent('//evil.example/x')}`);
  await page.click('[data-action="auth-continue"]');
  await page.waitForURL(/\/t\/[^/]+\/home$/);
  expect('unsafe return_to falls back to the app root', page.url().startsWith(base), page.url());

  await page.goto(`${base}/login?return_to=${encodeURIComponent('/t/wx-demo/library')}`);
  await page.click('a[data-action="auth-switch"]');
  await page.waitForURL(/\/signup\?return_to=/);
  expect('login links to signup and keeps return_to', decodeURIComponent(page.url()).includes('return_to=/t/wx-demo/library'), page.url());
  await page.click('[data-action="auth-continue"]');
  await page.waitForURL(/\/t\/wx-demo\/library$/);
  expect('signup continue returns to the requested page', true);

  // Invitation: create one through the Members page, then accept it from its link.
  await page.goto(`${base}/t/wx-demo/team/members`);
  await page.click('[data-action="space-invite"]');
  await page.fill('[role="dialog"] textarea, [role="dialog"] input[type="text"], [role="dialog"] input:not([type])', 'new.person@example.com');
  await page.click('[data-action="space-save-invite"]');
  await page.waitForTimeout(300);
  const token = await page.evaluate(() => {
    const root = JSON.parse(localStorage.getItem('workx-dev-backend-v1') || '{}');
    const org = (root.spaces || []).find(s => s.id === 'wx-demo');
    return org?.data.invitations.find(i => i.email === 'new.person@example.com' && i.status === 'pending')?.id;
  });
  expect('invitation created for the test', !!token);
  await page.goto(`${base}/invite/${token}`);
  expect('invite renders title', (await page.textContent('#auth-title')) === 'Join an organization');
  await page.click('[data-action="invite-accept"]');
  await page.waitForURL(/\/t\/wx-demo\/home$/);
  expect('accepting an invitation opens the organization', true);
  await page.goto(`${base}/invite/${token}`);
  await page.click('[data-action="invite-accept"]');
  await page.waitForSelector('.wx-auth-error');
  expect('a used invitation explains it is closed', (await page.textContent('.wx-auth-error')).includes('already used or cancelled'));
  await page.goto(`${base}/invite/not-a-real-token`);
  await page.click('[data-action="invite-accept"]');
  await page.waitForSelector('.wx-auth-error');
  expect('an unknown invitation explains the link is not valid', (await page.textContent('.wx-auth-error')).includes('not valid'));
  await page.click('[data-action="set-language"][data-locale="zh-CN"]');
  expect('language switch re-renders the screen', (await page.textContent('#auth-title')) === '加入组织');

  await page.goto(`${base}/session-expired?return_to=${encodeURIComponent('/t/wx-demo/projects')}`);
  await page.click('[data-action="auth-continue"]');
  await page.waitForURL(/\/t\/wx-demo\/projects$/);
  expect('session expired returns to the page the user was on', true);
  expect('no console or page errors', errors.length === 0, errors.join(' | '));
  await context.close();
}

if (shots) {
  for (const [vpName, viewport] of Object.entries(VIEWPORTS)) {
    for (const locale of ['en', 'zh-CN']) {
      const { page, context } = await fresh(locale, viewport);
      const dir = join(shots, locale, vpName);
      await mkdir(dir, { recursive: true });
      for (const [name, path, prepare] of [
        ['login', '/login'], ['signup', '/signup'], ['invite', '/invite/sample-token'],
        ['invite-error', '/invite/sample-token', async p => { await p.click('[data-action="invite-accept"]'); await p.waitForSelector('.wx-auth-error'); }],
        ['session-expired', '/session-expired'],
      ]) {
        await page.goto(base + path);
        await page.waitForSelector('.wx-auth-card');
        if (prepare) await prepare(page);
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
        expect(`${locale} ${vpName} ${name}: no horizontal overflow`, !overflow);
        await page.screenshot({ path: join(dir, `${name}.png`) });
      }
      await context.close();
    }
  }
}

await browser.close();
console.log(`\n${results.filter(r => r.ok).length}/${results.length} checks passed`);
