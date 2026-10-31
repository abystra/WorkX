# Part 14 — Validation and delivery plan (request I)

## 1. Risk-ranked technical spikes

Ordered by risk × impact. Each spike is time-boxed and ends with a written result (go / no-go / go-with-changes) appended to the decision log.

| # | Spike | Risk addressed | Time-box | Go criteria | No-go → fallback |
| --- | --- | --- | --- | --- | --- |
| **S-00** | Region & provider availability | C-01: Claude/E2B unavailable for target customers | 3 days + PO decision | PO confirms R1 market where Claude API and E2B operate; legal review on cross-border processing started; Feishu vs Lark app decision | Pause runtime build; scope China cell (alternative harness/model) as separate program |
| **S-01** | SDK in E2B with Model Gateway | Runner viability, streaming via `ANTHROPIC_BASE_URL`, version pinning | 2 weeks | Runner completes 20 scripted tasks; streaming deltas through gateway with < 300 ms added TTFT p95; `setting_sources=[]`, `plugins`, `skills`, `dontAsk`, hooks behave as documented on pinned version; no real key in sandbox (memory scan) | Evaluate Managed Agents (Part 4 §15A) |
| **S-02** | Interrupt, drain, checkpoint, resume | Recovery correctness | 1 week (with S-01) | Cancel stops within 20 s in 95% of runs; resume from checkpoint in a *new* sandbox continues a conversation coherently in ≥ 9/10 scripted cases; `mirror_error` handling tested if SessionStore used | Restart-with-summary strategy only (documented "restart" UX) |
| **S-03** | E2B egress enforcement | Exfiltration, gateway-only egress | 4 days | Only gateway hosts reachable; raw IP, alternate DNS, IPv6, DNS tunneling, HTTP CONNECT to other hosts all fail; live rule update works; document E2B egress IP ranges (for gateway ingress allow-listing) | Route all egress through BYO proxy (beta ◐) or self-hosted sandbox |
| **S-04** | Sandbox users and file permissions | Non-root runner, read-only inputs (C-05) | 3 days | Runner as non-root without sudo is configurable; agent user cannot modify staged inputs via Bash/Python/symlinks | Accept integrity-only guarantee (Part 5 §4); no change to security posture |
| **S-05** | Sandbox lifecycle cost/latency | Cold start, pause/resume, costs | 4 days | p95 create+stage < 5 s; pause/resume semantics confirmed incl. retention; per-attempt infra cost estimate | Warm pool; adjust session reuse policy |
| **S-06** | Identity stack | Keycloak + API session + invitations | 1 week | J1–J2 flows E2E; back-channel logout; social login in target region | Managed IdP or Ory |
| **S-07** | RLS + pooling + performance | Isolation without perf collapse | 1 week | All tenant tables FORCE RLS; PgBouncer transaction mode with `SET LOCAL` correct under concurrency fuzzing; top 20 queries within 1.3× of non-RLS baseline | Application-only filtering + stronger tests (RLS kept on critical tables) |
| **S-08** | MCP OAuth (pre-reg/CIMD/DCR) + Feishu user OAuth | Class B viability | 2 weeks | Successful auth + refresh + revocation against ≥ 3 real MCP servers and Feishu; single-use refresh rotation handled under concurrent calls (100 parallel calls, 0 invalid_grant) | Limit R1 to pre-registered providers |
| **S-09** | Knowledge retrieval eval | PG vs Meilisearch, Chinese quality, ACL latency | 2 weeks | Benchmark built (≥ 200 queries); PG baseline meets Recall@10 ≥ 0.8 on benchmark; decision per Part 7 §7 | Add reranker; consider Meilisearch/OpenSearch |
| **S-10** | Tika 4 parsing quality | Scanned Chinese PDFs, tables | 1 week | ≥ 95% of corpus parses; OCR CER acceptable on scanned set (threshold set from baseline); table locators exact for xlsx | Add Docling path for PDFs |
| **S-11** | Credential Worker isolation (R2 gate) | Class D safety | 2 weeks | gVisor/Firecracker unit per invocation; secrets never in logs/outputs (canary); cold start < 2 s; lark-cli provider works | Do not enable class D; restrict to class A–C |
| **S-12** | Feishu bot ingress + delivery | Channel reliability | 1 week | Event verification, dedupe, ack within platform window; delivery receipts; identity mapping flow | Long-connection mode vs HTTP callback switch |

## 2. First end-to-end vertical slice

**Scope**: organization workspace → authenticated user → Agent task → scoped tool → sandbox execution → streamed result → saved artifact.

