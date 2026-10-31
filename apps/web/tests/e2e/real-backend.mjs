// Browser journeys against the real API (not the development adapter). Start the stack first:
//   scripts/dev/stack.sh start        (dev OIDC issuer, API, worker, web on :5174 in integration mode)
//   node apps/web/tests/e2e/real-backend.mjs [--base http://127.0.0.1:5174] [--mail .local/run/mail]
// Covers J1 (sign-in through OIDC, personal workspace), P-07 (connect the test CRM with an API key), a real task
// run, J2 (create organization, invite by email, accept
// from the emailed link as the invitee) and J3 (switch workspaces; content stays per workspace).
import { createCipheriv, createHash, randomBytes } from 'node:crypto';
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
const waitUntil = async (check, timeout) => { const end = Date.now() + timeout; while (Date.now() < end) { if (await check()) return true; await new Promise(r => setTimeout(r, 500)); } throw new Error('timed out waiting'); };

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

// ---- P-08 / J7: attach the result file as knowledge, then a task searches it and cites the source.
const agentId = await alex.page.evaluate(async t => (await (await fetch(`/api/v1/tenants/${t}/agents`)).json())[0].id, personalId);
await alex.page.goto(`${base}/t/${personalId}/detail/${agentId}`);
await alex.page.click('[data-action="detail-tab"][data-tab="Work Context"]');
await alex.page.click('[data-action="knowledge-attach"]');
await alex.page.waitForSelector('#knowledge-form');
await alex.page.locator('#knowledge-form label', { hasText: 'top-accounts.md' }).locator('input').check();
await alex.page.click('[data-action="knowledge-save"]');
await alex.page.waitForSelector('.wx-knowledge-row', { timeout: 10000 });
await alex.page.waitForSelector('.wx-knowledge-row .is-delivered', { timeout: 30000 });
expect('P-08 attached file is processed by the worker and shown Ready', (await alex.page.textContent('.wx-knowledge-row')).includes('top-accounts.md'));
await alex.page.goto(`${base}/t/${personalId}/home`);
await alex.page.click('[data-action="nav"][data-page="new"]');
await alex.page.fill('#task-prompt', 'SCENARIO:knowledge Northwind Traders Contoso');
await alex.page.click('[data-action="send-task"]');
await alex.page.waitForURL(/\/task\/tsk_/, { timeout: 10000 });
await alex.page.waitForSelector('.wx-citations', { timeout: 60000 });
const cited = await alex.page.textContent('.chat-scroll');
expect('P-08 the answer cites the knowledge source with a number', cited.includes('your documents say [1]') && (await alex.page.textContent('.wx-citations')).includes('top-accounts.md'), cited.slice(-300));
expect('P-08 the made-up citation was removed', !cited.includes('knc_'));

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

// ---- J6: a Feishu bot bound to the workmate; signed + encrypted callbacks; linking; reply delivered.
const platformsUrl = args.platforms || 'http://127.0.0.1:8320';
const apiUrl = args.api || 'http://127.0.0.1:8000';
const fs = { appId: `cli_${stamp}`, appSecret: 'e2e-app-secret', encryptKey: 'e2e-encrypt-key', verificationToken: 'e2e-verify' };
await fetch(`${platformsUrl}/_apps`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ [fs.appId]: fs.appSecret }) });
const binding = await alex.page.evaluate(async ({ orgId, fs }) => {
  const csrf = (await (await fetch('/api/v1/me')).json()).csrf_token;
  const headers = { 'content-type': 'application/json', 'x-workx-csrf': csrf };
  const agents = await (await fetch(`/api/v1/tenants/${orgId}/agents`)).json();
  const created = await (await fetch(`/api/v1/tenants/${orgId}/channel-bindings`, { method: 'POST', headers, body: JSON.stringify({
    platform: 'feishu', method: 'feishu-bot', name: 'Team bot', agent_id: agents[0].id, capabilities: ['message-receive', 'message-reply'],
    config: { app_id: fs.appId }, secrets: { app_secret: fs.appSecret, encrypt_key: fs.encryptKey, verification_token: fs.verificationToken } }) })).json();
  return created;
}, { orgId, fs });
expect('J6 binding created with a callback URL', Boolean(binding.webhook_url), JSON.stringify(binding));
const feishuPost = async (event) => {
  const key = createHash('sha256').update(fs.encryptKey).digest(), iv = randomBytes(16);
  const cipher = createCipheriv('aes-256-cbc', key, iv);
  const encrypted = Buffer.concat([iv, cipher.update(JSON.stringify(event)), cipher.final()]).toString('base64');
  const body = JSON.stringify({ encrypt: encrypted }), ts = String(Math.floor(Date.now() / 1000)), nonce = randomBytes(6).toString('hex');
  const signature = createHash('sha256').update(ts + nonce + fs.encryptKey + body).digest('hex');
  const path = binding.webhook_url.slice(binding.webhook_url.indexOf('/api/v1'));
  return fetch(apiUrl + path, { method: 'POST', body, headers: { 'content-type': 'application/json', 'x-lark-request-timestamp': ts, 'x-lark-request-nonce': nonce, 'x-lark-signature': signature } });
};
const message = (text, id) => ({ schema: '2.0', header: { event_id: id, event_type: 'im.message.receive_v1', token: fs.verificationToken, tenant_key: 'tk_e2e' },
  event: { sender: { sender_id: { open_id: 'ou_alex' }, sender_type: 'user' }, message: { message_id: `om_${id}`, chat_id: 'oc_e2e', chat_type: 'p2p', message_type: 'text', content: JSON.stringify({ text }) } } });
