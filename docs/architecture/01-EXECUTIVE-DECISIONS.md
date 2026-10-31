# Part 1 — Executive decisions

## 1. Product goals

| ID | Goal | Measure of success (to be quantified with first scenario) |
| --- | --- | --- |
| G-1 | A user or organization member can give an AI partner a task in WorkX and receive a durable, reviewable deliverable. | Task → persisted artifact, survives refresh/restart; failure is visible and retryable. |
| G-2 | Workspaces are real ownership and isolation boundaries. | Zero cross-tenant reads in automated isolation suite; every resource has a non-null `tenant_id`. |
| G-3 | AI partners can use external tools and data **without** raw upstream credentials entering the agent sandbox. | Secret-canary tests never observe credential material in sandbox memory dumps, transcripts, logs, artifacts. |
| G-4 | Organizations can bring their knowledge and get grounded, cited answers that respect permissions. | Retrieval never returns unauthorized chunks; citations resolve to the cited revision. |
| G-5 | Feishu (and later WeCom) users can work with WorkX partners from chat, with correct identity mapping and replies to the originating conversation. | Every inbound event maps to exactly one tenant/binding/principal or is rejected; delivery state is independent from execution state. |
| G-6 | A small team can operate the MVP. | ≤ 10 deployable processes from one image + managed data stores; runbooks for the top 10 failure modes. |

## 2. Non-goals for the MVP

- Personal WeChat / ClawBot channel, WeCom (moves to the release after MVP unless the first scenario requires it).
- Multi-agent "squads", Code workspace with repository/terminal/Git (prototype CD-02, HB-03).
- Department-based permission inheritance, directory sync, SCIM, custom roles **[PO]**.
- Cross-workspace data migration or copy **[PO]**.
- Real-time co-editing of artifacts (versioned save with optimistic concurrency only).
- A public Skill/partner marketplace or third-party publishing (WorkX-curated catalog only).
- Model choice beyond Claude models (see conflict C-02).
- Billing/payments (usage metering is in scope; invoicing is not).
- Self-hosted / private deployment edition (architecture stays deployable, but no packaged offering).
- Arbitrary end-user-uploaded Skills or stdio MCP servers that need raw secrets.

## 3. Constraints