| Step | Included | Deliberately excluded |
| --- | --- | --- |
| Identity | Keycloak login, personal + one org tenant, membership | Invitations UI polish, SSO |
| Agent | One published agent version with one curated Skill (`xlsx-builder`) | Agent sharing UI |
| Tool | One class-A connector via Tool Gateway (a WorkX-hosted test API with API key) and `knowledge_search` over a fixed small source | OAuth |
| Execution | Orchestrator, E2B sandbox, Runner, Model Gateway, tickets, egress allow-list | Pause/resume, warm pool |
| Streaming | SSE with replay | Tenant activity stream |
| Artifact | XLSX produced in `outputs/`, validated, stored, downloadable | Previews |
| Ops | OTel traces end-to-end, audit events, usage events | Dashboards beyond basics |

UI: the slice's screens (shell, composer, conversation, library preview) use the ported prototype stylesheets and markup; their catalog states pass `tools/ui-fidelity` comparison in both languages at 1440×900 (Part 15 §8).

Acceptance: user in org A submits "Build a spreadsheet of top accounts from the CRM test API"; sees streaming progress and a tool step; downloads a valid XLSX; a user in org B cannot list/read the task or artifact (API and direct object URL); the sandbox memory/env contains no API key or Anthropic key (canary scan); cancel mid-run works; killing the orchestrator mid-run results in `interrupted` and a successful manual retry without duplicating the CRM write (test API counts calls).

## 3. Phased roadmap

Durations are ranges for the team in §7 and assume S-00 resolves to a supported region.

| Phase | Goal | Main contents | Duration |
| --- | --- | --- | --- |
| P0 Spikes | De-risk | S-00 … S-07 in parallel, S-08/S-09 start | 4–6 weeks |
| P1 SaaS foundations | Real tenancy | Identity, tenants, memberships, invitations, roles, grants, RLS, audit, web shell + switcher + settings/admin, CI/CD, IaC staging | 6–8 weeks (overlaps P0 end) |
| P2 Agent runtime | Vertical slice → R1 runtime | Orchestrator, Runner, gateways, tickets, events/SSE, artifacts, cancel/retry/recovery, budgets, agents UI, task UI | 8–10 weeks |
| P3 Credentials | Classes 0/A/B/C | Broker, KeyProvider, connections UI, OAuth (Feishu user + MCP), needs_auth resume, ledger, revocation flows | 6–8 weeks (overlaps P2) |
| P4 Knowledge | Grounded answers | Upload, Tika/OCR, chunking, embeddings, PG hybrid, citations, eval harness | 6–8 weeks (overlaps P3) |
| P5 Feishu channel | Chat entry | Bindings, ingress, identity mapping, delivery, inbox UI | 4–6 weeks |
| R1 hardening | Launch readiness | Isolation suite, security review/pen test, load/chaos, runbooks, DR drill, full UI fidelity pass (every catalog state pass or approved deviation) | 4 weeks |
| R2 | Expansion | WeCom, Credential Worker (class D) + Feishu CLI, connector knowledge sync, automations, SSO, Meilisearch decision | 3–4 months |
| R3 | Commercialization | Billing, plans/seats enforcement, directory sync, BYO keys, private deployment, regional cells | 4–6 months |

Indicative R1 calendar: **7–10 months** from start with 6–9 engineers. This is an estimate under the stated assumptions, not a commitment.

## 4. Prioritized backlog (R1)

