// Browser journeys against the real API (not the development adapter). Start the stack first:
//   scripts/dev/stack.sh start        (dev OIDC issuer, API, worker, web on :5174 in integration mode)
//   node apps/web/tests/e2e/real-backend.mjs [--base http://127.0.0.1:5174] [--mail .local/run/mail]
// Covers J1 (sign-in through OIDC, personal workspace), P-07 (connect the test CRM with an API key), a real task
// run, J2 (create organization, invite by email, accept
// from the emailed link as the invitee) and J3 (switch workspaces; content stays per workspace).
import { createRequire } from 'node:module';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

const { chromium } = createRequire(import.meta.url)('playwright');
const args = Object.fromEntries(process.argv.slice(2).reduce((acc, v, i, all) => (v.startsWith('--') ? [...acc, [v.slice(2), all[i + 1]]] : acc), []));
const base = args.base || 'http://127.0.0.1:5174';
const mailDir = args.mail || '.local/run/mail';
let passed = 0, total = 0;
const expect = (name, ok, detail = '') => { total++; if (ok) passed++; console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}${ok ? '' : ' ' + detail}`); if (!ok) process.exitCode = 1; };
const stamp = Date.now().toString(36);

const browser = await chromium.launch();

async function person(email, name) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'en-US' });
  await context.addInitScript(() => { try { localStorage.setItem('workx-locale', 'en'); } catch { /* ignore */ } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  return { context, page, errors, email, name };
}

async function signIn(p, start = '/') {
  await p.page.goto(base + start);
  await p.page.waitForURL(/\/login/);
  await p.page.click('[data-action="auth-continue"]');
  await p.page.waitForSelector('input[name="email"]');
  await p.page.fill('input[name="email"]', p.email);
  await p.page.fill('input[name="name"]', p.name);
  await p.page.click('button');
}

// ---- J1: first sign-in provisions a personal workspace with a starter workmate
const alex = await person(`alex-${stamp}@example.com`, 'Alex');
await signIn(alex);
await alex.page.waitForSelector('.app-layout', { timeout: 15000 });
expect('J1 sign-in lands in the app', /\/t\/ten_[^/]+\/home$/.test(alex.page.url()), alex.page.url());
expect('J1 starter workmate shown on Home', (await alex.page.textContent('body')).includes('My Workmate'));

// P-07: connect the test CRM with its API key (sent once to the broker). Without it the task has no CRM tools.
const personalId = /\/t\/(ten_[^/]+)\//.exec(alex.page.url())?.[1];
await alex.page.goto(`${base}/t/${personalId}/team/connections`);
await alex.page.click('[data-action="space-add-connection"]');
await alex.page.waitForSelector('select[name="connectorId"] option[value="crm"]', { state: 'attached' });
await alex.page.fill('#space-connection-form input[name="name"]', 'Test CRM');
await alex.page.selectOption('select[name="connectorId"]', 'crm');
await alex.page.fill('#space-connection-form input[name="secret"]', process.env.WORKX_DEV_CRM_KEY || 'dev-crm-key');
await alex.page.click('[data-action="space-save-connection"]');
await alex.page.waitForSelector('.ws-connection', { timeout: 10000 });
const card = await alex.page.textContent('.ws-connection');
expect('P-07 CRM connection created and shown as connected', card.includes('Test CRM') && card.includes('Connected'), card);
expect('P-07 the API key is not shown anywhere', !(await alex.page.content()).includes('dev-crm-key'));

// P-07b: connect the Notes test service through OAuth (discovery, dynamic registration, PKCE) and come back.
await alex.page.click('[data-action="space-add-connection"]');
await alex.page.waitForSelector('select[name="connectorId"] option[value="notes"]', { state: 'attached' });
await alex.page.fill('#space-connection-form input[name="name"]', 'My notes');
await alex.page.selectOption('select[name="connectorId"]', 'notes');
await alex.page.fill('#space-connection-form input[name="config.base_url"]', args.notes || 'http://127.0.0.1:8310/mcp');
await alex.page.click('[data-action="space-save-connection"]');
await alex.page.waitForURL(/:8310\/authorize/, { timeout: 15000 });
expect('P-07b browser is sent to the provider with PKCE', /code_challenge_method=S256/.test(alex.page.url()), alex.page.url());
await alex.page.click('button[value="allow"]');
await alex.page.waitForURL(/\/team\/connections/, { timeout: 15000 });
await alex.page.waitForTimeout(800);
const notesCard = await alex.page.locator('.ws-connection', { hasText: 'My notes' }).textContent();
expect('P-07b back in the app, Notes connection authorized', notesCard.includes('Connected'), notesCard);
expect('P-07b the result is announced once and removed from the URL', !alex.page.url().includes('connection='), alex.page.url());

// Start a task on the real API: runner → model gateway → tool gateway (CRM through the connection).
await alex.page.goto(`${base}/t/${personalId}/home`);
await alex.page.click('[data-action="nav"][data-page="new"]');
await alex.page.fill('#task-prompt', 'Summarize this week in three bullets');
await alex.page.click('[data-action="send-task"]');
await alex.page.waitForURL(/\/task\/tsk_/, { timeout: 10000 });
expect('task created through the API and opened', /\/task\/tsk_/.test(alex.page.url()), alex.page.url());
// The orchestrator runs it: runner → model gateway → (dev model or Anthropic) → tool gateway → test CRM.
await alex.page.waitForSelector('.wx-answer-text', { timeout: 60000 });
await alex.page.waitForSelector('.answer-artifact', { timeout: 30000 });
const conversation = await alex.page.textContent('.chat-scroll');
expect('P-05 the workmate answered through the real runtime', conversation.includes('top accounts'), conversation.slice(0, 200));
expect('P-05 the result file is attached to the answer', (await alex.page.textContent('.answer-artifact')).includes('top-accounts.md'));
await alex.page.click('.answer-artifact');
await alex.page.waitForTimeout(500);
expect('P-05 the result file opens with its content', (await alex.page.textContent('body')).includes('Northwind Traders'));
await alex.page.keyboard.press('Escape');

// ---- J2: create an organization and invite Bob by email
await alex.page.click('[data-action="profile"]');
await alex.page.click('[data-action="space-create"]');
await alex.page.fill('input[name="name"]', `Northwind ${stamp}`);
await alex.page.click('[data-action="space-save-organization"]');
await alex.page.waitForTimeout(1500);
expect('J2 organization created and opened', (await alex.page.textContent('body')).includes(`Northwind ${stamp}`));
const orgUrl = alex.page.url();
const orgId = /\/t\/(ten_[^/]+)\//.exec(orgUrl)?.[1];
expect('J2 organization has its own id in the URL', Boolean(orgId), orgUrl);

const bobEmail = `bob-${stamp}@example.com`;
await alex.page.goto(`${base}/t/${orgId}/team/members`);
await alex.page.click('[data-action="space-invite"]');
await alex.page.fill('textarea[name="emails"]', bobEmail);
await alex.page.click('[data-action="space-save-invite"]');
await alex.page.waitForTimeout(800);
expect('J2 invitation listed as pending', (await alex.page.textContent('body')).includes(bobEmail));

// The worker sends the email; read the link from the delivered message.
let link = '';
for (let i = 0; i < 40 && !link; i++) {
  await new Promise(r => setTimeout(r, 500));
  try {
    const files = readdirSync(mailDir).map(f => join(mailDir, f)).sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs);
    for (const f of files) {
      // Decode quoted-printable as a mail client would: soft line breaks and =XX escapes.
      const text = readFileSync(f, 'utf8').replace(/=\r?\n/g, '').replace(/=([0-9A-F]{2})/g, (_, h) => String.fromCharCode(parseInt(h, 16)));
      if (text.includes(bobEmail)) { link = (/(http\S+\/invite\/[A-Za-z0-9_-]+)/.exec(text) || [])[1] || ''; break; }
    }
  } catch { /* directory not created yet */ }
}
expect('J2 worker delivered the invitation email with a link', Boolean(link), mailDir);

const bob = await person(bobEmail, 'Bob');
if (process.env.E2E_DEBUG) {
  bob.page.on('response', r => { if (r.url().includes('/api/')) console.log('   bob', r.request().method(), r.status(), r.url().replace(base, '')); });
  bob.page.on('framenavigated', f => { if (f === bob.page.mainFrame()) console.log('   bob nav', f.url().replace(base, '')); });
}
await bob.page.goto(link.replace(/^http:\/\/[^/]+/, base));
await bob.page.waitForSelector('[data-action="invite-accept"]');
await bob.page.click('[data-action="invite-accept"]');
await bob.page.waitForSelector('[data-action="auth-continue"]');
await bob.page.click('[data-action="auth-continue"]');
await bob.page.waitForSelector('input[name="email"]');
await bob.page.fill('input[name="email"]', bobEmail);
await bob.page.click('button');
await bob.page.waitForSelector('[data-action="invite-accept"]', { timeout: 15000 });
await bob.page.click('[data-action="invite-accept"]');
await bob.page.waitForURL(new RegExp(`/t/${orgId}/home`), { timeout: 15000 });
expect('J2 invitee signs in, accepts and lands in the organization', bob.page.url().includes(orgId));
await bob.page.waitForSelector('.app-layout');
await bob.page.waitForTimeout(1000);
expect('J2 invitee sees the shared starter workmate', (await bob.page.textContent('body')).includes('My Workmate'));

// ---- J3: content stays per workspace; Alex's personal task is not visible to Bob anywhere
const bobBody = await bob.page.textContent('body');
expect('J3 personal task of another user is not visible', !bobBody.includes('Summarize this week in three bullets'));
const tenants = await bob.page.evaluate(async () => (await fetch('/api/v1/me/tenants', { credentials: 'include' })).json());
expect('J3 invitee belongs to personal + the organization', tenants.length === 2 && tenants.some(t => t.id === orgId), JSON.stringify(tenants));
await alex.page.goto(`${base}/t/${orgId}/team/members`);
await alex.page.waitForTimeout(800);
expect('J3 organization members page lists both people', (await alex.page.textContent('body')).includes(bobEmail));

expect('no page errors (Alex)', alex.errors.length === 0, alex.errors.join(' | '));
expect('no page errors (Bob)', bob.errors.length === 0, bob.errors.join(' | '));
await browser.close();
console.log(`\n${passed}/${total} checks passed`);