| ID | Constraint | Source |
| --- | --- | --- |
| K-1 | Workspace-based SaaS; one global user; personal workspace + many organization workspaces; separate ownership; no automatic migration on switch. | [PO] |
| K-2 | Personal settings and org administration are separate surfaces. | [PO] |
| K-3 | Management roles ≠ access to private resources; departments do not grant access initially. | [PO] |
| K-4 | Data, integrations, credentials have explicit owner and authorized usage scope. | [PO] |
| K-5 | Claude Agent SDK + E2B is the proposed execution direction; production readiness, limits, security, cost still require validation. | [PO] |
| K-6 | Real upstream secrets (including model API keys) never enter the agent E2B sandbox. | [DOC] ADR-0002, kept as [REC] |
| K-7 | Nango is not adopted unless a concrete gap justifies it. | [DOC] + request |
| K-8 | Claude Agent SDK use is governed by Anthropic's Commercial Terms; products must use API-key authentication, not claude.ai login, unless approved by Anthropic ([SDK overview](https://code.claude.com/docs/en/agent-sdk/overview) ✅). | Vendor terms |
| K-9 | Products built on the SDK must not be branded "Claude Code" ([SDK overview](https://code.claude.com/docs/en/agent-sdk/overview) ✅). | Vendor terms |
| K-10 | Small team; MVP must be operable without a dedicated platform team. | Request |
| K-11 | UI languages: English (default) and Simplified Chinese. | [PO] prototype requirement |

## 4. Assumptions (to confirm)

| ID | Assumption | If wrong |
| --- | --- | --- |
| A-1 | First production region is one where both the Claude API and E2B cloud are available (e.g., a US/EU/Singapore/Japan cloud region), serving customers who accept that location, including **Lark (international)** or Feishu tenants whose data may be processed outside mainland China. | See C-01; architecture needs a China-region plan. |
| A-2 | The first business scenario is document-centric (research/report/summary over uploaded files and knowledge) with Feishu as the first channel. | Connector and artifact priorities change. |
| A-3 | Team of 6–9 engineers (Part 14 §7). | Timeline ranges scale. |
| A-4 | Managed PostgreSQL, object storage, and a managed container platform are available in the chosen region. | More self-hosting and ops load. |
| A-5 | Email + password and OIDC social login are acceptable for MVP sign-in; enterprise SSO per organization comes later. | Earlier Keycloak brokering work. |
| A-6 | Per-attempt sandbox costs are small relative to model token cost (consistent with [SDK hosting](https://code.claude.com/docs/en/agent-sdk/hosting) ✅: "token cost typically dominates container infrastructure cost by an order of magnitude or more"). | Warm pools and pause/resume become cost levers. |

## 5. MVP boundary

**In the MVP (release "R1"):**

1. Real sign-up/sign-in, personal workspace auto-created, organization create, email invitation, roles owner/admin/member, deactivation and session revocation.
2. Resource sharing: private / selected members / project members / organization-wide, with explicit actions.
3. AI partners (agents) with versioned instructions, Skills from the WorkX-curated catalog, Knowledge sources.
4. Tasks with streamed progress (SSE), cancel, retry, and persisted artifacts (Markdown + DOCX/XLSX/PPTX generated in sandbox and validated on ingestion).
5. Execution: Claude Agent SDK in E2B through the WorkX Runner, Model Gateway, Tool Gateway, attempt tickets, egress allow-list.
6. Credentials: classes 0 (no-auth), A (API key/header via Gateway), B (user OAuth for one or two providers including Feishu user OAuth and one OAuth-protected HTTP MCP server). `needs_auth` pause and resume with a new Attempt.
7. Knowledge: upload → Tika parse (+OCR) → chunk → embeddings → PostgreSQL hybrid search with permission filter → citations.
8. Feishu application bot: receive messages, identity mapping, execute task, reply in the originating chat.
9. Audit log, usage metering per tenant, per-tenant quotas and cost caps.

**Next release (R2):** WeCom smart bot, Feishu CLI in Credential Worker (class C/D), Knowledge connectors (Feishu Docs sync), automations/scheduling, Meilisearch evaluation outcome, enterprise SSO.

**Later (R3+):** directory sync, department-based policies, BYO model keys, private deployment, squads, Code workspace, billing.

## 6. Conflicts and challenges to current direction

Each conflict keeps the current direction in the provisional design unless the product owner decides otherwise.

| ID | Conflict | Consequence | Options | Provisional position |
| --- | --- | --- | --- | --- |
| **C-01** | **Claude API is not offered in mainland China, Hong Kong, Macau** ([Anthropic supported countries](https://www.anthropic.com/supported-countries) ✅). E2B volumes are also "not available in APAC" in beta ([E2B volumes limitations](https://docs.e2b.dev/faq/volumes-beta-limitations.md) ◐), and I found no official E2B region list. The product's primary channels are Feishu and WeCom, which are China-centric. | A deployment serving mainland-China tenants with in-country processing cannot use the chosen runtime. Cross-border data transfer and model access have legal implications that need qualified review. | (a) Serve markets where Claude is available, including Lark-international tenants; keep runtime. (b) Add a second runtime for China regions behind the same Task/Attempt/Gateway contracts (different harness and sandbox, e.g., an E2B-API-compatible sandbox such as Alibaba Cloud FC Agent Sandbox — third-party documentation lists China regions ([Alibaba FC Agent Sandbox log](https://help.aliyun.com/en/functioncompute/feature-release-log-for-fc-agent-sandbox-2026) ⚠) — plus a domestic model). (c) Defer channels to Lark only. | Keep (a) for R1. Design the Runner protocol, Model Gateway, and Tool Gateway to be harness-neutral so (b) remains possible. **Product owner decision required** (Q-01). |
| **C-02** | Prototype TK-03 lets users choose Auto/Doubao/DeepSeek/Claude. The Claude Agent SDK runs Claude models (routing it to another vendor through `ANTHROPIC_BASE_URL` is not a supported configuration). | UI promises a capability the backend will not have. | (a) Remove model picker; expose Claude model tiers only. (b) Keep a picker for a non-agent "chat" mode using a different API. (c) Second runtime (see C-01b). | (a) for R1. |
| **C-03** | Docs choose **Redis Streams + outbox** for task dispatch. | Two delivery logs (PG outbox and Redis stream) to reconcile; Redis persistence and consumer-group recovery to operate; adds failure modes without a measured need. | (a) Keep Redis Streams. (b) PostgreSQL jobs table with `FOR UPDATE SKIP LOCKED` (the outbox *is* the queue); Valkey only for SSE fan-out, rate limits, caches. (c) Durable execution engine (Temporal/Hatchet/DBOS). | **[REC] (b)** for R1, with explicit extraction triggers (Part 10 §1–2). This changes a [DOC] proposal, not a [PO] decision. |
| **C-04** | Docs prioritize validating **Meilisearch auto-embedding as the primary search layer** while keeping pgvector as baseline. | Meilisearch adds a second store whose ACL filters lag PostgreSQL on revocation; documents already require "temporary query blocking" to compensate. | (a) Meilisearch primary. (b) PostgreSQL FTS (Chinese tokenizer extension) + pgvector in R1, Meilisearch evaluated in parallel on the same corpus. | **[REC] (b)**: ship PG baseline; adopt Meilisearch only if evaluation shows a material retrieval-quality or latency win (Part 7 §7). |
| **C-05** | Docs require the sandbox Runner to run as a non-root user without sudo, and rely on local file permissions for read-only knowledge/skills. I could not verify E2B's default user privileges from this session. | If the template user can escalate, local read-only is not enforceable. | Treat in-sandbox read-only as integrity, not security: the system of record is outside the sandbox; nothing flows back except validated outputs. | **[REC]** Reframe (Part 5 §4); keep non-root as hardening, validate in spike S-04. |
| **C-06** | Docs say `/mnt/skills/<rev>` needs "an Adapter to make SDK discover it". The SDK supports loading skills from a specific path via the `plugins` option and restricting with `skills` ([SDK skills](https://code.claude.com/docs/en/agent-sdk/skills) ✅). | No conflict in intent; resolves an open item. | Package curated Skills as SDK plugins; pass `setting_sources=[]`, `plugins=[<path>]`, explicit `skills=[...]`. | **[REC]** adopt; note skill files remain readable via Read/Bash even when not in the `skills` list. |
| **C-07** | Docs propose E2B volumes for `/mnt/persist`. Volumes are private beta, no read-only mounts, no snapshots, permission bits not enforced, mounts fixed at create, **not available in APAC** ([E2B volumes limitations](https://docs.e2b.dev/faq/volumes-beta-limitations.md) ◐). | Feature cannot be relied upon for R1, especially in Asian regions. | Checkpoints to object storage via the trusted Worker. | **[REC]** drop `/mnt/persist` from R1. |
| **C-08** | Docs keep both **OpenBao Transit** and generic "KMS" language; OpenBao is a self-operated, sealed service. | Seal/unseal, HA, backup, and upgrade runbooks fall on a small team. | (a) OpenBao Transit. (b) Cloud KMS envelope encryption (same `KeyProvider` interface). | **[REC]** `KeyProvider` interface; cloud KMS in the managed SaaS deployment, OpenBao Transit for self-hosted/private deployments. Data model unchanged. Requires PO/security sign-off (Q-07). |
| **C-09** | Department "no inheritance" [PO] vs. organizations that will expect department sharing. | None for R1. | Model `department` as a principal type reserved for later. | Keep [PO]; schema reserves `principal_type='department'` but policy engine rejects it in R1. |
| **C-10** | Resource ownership when a member leaves an organization is not decided. | Orphaned private resources or silent disclosure. | (a) Keep resources, owner becomes "former member", only org owner can reassign. (b) Mandatory reassignment at removal. (c) Archive. | **[REC]** (a) with explicit admin reassignment action and audit; credentials never transfer. PO confirmation (Q-05). |

## 7. Major architecture decisions

| ID | Decision | Alternatives considered | Trade-off |
| --- | --- | --- | --- |
| AD-01 | Modular monolith (one Python codebase) deployed as multiple processes: `api`, `worker`, `orchestrator`, `tool-gateway`, `model-gateway`, `broker`, `credential-worker`, `channel-worker`, `knowledge-worker`; plus `parser` (Tika, Java). | Microservices from day one; single process. | Fast iteration with strict module boundaries; trusted components still get separate identities and secrets. |
| AD-02 | PostgreSQL is the system of record for every business fact and the job queue (outbox → jobs). | Redis Streams; Kafka; Temporal. | Fewer moving parts; transactional enqueue; throughput ceiling acknowledged with triggers. |
| AD-03 | Tenant isolation = request-scoped tenant context + composite `(tenant_id, id)` keys + PostgreSQL RLS + per-tenant object key prefixes + tenant-scoped tickets. | Schema-per-tenant; database-per-tenant. | Shared schema scales to many small personal tenants; RLS is defense in depth, not the only control. |
| AD-04 | Authorization = in-process policy evaluator over `memberships`, `roles`, `resource_grants`, called from API, workers, gateways, and retrieval. | OpenFGA/SpiceDB; Cerbos; OPA. | Simple model fits R1; extraction to OpenFGA when relationship depth grows (trigger in Part 10). |
| AD-05 | Identity via Keycloak (OIDC) with WorkX-owned tenancy; API is a confidential OIDC client and issues an HttpOnly session cookie. | Managed IdP (Auth0/Clerk); Ory; Zitadel (now AGPL). | Open source, SAML/OIDC brokering for later org SSO; operational weight accepted. |
| AD-06 | Agent execution: one E2B sandbox per active WorkX Session; WorkX Runner (Python) drives `ClaudeSDKClient`; NDJSON over process stdout; control via files/stdin. | Managed Agents; self-written loop; self-hosted Firecracker/gVisor. | Kept per [PO]; alternatives documented in Part 4 §12. |
| AD-07 | All model and tool egress from the sandbox goes to WorkX gateways (E2B egress allow-list); credentials injected outside. | E2B native secret injection; TLS-terminating proxy. | Gateways give per-call authorization, audit, idempotency. E2B header injection is an optional later adapter. |
| AD-08 | Credential storage: AEAD ciphertext in PostgreSQL (`secret_versions`), DEKs wrapped by `KeyProvider` (cloud KMS or OpenBao Transit). Only the Broker can unwrap. | Vault/OpenBao KV; Nango. | One store, versioned, auditable; Broker is a high-value target and is hardened accordingly. |
| AD-09 | `needs_auth` ends the current Attempt, releases the sandbox lease, and a new Attempt starts after authorization; an operation ledger prevents duplicate side effects. | Hold sandbox paused while waiting. | No idle sandbox cost; resumption is explicit and safe. |
| AD-10 | Knowledge R1: Tika 4 parser service + WorkX chunker + embeddings via Embedding Gateway + PostgreSQL FTS/pgvector hybrid with SQL-level ACL filter. | Meilisearch primary; OpenSearch; dedicated vector DB. | One consistent store; revocation is immediate; Meilisearch remains a measured candidate. |
| AD-11 | Frontend: React + TypeScript + Vite SPA, TanStack Router/Query, generated OpenAPI client, SSE with server cookie auth, react-i18next; **prototype UI reproduced exactly** (stylesheets, DOM, class names, icons, copy keys) and verified by visual comparison (Part 15). | Next.js; keep vanilla JS; new component library. | Matches [DOC] and [PO]; SPA keeps backend authority in FastAPI. |
| AD-12 | Monorepo with `uv` (Python) and `pnpm` (TypeScript) workspaces; contracts generated from FastAPI OpenAPI and JSON Schema. | Multi-repo. | Atomic changes across API/contracts/web; import-linter enforces module direction. |

## 8. Decision log

Status values: **Approved** (product owner decided), **Provisional** (adopted for design; can change without PO), **Validation-required** (blocked on spike), **Rejected**.

| # | Decision | Status | Owner | Evidence / next step |
| --- | --- | --- | --- | --- |
| 1 | Workspace SaaS: personal + organization tenants, one global user | Approved | PO | Request §3; `TENANCY-MODEL.md` |
| 2 | Personal and org are separate ownership boundaries; no automatic migration | Approved | PO | Request §3 |
| 3 | Personal settings separate from org administration | Approved | PO | Request §3; prototype SA-05 |
| 4 | Roles owner/admin/member; management ≠ private-resource access | Approved | PO | Request §3 |
| 5 | Departments are attributes only in R1 | Approved | PO | Request §3 |
| 6 | Claude Agent SDK + E2B as execution direction | Approved direction, **Validation-required** for production | PO | Spikes S-00…S-05 |
| 7 | No raw upstream secrets in agent sandbox (incl. model key) | Provisional (strongly recommended) | Arch | ADR-0002 |
| 8 | Nango not adopted | Provisional | Arch | Part 6 §10 comparison; revisit trigger defined |
| 9 | Modular monolith + trusted gateway processes | Provisional | Arch | AD-01 |
| 10 | PostgreSQL job queue instead of Redis Streams | Provisional (changes [DOC]) | Arch | C-03 |
| 11 | PostgreSQL hybrid search in R1; Meilisearch measured | Provisional (changes [DOC] priority) | Arch | C-04, spike S-09 |
| 12 | `KeyProvider` with cloud KMS (SaaS) / OpenBao (self-hosted) | Validation-required | Security | C-08, Q-07 |
| 13 | Drop E2B volumes (`/mnt/persist`) from R1 | Provisional | Arch | C-07 |
| 14 | Keycloak for identity | Provisional | Arch | AD-05; spike S-06 |
| 15 | Model picker limited to Claude tiers | **Approved (2026-10-31)** | PO | C-02, Q-02; Part 15 D-01 |
| 16 | Target region / China strategy | **Open — PO decision** | PO | C-01, Q-01 |
| 17 | Member-departure resource ownership rule | Open — PO decision | PO | C-10, Q-05 |
| 18 | Run Agent SDK in FastAPI process | Rejected | — | Shared process for untrusted execution |
| 19 | Write real secrets to `.env` inside agent sandbox | Rejected | — | ADR-0002 |
| 20 | Copy users' local Feishu CLI login cache into sandbox | Rejected | — | Part 6 §8 |
| 21 | Use E2B volumes for read-only knowledge | Rejected | — | Vendor limitations (C-07) |
| 22 | Use `allowed_tools` as a security allow-list | Rejected | — | `allowed_tools` auto-approves; unlisted tools remain available ([SDK permissions](https://code.claude.com/docs/en/agent-sdk/permissions) ✅) |
| 23 | Use MinIO Community Edition for self-hosted object storage | Rejected for new deployments | Arch | Reported in maintenance/unmaintained state ([vonng blog](https://blog.vonng.com/en/db/minio-is-dead/) ⚠); verify on GitHub |
| 24 | Durable workflow engine (Temporal) in R1 | Rejected for R1; growth path | Arch | Part 10 §1–2 triggers |
| 25 | The prototype UI (`workmates-prototype/dist/`) is the approved design baseline; migrate without redesign | Approved | PO | Part 15 |
| 26 | UI fidelity scope is the desktop web browser (1440×900, 1280×800); narrow/mobile layouts not in acceptance | Approved (2026-10-31) | PO | Part 15 §1.3 |
| 27 | Port prototype stylesheets, DOM structure, class names, icons and i18n keys verbatim; no new component library | Provisional | Arch/Frontend | Part 15 §4.2 |
| 28 | Adopt a third-party component library (e.g., Radix-based styling) for the production UI | Rejected | — | Would change DOM and styling of the approved baseline |
| 29 | Darken `--muted` secondary text from `#8f959e` (3.02:1) to `#6b7079` (4.98:1) | **Approved (2026-10-31)** | PO | Part 15 D-04, Q-16 |
| 30 | Knowledge UI lives inside Workmate detail "Work Context" plus a Library "Knowledge" filter; no new sidebar item | **Approved (2026-10-31)** | PO | Part 15 §4.3, Q-15 |
| 31 | Replace simulation-only wording with production wording at the same position and similar length | **Approved (2026-10-31)** | PO | Part 15 D-02, Q-17 |
| 32 | Begin production React implementation (`apps/web`) | **Approved (2026-10-31)** | PO | Part 15, Part 9 |
