# WorkX delivery plan

Started 2026-10-31. This plan orders the agreed scope into phases. The scope is architecture Part 14 §3 and §4 (R1 backlog B-01…B-22, B-UI-01…04), R2 and R3, and the approved decisions in Part 1 §8. Progress is tracked in [`COMPLETION-MATRIX.md`](COMPLETION-MATRIX.md); a phase is complete only when its acceptance criteria pass in automated tests against real local infrastructure (PostgreSQL, Redis). Verification against external services (Anthropic, E2B, Keycloak, Feishu, WeCom, cloud KMS) is tracked separately and is never inferred from fakes.

## Environment used for delivery

| Available here | Not available here (blocks only real-service verification) |
| --- | --- |
| PostgreSQL 16 (local cluster), Redis, Python 3.13 + uv, Node 22 + pnpm, Chromium/Playwright, Java 21, gcc | Anthropic API key, E2B API key, Feishu/WeCom apps and tenants, Keycloak instance (may be downloadable; see P-02), cloud KMS, OpenBao server, SMTP, a container daemon for compose |

Integrations with unavailable services are implemented against their documented protocols, tested against local fakes that speak those protocols (fake OIDC provider, fake Anthropic Messages endpoint, fake E2B sandbox provider, signed fake Feishu/WeCom events), and each has a "real-service verification" entry with the exact commands to run once credentials exist.

## Phase list

Each phase lists scope (backlog IDs), dependencies, working functionality, acceptance criteria, verification commands, and commit boundaries. All commands run from the repository root unless stated.

### P-01 Backend foundation — B-01, part of B-07

- **Depends on:** nothing.
- **Scope:** uv workspace; `services/workx` modular monolith skeleton (`core`, `platform`, `domains`, `trusted`, `entrypoints`); typed settings per entrypoint; SQLAlchemy 2 + psycopg 3; Alembic migrations; RFC 9457 problem-details errors; prefixed IDs; request IDs and redaction; FastAPI app with health/readiness; OpenAPI exported to `packages/contracts/openapi/workx.v1.yaml` and checked for staleness; pytest against a real PostgreSQL; ruff, mypy, import-linter contracts (domains never import `trusted`); CI workflow.
- **Works:** `workx api` serves `/healthz`, `/readyz` (checks DB), `/api/v1/openapi.json`; `workx db upgrade` migrates an empty database.
- **Acceptance:** migrations apply and downgrade cleanly; error responses match problem-details shape; import-linter passes and fails on a deliberate violation (tested); committed OpenAPI matches the generated one.
- **Verify:** `scripts/dev/pg.sh start && uv run --package workx pytest services/workx/tests -q && uv run lint-imports && uv run workx openapi --check`
- **Commits:** (1) workspace + core + settings; (2) DB, migrations, app, tests; (3) lint/contracts/CI.

### P-02 Identity, tenancy, invitations — B-02, B-03, B-04

- **Depends on:** P-01.
- **Scope:** users, login sessions (opaque cookie, hashed, sliding 7 d / absolute 30 d, revocation), OIDC authorization-code + PKCE client (Keycloak as the target; any standards-compliant issuer works), `/auth/login|callback|logout`, CSRF token, `/me`, preferences; tenants (personal auto-provisioned exactly once, organizations), memberships and roles with last-owner protection, departments; invitations with token digests, 7-day expiry, email via outbox; global `POST /invitations/accept` with verified-email match.
- **Works:** sign-in through any OIDC provider; personal workspace on first login; create org; invite, accept, cancel; session revocation.
- **Acceptance:** J1/J2 end-to-end against a local fake OIDC issuer; 50 parallel first logins → one personal tenant; last owner cannot leave/demote; expired/cancelled/foreign-email invitation rejected; replayed acceptance returns the same membership; revoked session rejected.
- **Real-service verification (pending):** Keycloak realm import + login E2E (`infra/keycloak/README.md`).
- **Commits:** identity; tenancy; invitations + outbox email.

### P-03 Authorization, RLS, audit, jobs — B-05, B-07

- **Depends on:** P-02.
- **Scope:** policy evaluator (`authorize(principal, action, resource)`), resource grants (private/selected/workspace), PostgreSQL RLS on every tenant table with `SET LOCAL app.tenant_id`, non-owner app role, audit log, transactional outbox, PG job queue (`SELECT … FOR UPDATE SKIP LOCKED`) with retries, dedupe and DLQ, reconciler skeleton, usage events table.
- **Acceptance:** isolation suite T-ISO (cross-tenant reads/writes via API and via raw SQL under the app role return nothing); admin cannot read a member's private resource; job at-least-once with idempotent handler; DLQ after max attempts.
- **Commits:** authz + grants; RLS + isolation suite; audit + outbox + jobs.

### P-04 Workspace API and web on the real backend — B-06, B-08 (agents), B-UI-02 (backend seed)

