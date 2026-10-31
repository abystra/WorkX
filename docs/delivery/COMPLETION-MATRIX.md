# Completion matrix

Every agreed capability, with three independent statuses. Updated at each phase checkpoint.

- **Impl**: code exists in the repository for the real system (not the frontend development adapter).
- **Tests**: automated tests pass in this environment against real local infrastructure (PostgreSQL, Redis) and protocol-level fakes for external services.
- **Real**: verified against the real external service. `n/a` when no external service is involved.

Legend: ✅ done · 🟡 partial (see note) · ⬜ not started · ⛔ blocked (reason in note)

| ID | Capability | Phase | Impl | Tests | Real | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| B-01 | Monorepo, CI, contracts pipeline | P-01 | ✅ | ✅ | n/a | uv workspace, import-linter, OpenAPI check, tests on real PG. `.github/workflows/ci.yml` written but not yet run on GitHub |
| B-02 | Identity: OIDC login, sessions, revocation | P-02 | ✅ | ✅ | ⛔ | Tested with the protocol-level dev issuer (`workx dev-oidc`) in-process and as real processes. Keycloak run blocked here (starting a downloaded server is not permitted); realm + `scripts/verify/keycloak_login.py` ready (infra/keycloak/README.md). SSE revocation check arrives with the event stream (P-04) |
| B-03 | Tenancy: personal provisioning, orgs, memberships, roles | P-02 | ✅ | ✅ | n/a | 50-parallel first-login test, last-owner DB constraint, Part 3 §6.1 rules |
| B-04 | Invitations with email outbox | P-02 | ✅ | ✅ | ⬜ | Outbox → worker → email tested end to end with FileMailer. Real: SMTP server |
| B-05 | Authz, grants, RLS, isolation suite | P-03 | ✅ | ✅ | n/a | RLS on every tenant table for the runtime role; cross-tenant lookups only via named definer functions; T-ISO 01–08; Python evaluator and SQL `workx_can()` parity test. Project grants activate when projects exist (P-04). Membership cache (Valkey) not built: lookups hit PostgreSQL per request |
| B-06 | Web shell/admin on real API | P-04 | ✅ | ✅ | n/a | Web http transport + mapping; browser journeys J1–J3 against the real API (`apps/web/tests/e2e/real-backend.mjs`, 14/14). ETag/If-Match and list pagination not yet (P-12). Connections/knowledge/channels screens wait for P-07..P-09 |
| B-07 | Jobs/outbox, reconciler, audit, usage events | P-03 | ✅ | ✅ | n/a | PG queue with SKIP LOCKED leases, outbox fan-out dedupe, backoff, DLQ + `workx jobs dead/retry`, reconciler skeleton, audit API, idempotent usage metering |
| B-08 | Agents: drafts, versions, publish, sharing, skills | P-04 | ✅ | ✅ | n/a | Saving runtime fields publishes an immutable version (DB trigger); tasks pin versions; starter workmate per new workspace |
| B-09 | Runtime release, E2B template, Runner v1 | P-05 | ✅ | ✅ | ⛔ | Runner (SDK + messages engines), protocol schemas, E2B provider and template (renders offline). SDK engine verified with the real bundled Claude Code CLI through the gateways. Real: E2B key needed (runtime/README.md) |
| B-10 | Model Gateway, budgets, usage | P-05 | ✅ | ✅ | ⛔ | Ticket auth, pinned model, per-task/monthly budgets, streaming passthrough, usage metering; upstream verified only against the scripted dev model. Real: Anthropic key |
| B-11 | Broker tickets, Tool Gateway (class 0/A), ledger | P-05 | ✅ | ✅ | n/a | Digest-only tickets, MCP gateway, tool scopes, ledger dedupe across attempts, SSRF-guarded web_fetch; class-A connector is the platform test CRM until P-07 |
| B-12 | Orchestrator, leases, fencing, events, SSE | P-05 | ✅ | ✅ | ⛔ | Fence-checked frames, leases + heartbeat, coalesced deltas, task SSE with replay; web conversation shows real runs (17/17 browser checks). Real: with E2B + Anthropic |
| B-13 | Artifact ingestion, validation, Library | P-06 | ✅ | ✅ | ⬜ | Content-based validation (OOXML structure, traversal, bombs, macros, PDF, UTF-8, images), previews, versions with retry dedupe, partial results, tenant-prefixed object keys, authorized download only, uploads. XLSX produced by the real Claude Code CLI downloaded and opened in tests. Filesystem store tested; S3 store needs a real bucket |
| B-14 | Cancel/retry/recovery, approvals | P-05 | ✅ | ✅ | ⛔ | Cancel revokes tickets and kills after 20 s; reconciler → interrupted; retry with next fence, no duplicate writes; approvals bound to argument digests, UI approve/reject. Checkpoints/resume of SDK sessions not built (fresh attempt with history) |
| B-15 | KeyProvider, secret versions, API-key connections | P-07 | ✅ | ✅ | ⛔ | Local (HKDF + AES-GCM), OpenBao Transit and AWS KMS providers; envelope encryption with AAD bound to tenant/credential/version; secret tables readable only by `workx_broker`; rotation with a 10-minute grace, crypto-shredding. Tests: local provider end to end; OpenBao Transit (fake HTTP engine) and AWS KMS (botocore Stubber against the service model) at the protocol level. Real: no OpenBao or KMS reachable here |
| B-16 | OAuth (Feishu user, MCP), needs_auth resume | P-07 | ⬜ | ⬜ | ⬜ | Real: Feishu app, MCP server |
| B-17 | Org-shared connections, usage policies | P-07 | ✅ | ✅ | n/a | Member/tenant scope, policies default to no use, epoch bump on change; tool bindings resolved at task start and re-checked per call |
| B-18 | Member removal / revocation effects on tasks | P-07 | ✅ | ✅ | n/a | Revocation revokes leases naming the connection (active task loses tool use at once, verified in the slice) and shreds secrets; deactivation cancels the member's live tasks and suspends their connections. Ownership rule on departure is open decision 17 |
| B-19 | Knowledge ingest, parse, chunk, embed, index | P-08 | 🟡 | 🟡 | ⬜ | UI on the development adapter only; Real: Tika, embedding provider |
| B-20 | Retrieval tool, citations, ACL | P-08 | ⬜ | ⬜ | n/a | |
| B-21 | Feishu bot channel, delivery, inbox | P-09 | 🟡 | 🟡 | ⬜ | UI on the development adapter only; Real: Feishu app |
| B-22 | Security hardening, runbooks, DR drill | P-12 | ⬜ | ⬜ | ⬜ | Pen test needs an external party |
| B-UI-01 | Prototype styles, icons, i18n, React shell | done | ✅ | ✅ | n/a | Fidelity 272/274 pass, 2 proposed deviations |
| B-UI-02 | Fidelity test seed + web target | P-04 | 🟡 | ✅ | n/a | Adapter seed and web target done (272/274 pass). A backend seed endpoint for capturing fidelity against the real API is deferred to P-12, when every screen is API-backed |
| B-UI-03 | CI fidelity job | P-12 | ⬜ | ⬜ | n/a | |
| B-UI-04 | Design sign-off for new screens | — | 🟡 | n/a | n/a | Documented in apps/web/docs/NEW-SCREENS.md; sign-off is a human decision |
| R2-1 | WeCom channel | P-09 | ⬜ | ⬜ | ⬜ | Real: WeCom app |
| R2-2 | Credential Worker (class D) + Feishu CLI wrapper | P-10 | ⬜ | ⬜ | ⬜ | |
| R2-3 | Connector knowledge sync | P-10 | ⬜ | ⬜ | ⬜ | |
| R2-4 | Automations scheduler | P-10 | ⬜ | ⬜ | n/a | |
| R2-5 | Organization SSO and re-auth | P-10 | ⬜ | ⬜ | ⬜ | |
| R3-1 | Plans, seats, quota enforcement | P-11 | ⬜ | ⬜ | n/a | |
| R3-2 | Billing integration | P-11 | ⬜ | ⬜ | ⬜ | Real: payment provider (not chosen) |
| R3-3 | Directory sync (SCIM) | P-11 | ⬜ | ⬜ | ⬜ | |
| R3-4 | BYO model keys | P-11 | ⬜ | ⬜ | ⬜ | |
| R3-5 | Private deployment packaging | P-11 | ⬜ | ⬜ | ⬜ | |
| R3-6 | Regional cells | P-11 | ⬜ | ⬜ | ⬜ | Depends on open decision 16 |

## Not in scope

See [`PLAN.md`](PLAN.md#explicitly-not-in-scope): rejected decisions 18–24 and 28; Meilisearch evaluation and Temporal are optional; decisions 16 and 17 are open product decisions.