| ID | Item | Depends on | Acceptance criteria |
| --- | --- | --- | --- |
| B-01 | Monorepo scaffolding, CI, contracts pipeline | — | Lint/type/test/import-linter gates; OpenAPI committed and diffed |
| B-02 | Identity: Keycloak, login/callback, sessions, revocation | B-01, S-06 | J1 E2E; revoked session rejected within 60 s on SSE |
| B-03 | Tenancy: tenants, personal auto-provisioning, org create, memberships, roles | B-02 | Concurrency test: 50 parallel first logins → 1 personal tenant; last-owner protection |
| B-04 | Invitations with email outbox | B-03 | J2 E2E; expired/cancelled tokens rejected; replay idempotent |
| B-05 | Authz module + grants + RLS + isolation suite v1 | B-03, S-07 | T-ISO-01..13 pass; admin cannot read private resource |
| B-06 | Web shell, tenant routing, switcher, personal settings, org admin (members/invites/sharing) | B-02..B-05 | J3 E2E; cache cleared on switch; a11y checks pass |
| B-07 | Jobs/outbox, reconciler skeleton, audit, usage events | B-01 | At-least-once delivery with dedupe; DLQ visible |
| B-08 | Agents: drafts, versions, publish, sharing, skills catalog | B-05 | J4 E2E; versions immutable |
| B-09 | Runtime release + E2B template + Runner v1 | S-01..S-04 | Template smoke tests; protocol conformance tests |
| B-10 | Model Gateway with budgets and usage | S-01 | No real key in sandbox; budget stop works |
| B-11 | Broker tickets + Tool Gateway (class 0/A) + ledger | B-07, B-09 | Seq 4 passes; duplicate write prevented across attempts |
| B-12 | Orchestrator: attempts, leases, fencing, sandbox lifecycle, staging, events, SSE | B-09..B-11 | J5 E2E; fenced writes rejected; SSE replay |
| B-13 | Artifact ingestion and library UI | B-12 | Malicious path/symlink tests pass; XLSX/DOCX/PPTX validated |
| B-14 | Cancel/retry/recovery + approvals | B-12 | J10 E2E; chaos tests pass |
| B-15 | KeyProvider + secret versions + connections UI (API key) | B-05, Q-07 | Secrets never returned; rotation without downtime |
| B-16 | OAuth (Feishu user, MCP pre-reg/CIMD) + needs_auth resume | B-15, S-08 | Seq 1, 3, 7 E2E; single-use refresh race test |
| B-17 | Org-shared connections with usage policies | B-15 | Seq 2; non-allowed member gets clear "not available" |
| B-18 | Member removal/connection revocation effects on active tasks | B-12, B-16 | J11 / Seq 8 E2E |
| B-19 | Knowledge upload → parse → chunk → embed → PG index | B-07, S-09, S-10 | J7 E2E; failure states visible |
| B-20 | Retrieval tool + citations validation | B-19, B-11 | Citation precision ≥ target on benchmark; ACL tests T-KN-* |
| B-21 | Feishu bot binding, ingress, identity linking, delivery, inbox UI | B-12, B-16, S-12 | J6 E2E; replayed event creates no duplicate |
| B-22 | Security hardening, pen test fixes, runbooks, DR drill | all | No open high findings; restore drill within RTO |
| B-UI-01 | Port prototype stylesheets, icon paths, avatars, i18n dictionaries; React shell (sidebar, account menu, workspace switcher, search, notifications, toast, overlay hooks) | B-01 | Shell catalog states pass `compare` (en, zh-CN, 1440×900) |
| B-UI-02 | Fidelity test seed endpoint (test builds only) loading `tools/ui-fidelity/fixtures/prototype-seed.json`; implement `web` target in `targets.mjs` | B-03, B-UI-01 | `capture:web` runs every catalog step without step failures |
| B-UI-03 | CI job: capture prototype + web, compare, publish contact sheet and diff summary as build artifacts; fail on `fail` verdicts | B-UI-02 | Job runs on every PR touching `apps/web` or `packages/ui` |
| B-UI-04 | Design sign-off for new states and screens (auth pages, Knowledge, streaming/approval/needs-auth/partial, loading/error/permission) using existing patterns | B-UI-01 | Each new state added to the catalog as `new: true` with recorded approval |

Every backlog item that delivers UI (B-06, B-08, B-12, B-13, B-14, B-16, B-17, B-19, B-21) additionally requires the Part 15 §8 acceptance criteria for its screens.

## 5. Test matrix

