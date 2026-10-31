# Backend integration status

Updated with each delivery phase (docs/delivery/PLAN.md). Overall status is in `docs/delivery/COMPLETION-MATRIX.md`.

## 1. Modes

| Mode | Command | Backend | Bundled in production |
| --- | --- | --- | --- |
| Production | `pnpm build` (`VITE_API_MODE=http`) | `HttpTransport` → `/api/v1` (services/workx) | Yes |
| Real API, local | `scripts/dev/stack.sh start` → http://127.0.0.1:5174 (`pnpm dev:api`) | Local API + worker + development OIDC issuer | — |
| Development adapter | `pnpm dev`, `pnpm build:demo` | In-browser `DevBackend` (simulated) | No |
| Fidelity tests | `pnpm dev:fidelity` | `DevBackend` + `/__test__/seed` | No |

Screens use `src/api/client.ts` only. In http mode, `src/api/http-mapping.ts` translates every view-model call to the API's routes, field names (snake_case) and vocabularies (task states, cron schedules, visibility), so no screen code depends on the transport.

## 2. What runs on the real API today (verified)

Verified by `apps/web/tests/e2e/real-backend.mjs` against the running stack (32/32 checks), plus the API test suite on PostgreSQL (`scripts/check.sh backend`):

- **J1:** sign-in through the OIDC code flow. In this environment that means the development issuer; Keycloak uses the same protocol but is not yet verified here. A personal workspace and a starter workmate are created.
- **J2:** create an organization and invite by email. The worker sends the email; the invitee follows the link, signs in and accepts.
- **J3:** workspace separation (another user's private task is invisible; the member list is per workspace).
- **Connections (P-07):** Settings › Connections lists the workspace's connections from the API. Adding one picks a connector from the workspace catalog. API keys are sent once to the credential broker and never shown again. Shared connections are used only by the workmates bound to them (usage policy). Pause/resume maps to suspend/activate. The test CRM is connected this way (key `dev-crm-key`).
- **OAuth connections (P-07b):** choosing an OAuth connector (Notes test service, Feishu Docs) sends the browser to the provider after saving. The provider returns to `/api/v1/oauth/callback`, then to the page the user started from, where a toast reports the result. Connections that need authorization show **Authorize** to their owner. A task stopped for authorization says it continues by itself once the connection is authorized, and links to Connections.
- **Knowledge (P-08):** attaching Library files to a workmate creates knowledge sources; the worker parses, chunks, embeds and indexes them, and the status changes from Processing to Ready (or Processing failed, with the reason). Answers that use the knowledge show numbered citations and a Sources list; citations the workmate did not actually retrieve are removed. Locally, embeddings come from the development hash embedder in the Model Gateway.
- **Channels (P-09):** Ecosystem bindings (Feishu bot, WeCom app) and the channel workbench use the API. The wizard creates the binding; the connection dialog's Save sends app ID / corp ID to the binding and the secrets to the broker; the preview shows the callback URL to admins and a "Link my chat account" code to members. Runs show real stages, including "Account not linked", "Not addressed to the bot" and blocked deliveries. Locally, replies go to `workx dev-channels`. Other connection methods (Feishu webhook/API, WeCom AI bot and webhook) have no backend yet; saving them fails.
- **Task execution:** a task started in the browser runs through the real orchestrator, runner, Model Gateway, Tool Gateway and test CRM. The conversation shows the answer and the result file. Locally the upstream model is `workx dev-model` (scripted) unless `WORKX_ANTHROPIC_API_KEY` is set; see `runtime/README.md`. Approve/reject, stop and retry are wired to the API.
- **Workspace data:** workmates (each save that changes runtime fields publishes an immutable version), projects (roster, shared context), Library files (any validated type; downloads go through the API), tasks (create, rename, pin, archive, unread, assign, review, follow-up, cancel), automations (cron and time zone; the worker's scheduler creates a task as the owner at each slot, once), scenarios, sharing, members, departments, invitations, the activity feed (audit log, managers only), and the tenant event stream.

## 3. Not yet served by the API

These calls are answered inside the transport: lists return empty, writes fail with `NOT_AVAILABLE`. Each becomes real in the listed phase.

| Area | Calls | Phase |
| --- | --- | --- |
| Simulated channel messages | `/channel-messages` (development adapter only) | — |

## 4. Contract notes for reviewers

- **Proposed additions now implemented:**
  - the tenant event stream `GET /tenants/{t}/events` (named SSE frames, `Last-Event-ID` resume, audience filtering, re-checks the session and membership every 30 s);
  - `POST /invitations/preview` (organization name, role, inviter);
  - `membership_id` on workspace summaries.
- **Pagination:** list endpoints return arrays. Cursor pagination (`{items, next_cursor}`) is implemented only on the audit log so far.
- **Optimistic concurrency (`ETag` / `If-Match`):** not yet implemented in the API or the client. Rows carry `row_version` for it. Tracked for P-12.
- **Idempotency-Key:** sent on every POST. The API requires it for creating organizations, invitations and tasks. The client never retries automatically, so one key per request is one key per user action.
- **Manager-only lists the UI loads for every member** (invitations, activity): a 403 is shown as an empty list.

## 5. Real-service verification still needed

- Keycloak sign-in: `infra/keycloak/README.md` (scripted check ready; this environment cannot start the server).
- SMTP delivery (`WORKX_MAIL_URL=smtp://…`); here mail is written to files.
- Everything that depends on P-05 and later: Claude Agent SDK, E2B, connectors, Feishu/WeCom.