const sentTexts = async () => (await (await fetch(`${platformsUrl}/_sent`)).json()).map(m => JSON.parse(m.content || '{}').text || m.content);
expect('J6 signed callback accepted', (await feishuPost(message('hello', `e-${stamp}-1`))).status === 200);
await waitUntil(async () => (await sentTexts()).some(t => String(t).includes("don't know who you are")), 20000);
expect('J6 unlinked sender is told how to link (no task)', true);
await alex.page.goto(`${base}/t/${orgId}/ecosystem`);
await alex.page.waitForTimeout(800);
await alex.page.locator('[data-action="eco-preview"]').first().click();
await alex.page.click('[data-action="channel-link-account"]');
const code = (await alex.page.getAttribute('.wx-link-code', 'data-code', { timeout: 10000 }));
expect('J6 the member gets a one-time link code in the app', /^[A-Z0-9]{8}$/.test(code || ''), code);
await alex.page.keyboard.press('Escape');
await feishuPost(message(`link ${code}`, `e-${stamp}-2`));
await waitUntil(async () => (await sentTexts()).some(t => String(t).startsWith('Linked')), 20000);
await feishuPost(message('Summarize this week in three bullets', `e-${stamp}-3`));
await waitUntil(async () => (await sentTexts()).some(t => String(t).includes('/task/tsk_')), 90000);
expect('J6 the linked member\'s request ran and the answer was delivered to the chat', true);
await feishuPost(message('Summarize this week in three bullets', `e-${stamp}-3`));
await alex.page.goto(`${base}/t/${orgId}/inbox`);
await alex.page.waitForTimeout(1500);
const inbox = await alex.page.textContent('body');
expect('J6 the channel workbench lists the real runs with their delivery state', inbox.includes('Delivered') && inbox.includes('Summarize this week'), inbox.slice(0, 300));
const runsNow = await alex.page.evaluate(async t => (await (await fetch(`/api/v1/tenants/${t}/channel-runs`)).json()), orgId);
expect('J6 a replayed platform event creates no second task', runsNow.filter(r => r.event_id === `e-${stamp}-3`).length === 1 && runsNow.find(r => r.event_id === `e-${stamp}-3`).replay_count === 1);

// ---- J3: content stays per workspace; Alex's personal task is not visible to Bob anywhere
const bobBody = await bob.page.textContent('body');
expect('J3 personal task of another user is not visible', !bobBody.includes('Summarize this week in three bullets'));
const tenants = await bob.page.evaluate(async () => (await fetch('/api/v1/me/tenants', { credentials: 'include' })).json());
expect('J3 invitee belongs to personal + the organization', tenants.length === 2 && tenants.some(t => t.id === orgId), JSON.stringify(tenants));
await alex.page.goto(`${base}/t/${orgId}/team/members`);
await alex.page.waitForTimeout(800);
expect('J3 organization members page lists both people', (await alex.page.textContent('body')).includes(bobEmail));

// ---- R2 SSO: the owner signs in through the org's identity provider and requires it; Bob is sent through it.
const alexEmail = alex.email;
await alex.page.goto(`${base}/api/v1/auth/login?idp_hint=acme-sso&return_to=${encodeURIComponent(`/t/${orgId}/home`)}`);
await alex.page.waitForSelector('input[name="email"]');
await alex.page.fill('input[name="email"]', alexEmail);
await alex.page.click('button');
await alex.page.waitForURL(new RegExp(`/t/${orgId}/home`), { timeout: 15000 });
const policy = await alex.page.evaluate(async orgId => {
  const csrf = (await (await fetch('/api/v1/me')).json()).csrf_token;
  const response = await fetch(`/api/v1/tenants/${orgId}/sso`, { method: 'PUT', headers: { 'content-type': 'application/json', 'x-workx-csrf': csrf }, body: JSON.stringify({ required: true, idp_alias: 'acme-sso' }) });
  return response.status;
}, orgId);
expect('SSO the owner (signed in through the provider) requires it for the organization', policy === 200, String(policy));
await bob.page.goto(`${base}/t/${orgId}/home`);
await bob.page.waitForSelector('input[name="email"]', { timeout: 15000 });
expect('SSO a member with a password session is sent to the organization\'s sign-in', /kc_idp_hint=acme-sso/.test(bob.page.url()), bob.page.url());
await bob.page.fill('input[name="email"]', bobEmail);
await bob.page.click('button');
await bob.page.waitForURL(new RegExp(`/t/${orgId}/home`), { timeout: 15000 });
await bob.page.waitForSelector('.app-layout', { timeout: 15000 });
expect('SSO after signing in through it, the member is back in the organization', bob.page.url().includes(orgId));

expect('no page errors (Alex)', alex.errors.length === 0, alex.errors.join(' | '));
expect('no page errors (Bob)', bob.errors.length === 0, bob.errors.join(' | '));
await browser.close();
console.log(`\n${passed}/${total} checks passed`);