| Area | ID range | Representative cases | Level |
| --- | --- | --- | --- |
| Tenant isolation | T-ISO-01..19 | Cross-tenant GET/LIST/PATCH by ID (404); composite FK prevents cross-tenant attach; RLS with wrong `app.tenant_id`; presigned URL for other tenant's object; cache key collision; job with forged tenant; SSE subscribe to other tenant's task; sandbox reuse across sessions forbidden; secret ciphertext moved across tenants fails AEAD; logs contain tenant attributes | Integration + synthetic prod probe |
| Authorization | T-AZ-01..15 | Admin cannot read private resource; visibility "organization" grants read/use only; project removal revokes access; department change grants nothing; deactivated member blocked mid-session; shared agent does not share member-private connection | Unit + integration |
| OAuth | T-OA-01..14 | state reuse/expiry; PKCE missing; issuer mismatch (mix-up); callback with different logged-in user; wrong upstream account on re-auth; refresh single-flight under 100 concurrent calls; single-use refresh token crash window; upstream revocation detection; DCR disabled path; CIMD document served correctly | Integration with fake AS + real provider sandbox |
| Secrets | T-SEC-01..12 | Canary secret never in logs/traces/events/artifacts/checkpoints/transcripts; product API never returns values; non-broker DB role cannot select ciphertext; rotation with in-flight calls; KEK rotation rewrap; memory scan of sandbox for model/tool keys | Integration + staging |
| Sandbox recovery | T-SBX-01..12 | Kill sandbox mid-tool; kill orchestrator; lease expiry with live runner (fenced writes rejected); orphan sweep; checkpoint restore in new sandbox; output ingestion with symlink/hardlink/device/oversize; cancel during approval wait | Chaos tests in CI (nightly) |
| Task idempotency | T-IDM-01..10 | Same Idempotency-Key twice; different body same key; duplicate job delivery; duplicate runner frames; retry after unknown write requires reconciliation; operation ledger dedupe across attempts; artifact dedupe by hash; delivery retry reuses artifact | Unit + integration |
| Knowledge permissions | T-KN-01..10 | Unauthorized chunk never in top-K or snippet; revocation effective on next query; deleted source excluded immediately; revision pinning for running task; cross-tenant same filename; injection-flagged chunk labeling | Integration + eval |
| Channel identity | T-CH-01..10 | Payload claims another tenant (ignored); signature failure; replayed event; unmapped sender; display-name collision does not map; binding paused mid-task → delivery blocked; group reply policy hides private content; Feishu tenant key mismatch | Integration with recorded fixtures + staging app |
| Performance | T-PERF-* | SSE fan-out 5k streams; 200 concurrent attempts; retrieval p95 < 300 ms at 10M chunks [VALIDATE] | Load tests |
| UI fidelity | T-UI-* | Every catalog state (Part 15) in en and zh-CN at 1440×900 (plus 1280×800 subset): pixel compare pass/approved, steps succeed, no console errors or horizontal overflow, keyboard behaviors, axe scan with no new violations | Visual + E2E (CI) |
| Agent evaluation | T-EVAL-* | Golden tasks pass rate ≥ baseline; red-team injection scenarios blocked | Nightly |

## 6. Prototype and documents versus proposed production system

| Capability | Prototype today [PROTO] | Repo docs [DOC] | Proposed production (this package) |
| --- | --- | --- | --- |
| Identity | Demo user "Alex", no login | Real login in P0, Keycloak candidate | Keycloak OIDC, server sessions, revocation |
| Tenancy | localStorage namespaces per space | personal/org tenants, RLS | Same + composite FKs, RLS FORCE, cells |
| Invitations | Simulated accept, no email | Token digest, outbox email | Same; implemented as B-04 |
| Roles/sharing | Client-side checks; visibility metadata | Roles ≠ resource access; grants | Grants authoritative; policy evaluator + RLS |
| Agents | Name/description/instructions stored locally; not used by any model | Versioned agents | Immutable versions with skills/knowledge/tool bindings |
| Tasks | 1.6 s timer, template answer | Task/Attempt/Runner/SSE | Same + ledger, fencing, budgets |
| Model choice | Auto/Doubao/DeepSeek/Claude picker | Claude via SDK | Claude tiers only (C-02) |
| Artifacts | Markdown download only | Ingestion pipeline | Validated multi-format artifacts with versions |
| Knowledge | Free-text context only | Tika + Meilisearch/pgvector | Tika + PG hybrid; Meilisearch measured |
| Connections | Metadata only, secrets never stored | Broker/Gateway, PG+Transit | Same + KeyProvider abstraction, tickets, usage policies |
| Feishu/WeCom | Wizard, params, simulated test, simulated inbound/delivery | Adapters, channel worker | Feishu in R1, WeCom R2 |
| Execution vs delivery | Separated, retry semantics modeled | Separate state machines | Same |
| Automations | Local config, no scheduler | Not designed in detail | R2 scheduler using jobs table |
| Tests | 73 Node behavior tests | Validation lists | Full test matrix (§5), including visual comparison against the prototype |
| UI design | Approved baseline | Not specified | Reproduced exactly; deviations only with recorded reason and approval (Part 15 §5) |

## 7. Team, schedule, cost drivers (assumptions)

**Team (assumption A-3): 6–9 engineers + part-time roles**

| Role | Count | Focus |
| --- | --- | --- |
| Tech lead / architect | 1 | Decisions, security design, reviews |
| Backend (Python) | 2–3 | Tenancy/authz, orchestrator/runtime, knowledge |
| Platform/security engineer | 1 | IaC, CI/CD, trusted zone, KMS, observability, pen-test liaison |
| Integrations engineer | 1 | Broker/OAuth/MCP, Feishu adapters |
| Frontend (React/TS) | 1–2 | Web app migration |
| QA/automation (can be shared) | 0.5–1 | Isolation/E2E suites |
| Product + design | 1 + 0.5 | Scenario definition, UX |
| Part-time: legal/privacy, security reviewer | — | C-01, Q-10, pen test |