- **Depends on:** P-03.
- **Scope:** REST for agents (drafts, immutable versions, publish, sharing, skills catalog), projects, files/library metadata, automations, scenarios, members/departments/activity, sharing, tenant settings, notifications; tenant event stream (SSE, IDs only); test-only seed endpoint loading the prototype fixture (refused unless `WORKX_ENABLE_TEST_SEED=true` and environment ≠ production); `HttpTransport` mapping (snake_case, `{items,next_cursor}`, ETag/If-Match, stable Idempotency-Key per action).
- **Works:** `apps/web` production mode against the real API for every non-execution screen.
- **Acceptance:** web Playwright journeys J1–J3 against API + fake OIDC; fidelity capture `--target web` against the real backend passes like the adapter run; agent versions immutable (DB trigger test).
- **Commits:** per resource group; transport mapping; e2e.

### P-05 Agent runtime — B-09, B-10, B-11, B-12, B-14

- **Depends on:** P-04.
- **Scope:** runner protocol JSON Schemas + Python models; `runtime/runner` (Claude Agent SDK adapter, hooks, control loop, drain) with no import of `workx`; `SandboxProvider` interface with `e2b` and `local_process` implementations; E2B template definition; orchestrator (attempts, leases, fencing tokens, sandbox lifecycle, staging, event log, SSE with replay by `Last-Event-ID`); model gateway (Anthropic Messages proxy with per-task tickets, budgets, usage); broker tickets; tool gateway (class 0/A tools, test CRM API, ledger, write dedupe across attempts); cancel, retry, interruption recovery; approvals.
- **Acceptance:** vertical slice with fakes: task → runner in `local_process` sandbox → fake Anthropic endpoint (tool_use stream) → tool gateway → ledger → artifact staged → SSE stream; no real key in sandbox env (canary); cancel mid-run; killed orchestrator → `interrupted` → retry without duplicate CRM write; fenced stale attempt writes rejected.
- **Real-service verification (pending keys):** same slice with `SANDBOX_PROVIDER=e2b`, real Anthropic key in the model gateway only.
- **Commits:** protocol; runner; providers; gateways; orchestrator; recovery/approvals; web conversation wiring.

### P-06 Artifacts — B-13

- **Depends on:** P-05. Ingestion from `outputs/`, path/symlink/size checks, XLSX/DOCX/PPTX/PDF/CSV/MD validation, object storage (filesystem + S3-compatible), versioning, authorized download, Library previews from real data.
- **Acceptance:** malicious path/symlink/zip-bomb fixtures rejected; valid Office files stored and downloadable only by authorized users.

### P-07 Credentials and connections — B-15, B-16, B-17, B-18

- **Depends on:** P-03 (P-05 for runtime use). `KeyProvider` (local AES file, OpenBao Transit, cloud KMS interface), envelope encryption, secret versions and rotation, broker resolution with single-flight refresh, connections API and UI wiring, OAuth (generic, Feishu user, MCP with PKCE + pre-registration/CIMD/DCR), `needs_auth` pause/resume, org-shared connections with usage policies, revocation effects on running tasks.
- **Acceptance:** secrets never returned or logged (canary); rotation without downtime; refresh race single-flight; needs_auth task resumes after consent (fake OAuth server); revoked connection stops tool use in active task.

### P-08 Knowledge — B-19, B-20

- **Depends on:** P-06, P-05. Upload, security checks, parser client (Tika server) with in-process fallbacks, structure-aware chunking, embeddings gateway, PostgreSQL FTS (+ pgvector when installed), hybrid retrieval with ACL filtering, `knowledge_search` tool, citation validation, eval harness.
- **Acceptance:** J7 with local files; T-KN ACL tests; eval harness reports precision on the bundled labeled set.

### P-09 Channels — B-21 (Feishu), R2 WeCom

- **Depends on:** P-05, P-07. Bindings, webhook ingress with signature/decryption verification, event dedupe, identity linking, task creation, delivery with retries, inbox API; WeCom adapter.
- **Acceptance:** J6 with signed fake events; replayed event creates no duplicate; group privacy rule.

### P-10 R2 expansion

Automations scheduler; organization SSO (per-org OIDC/SAML via Keycloak brokering) with `TENANT_REAUTH_REQUIRED`; connector knowledge sync; Credential Worker (class D) + Feishu CLI wrapper.

### P-11 R3 commercialization

Plans, seats and quota enforcement; billing integration interface; directory sync (SCIM); BYO model keys; private-deployment packaging; regional cell routing.

### P-12 Hardening — B-22, B-UI-03, B-UI-04, R1 hardening

Security test suites (ticket replay, SSRF, path traversal, authz fuzzing), CI fidelity job, compose stack, OpenTofu skeletons, runbooks, backup/restore drill script, load test scenarios.

## Explicitly not in scope

- Rejected in Part 1 §8: decisions 18–24, 28 (Agent SDK in the API process, secrets in sandbox `.env`, copying Feishu CLI login caches, E2B volumes for knowledge, `allowed_tools` as a security boundary, MinIO CE, Temporal in R1, third-party component library).
- Optional or measured: Meilisearch (evaluation spike only, decision 11), Temporal (growth path), mobile layouts (decision 26).
- Open product decisions that block only their dependent work: target region / China strategy (16), member-departure ownership rule (17).
