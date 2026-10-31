# Backend integration status

Status as of 2026-10-31. **No WorkX backend exists yet.** Every screen in `apps/web` runs against the in-browser development adapter (`src/dev-backend`). The production transport (`src/api/http-transport.ts`) is written to the architecture's conventions but has never been exercised against a server. Nothing in this app should be described as operational until the control plane, runner, connectors and channel integrations exist and have been verified end to end.

## 1. How the app talks to a backend

| Mode | Selected by | Transport | Bundled in production |
| --- | --- | --- | --- |
| Production | `VITE_API_MODE=http` (`pnpm build`) | `HttpTransport`: `fetch` to `/api/v1` with the session cookie, `X-WorkX-CSRF` on writes, `Idempotency-Key` on POST, tenant events over `EventSource` | Yes |
| Development / demo | any other mode (`pnpm dev`, `pnpm build:demo`) | `DevBackend`: routes over `localStorage` (`workx-dev-backend-v1`), seeded from the prototype fixture, timers for simulated work | No (dynamic import; `scripts/check-production-bundle.mjs` fails the build if adapter code, fixture text or test routes appear) |
| Fidelity tests | `pnpm dev:fidelity` (`VITE_ENABLE_TEST_SEED=true`) | `DevBackend` plus `/__test__/seed` | No (`vite.config.ts` refuses a production build with the flag) |

Screens depend only on `src/api/client.ts` (`api.*`) and the `Transport` interface, so switching to the real backend does not change UI code. It does require the transport work in §2.

## 2. Transport gaps to close before connecting the real API

The view models in `src/api/contracts.ts` keep the prototype's camelCase shapes so screens could be migrated with identical DOM. The architecture's API (Part 11 §3) differs, and `HttpTransport` does not translate yet:

| Architecture convention | Current client behavior | Work needed |
| --- | --- | --- |
| snake_case JSON, prefixed external IDs (`tsk_…`) | Expects camelCase view models | Add a mapping layer per resource in `http-transport.ts` (or a BFF serving view models). IDs are opaque strings in the UI, so prefixes need no change. |
| Cursor pagination `{items, next_cursor}` | Expects bare arrays | Unwrap `items`; add paging to Library, tasks, activity and inbox lists when the server enforces limits. |
| `ETag` / `If-Match` on PATCH/PUT, `412 PRECONDITION_FAILED` | Not sent | Keep the ETag from GET in the query cache and send `If-Match`; on 412 refresh and show `web.requestFailed`. |
| `Idempotency-Key` per user action | A new key per request | Generate the key once per user action and reuse it on retries (currently a retry after a network error would not dedupe). |
| RFC 9457 problem details | Reads `code` and `detail` | Already compatible. UI messages are chosen by `code`. |
| 401 `UNAUTHENTICATED` / `SESSION_REVOKED` | Leaves for `/login` (first visit) or `/session-expired` (after a working session), keeping `return_to` | Done; needs a test against the real API. |
| SSE named events | Listens to `message` and to each type in `TENANT_EVENT_TYPES` | Done; resume with `Last-Event-ID` is browser-native once the server sends `id:`. |

## 3. Endpoints the UI calls

"Arch" is the architecture reference; **proposed** means the UI needs it but Parts 3/8/11 do not define it yet, so the backend team should confirm or replace it.

### Account and tenancy

| Method and path | Used by | Arch | Dev adapter behavior |
| --- | --- | --- | --- |
| `GET /auth/login?intent=login\|signup&return_to=` (navigation, not XHR) | `/login`, `/signup`, `/session-expired`, `/invite/:token` | Part 8 J1, Part 9 §3 | No identity service: Continue goes straight to `return_to`. A yellow notice says so. |
| `GET /me`, `PATCH /me`, `PUT /me/preferences` | Shell, Settings › Profile/General | Part 11 §3 | Single demo user `m1`. |
| `GET /me/tenants`, `POST /tenants`, `GET/PATCH /tenants/{t}` | Space switcher, create organization, workspace settings | J2, J3 | Personal + one organization seeded. |
| `POST /invitations/accept {token}` | `/invite/:token` | J2 | Token is the invitation id (the real API stores digests only and checks the verified email). Errors: `INVITATION_NOT_FOUND`, `INVITATION_EXPIRED`, `INVITATION_CLOSED`. The UI also maps `INVITATION_EMAIL_MISMATCH` and `SEAT_LIMIT_REACHED`, which only the real API can return. |
| `GET/POST /tenants/{t}/invitations`, `POST …/invitations/{id}/accept\|cancel` | Members | J2 | Ported prototype rules (7-day expiry, duplicates rejected). |
| `GET /tenants/{t}/members`, `PATCH …/members/{id}`, `GET …/departments`, `GET …/activity` | Members, Permissions, Activity | Part 3 | Ported prototype rules. |
| `PUT /tenants/{t}/resources/{collection}/{id}/sharing` | Sharing dialog | Part 11 §3.1 | Ported rules; no `If-Match`. |
| `GET /tenants/{t}/shared-agents` | Hub, Home | **proposed** (could be a filter on agents) | Ported rules. |

### Work