**Schedule**: see §3 (R1 in 7–10 months; R2 +3–4 months; R3 +4–6 months).

**Operating-cost drivers** (no figures fabricated; measure in S-05 and pilot):

| Driver | Scales with | Levers |
| --- | --- | --- |
| Model tokens (expected dominant, per [SDK hosting](https://code.claude.com/docs/en/agent-sdk/hosting) ✅) | Tasks × turns × context size | Model tier per agent, context compaction, retrieval instead of stuffing, caching, budgets |
| Sandbox compute | Attempt duration × size; idle policy | Terminate on idle, right-size template, reuse within session |
| Embeddings | Ingested tokens; re-embeds | Incremental chunk reuse; self-hosted model for large tenants |
| Storage | Artifacts, raw files, checkpoints, events | Retention policies, compression, lifecycle tiers |
| Managed infra | PG size/IOPS, Valkey, container hours, Keycloak | Right-sizing; partitioning |
| Egress/bandwidth | Downloads, cross-region | CDN, co-location |
| Third-party | Email, AV, observability, E2B plan, pen tests | Self-hosted where cheaper |
| People | On-call, security reviews | Automation, runbooks |

## 8. Open questions and decisions for the product owner

| ID | Question | Why it matters | Needed by |
| --- | --- | --- | --- |
| **Q-01** | Which markets and regions does R1 serve? Are mainland-China tenants in scope, and must their data and processing stay in China? Feishu or Lark (or both)? | Claude API is unavailable in mainland China/HK/Macau; determines whether the chosen runtime is viable for the target customers (C-01) | Before P0 ends |
| **Q-02** | **Decided 2026-10-31: accepted recommendation.** Remove the multi-vendor model picker and expose Claude tiers only? | C-02 | P2 start |
| **Q-03** | What is the first business scenario (inputs, outputs, success metric)? | Prioritizes connectors, artifact types, knowledge formats | P1 |
| **Q-04** | SaaS only, or must a private/self-hosted edition be planned for R2–R3? | KeyProvider, E2B self-hosting, licensing choices (AGPL components) | P1 |
| **Q-05** | When a member leaves, who owns their private resources: keep with reassignment by admin (recommended), mandatory reassignment, or archive? | C-10 | P1 |
| **Q-06** | May admins see existence metadata of members' private resources in an inventory and perform audited security takedowns? | Admin vs privacy balance | P1 |
| **Q-07** | Approve `KeyProvider` = cloud KMS for managed SaaS (OpenBao Transit for self-hosted)? | C-08 | P1 |
| **Q-08** | Group-chat reply policy: inline content vs link-only when private sources were used? | Data leakage in channels | P5 |
| **Q-09** | Embedding provider choice and acceptable data-processing terms | Knowledge quality, residency | P4 |
| **Q-10** | Default retention periods (events, checkpoints, audit, AI traces) and deletion SLAs | Privacy commitments | P1 |
| **Q-11** | Personal workspaces: allowed to bind Feishu user OAuth (personal account)? Enterprise bot channels only for organizations? | Scope of personal tier | P3 |
| **Q-12** | Are automations (scheduled tasks) needed in R1 for the first scenario? | Scheduler scope | P2 |
| **Q-13** | Plans/quotas for personal vs organization (concurrency, budgets) | Admission control defaults | P2 |
| **Q-14** | Is the "Code" mode (repository/terminal) a product priority for R2? | Runtime features (Git, larger sandboxes) | R2 planning |
| **Q-15** | **Decided 2026-10-31: accepted recommendation.** Where does Knowledge live in the UI? Proposed: inside Workmate detail "Work Context" plus a Library filter, with no new sidebar item | Knowledge has no prototype screen; a new nav item would change the approved IA | Before F4 |
| **Q-16** | **Decided 2026-10-31: accepted recommendation.** Approve darkening `--muted` (3.02:1 contrast) for accessibility, or keep the baseline color? | WCAG AA vs visual fidelity | Before F1 |
| **Q-17** | **Decided 2026-10-31: accepted recommendation.** Confirm replacement copy for simulation-only text (D-02), e.g. the "About this prototype" menu item | Production honesty vs fidelity | Before F1 |