| Method and path | Used by | Arch | Dev adapter behavior |
| --- | --- | --- | --- |
| `GET /models` | Composer model menu | Decision Q-02/D-01 | Returns Auto plus Claude tiers. No model is called. |
| `GET/POST /tenants/{t}/agents`, `PATCH …/agents/{id}` | Home, Hub, workmate detail, create/edit dialogs | Part 11 `agents`/`agent_versions` | Edits mutate the agent in place (the real API publishes an immutable version). |
| `GET/POST /tenants/{t}/tasks`, `PATCH …/tasks/{id}`, `POST …/tasks/{id}/messages` | Composer, task list and menus, conversation | Part 11 §3.1, J4 | **Simulated execution:** status `running`, then `succeeded` after 1.6 s with a canned answer and a generated Library file. No Claude Agent SDK, E2B sandbox, runner or tool call is involved. |
| `GET/POST /tenants/{t}/projects`, `PATCH …/projects/{id}` | Projects, project workspace, roster, assign, shared context | Part 11 | Ported prototype rules. |
| `GET /tenants/{t}/artifacts` | Library, file preview | Part 11 `files`/`artifacts` | Prototype fixture files. Preview renders stored text. No object storage. |
| `GET/POST /tenants/{t}/automations`, `PATCH …/automations/{id}` | Automations | Part 11 | Stored only. **No scheduler runs them.** |
| `GET/POST/PATCH/DELETE /tenants/{t}/scenarios` | Business scenarios (drafts) | Prototype "planned" page | Stored only. |
| `GET /tenants/{t}/knowledge-sources`, `POST …/knowledge-sources {fileId}` | Work Context › Knowledge, Library › Knowledge filter | **proposed**, shaped on Part 7 §1 and `knowledge_sources` | **Simulated processing:** `processing`, then `ready` after 1.2 s. Nothing is parsed, chunked, embedded or retrievable. |
| `PUT /tenants/{t}/agents/{id}/knowledge {sourceIds}` | Work Context › Knowledge | **proposed** (real API: publish an agent version with `knowledge_source_ids`) | Replaces the list on the agent. |

### Connections and channels

| Method and path | Used by | Arch | Dev adapter behavior |
| --- | --- | --- | --- |
| `GET/POST /tenants/{t}/connections`, `PATCH …/connections/{id}` | Organization › Connections | Part 6 | Metadata only. The UI never sends secrets on this route. No OAuth flow exists. |
| `GET/POST /tenants/{t}/channel-bindings`, `PATCH/DELETE …/{id}` | Ecosystem, add-binding wizard, workmate Ecosystem tab | Part 6, Part 8 channel journeys | Ported prototype rules (`bindingIsReady`). |
| `PUT /tenants/{t}/channel-bindings/{id}/connection` | Connection setup dialog | Part 6 §5 | The dialog sends the whole draft, **including secret fields** such as the app secret. The adapter keeps only non-secret fields, confirmations and the **simulated** test result (`sanitizeConnection`), and drops the secrets. The real API must pass secrets to the credential broker (`put_secret`, Part 6 §3), redact them from logs and never return them. The connection test runs in the browser (300 ms per stage) and contacts no platform. The real test belongs on the server. |
| `POST /tenants/{t}/channel-messages` | "Simulate incoming message" (shown only when `runtime.simulated`) | Development only | Creates a channel run and task, then runs the simulated pipeline. The real system receives platform webhooks at `/channels/{platform}/{binding_public_id}/events` (Part 11) and has no such endpoint. |
| `GET /tenants/{t}/channel-runs`, `POST …/channel-runs/{id}/cancel\|retry-execution\|retry-delivery\|replay` | Channel workbench, channel task detail | Part 8 channel journeys | Simulated execution and **simulated delivery**. Nothing is sent to Feishu or WeCom. `replay` exists only for the demo. |

### Tenant event stream (proposed)

`GET /tenants/{t}/events` (SSE) carries tenant-scoped changes the shell needs: task status (sidebar unread dots, completion toasts), `channel.run.updated` (workbench), `knowledge.source.updated` (status tags), and membership/tenant updates. The architecture defines only per-task streams (`/tasks/{id}/events`, Part 9 §5). Options for the backend team:

- Add this stream, carrying IDs only (Part 11 §4 rules) and filtered by the caller's permissions.
- Or reject it. The client then polls list endpoints and opens per-task streams for the open conversation.

The UI handles the event names in `TENANT_EVENT_TYPES` and refreshes on anything else, so either choice is a transport change only.

## 4. Not built in the UI because it depends on backend behavior

These are architecture features with no screen yet. The UI work is small once the API exists:

- Streaming assistant output (`assistant.delta`), tool timeline (`tool.started/finished`), approvals (`approval.requested`) and in-task authorization prompts (`auth.required`, `NEEDS_AUTH`) in the conversation view.
- OAuth connect flows for connectors (`/oauth/callback/{provider}`) and per-member connection consent.
- File upload (presigned PUT) for Library and Knowledge. Today Knowledge can only use existing Library files.
- Usage, budgets and quotas (`usage.updated`, `QUOTA_EXCEEDED`). The Usage tab shows prototype content.
- Organization SSO re-authentication (`403 TENANT_REAUTH_REQUIRED`).

## 5. Verification that only a real environment can provide

- Sign-in, sign-up and session revocation through Keycloak, including `return_to` validation on the server (the client also validates it, see `safeReturnTo`).
- Invitation acceptance with token digests, verified-email matching and seat limits.
- Task execution through the runner, Claude Agent SDK and E2B sandbox, with event ordering and resume.
- Channel webhooks, signature checks, delivery to Feishu/WeCom, and dedupe on `(binding, platform_event_id)`.
- Knowledge ingestion (Tika, chunking, embeddings) and permission-filtered retrieval.
- CSRF, CORS and cookie attributes on the deployed origin.
