# WorkX Production Architecture Package — v1.0 (review draft)

Date: 2026-10-30 · Status: **proposal for product/engineering review** · Repository baseline: `abystra/WorkX@main` commit `f262dc5`

This package turns the existing WorkX prototype and Chinese-language design documents into one implementation-oriented architecture. It does not replace the repository documents yet. Nothing in it has been implemented, and no repository file was changed.

## How to read this package

| Part | File | Covers request section |
| --- | --- | --- |
| 0 | `00-INDEX.md` (this file) | Evidence base, status legend, source inventory |
| 1 | `01-EXECUTIVE-DECISIONS.md` | A. Goals, non-goals, MVP boundary, decision log, conflicts |
| 2 | `02-ARCHITECTURE-DIAGRAMS.md` | B. Twelve architecture diagrams |
| 3 | `03-TENANCY-IDENTITY-AUTHZ.md` | 5.1 SaaS identity, tenancy, permissions matrix, policies |
| 4 | `04-AGENT-RUNTIME.md` | 5.2 Claude Agent SDK + E2B runtime |
| 5 | `05-SANDBOX-FILESYSTEM.md` | 5.3 Sandbox filesystem and mounting |
| 6 | `06-CREDENTIALS-CONNECTORS.md` | 5.4 Credentials, OAuth, MCP, Skills, CLI, connectors (8 sequences) |
| 7 | `07-KNOWLEDGE.md` | 5.5 Knowledge ingestion, indexing, retrieval |
| 8 | `08-USER-JOURNEYS.md` | C. Eleven user-journey sequence diagrams |
| 9 | `09-FRONTEND.md` | D. Frontend architecture and prototype migration |
| 10 | `10-BACKEND-PLATFORM.md` | E. Backend, middleware, deployment, technology selection and licenses |
| 11 | `11-DATA-API-EVENTS.md` | F. Domain model, tables, APIs, events, state machines |
| 12 | `12-REPOSITORY.md` | G. Monorepo layout and dependency rules |
| 13 | `13-SECURITY-OPERATIONS.md` | H. Security, compliance, reliability, operations |
| 14 | `14-VALIDATION-DELIVERY.md` | I. Spikes, vertical slice, roadmap, backlog, test matrix, team, open questions |
| — | `99-SOURCES.md` | All external sources with verification status |

Suggested reading order for a decision meeting: Part 1 → Part 14 §8 (open questions) → Part 2. Engineers estimating work should read Parts 3–7 and 11–12.

## Evidence base: what was actually inspected

The task referenced a macOS path (`/Users/yuhuangyan/.../WorkX`). That path is not reachable from this environment. I inspected the same repository cloned from `github.com/abystra/WorkX` (branch `main`, 5 commits, latest `f262dc5`, 2026-10-30). Every file in the repository was read.

| Material | Status | Notes |
| --- | --- | --- |
| `README.md`, `docs/README.md` (v0.7) | Read in full | Entry point and normative reading order |
| `docs/ARCHITECTURE.md` (v0.6) | Read | Logical architecture, module table |
| `docs/TENANCY-MODEL.md` (v0.2) | Read | Personal/organization tenant model |
| `docs/CREDENTIAL-SOLUTION.md` (v0.2) | Read | Normative credential entry point (0/A/B/C/D classes) |
| `docs/CREDENTIALS-AND-CONNECTORS.md` (v0.4) | Read | Credential entities |
| `docs/SKILL-RUNTIME-CONTRACT.md` (v0.2) | Read | Skill/MCP env and `.env` assembly |
| `docs/API-AND-EVENTS.md` (v0.5) | Read | REST, Runner protocol, SSE, task state machine |
| `docs/CLAUDE-E2B-RUNTIME.md` (v0.5) | Read | Runtime design |
| `docs/SANDBOX-FILESYSTEM.md` (v0.2) | Read | `/mnt` conventions |
| `docs/DATA-AND-TENANCY.md` (v0.5) | Read | Tables and constraints |
| `docs/KNOWLEDGE-PIPELINE.md` (v0.3) | Read | Tika and Meilisearch evaluation |
| `docs/IMPLEMENTATION-PLAN.md` (v0.6) | Read | Phases 0–5 |
| `docs/ARCHITECTURE-REVIEW.md` | Read | Conflict log from the previous review |
| `docs/NANGO-ADOPTION.md` | Read | Historical; Nango not adopted |
| `docs/adr/0001`, `docs/adr/0002` | Read | Runtime and credential ADRs |
| `workmates-prototype/README.md`, `docs/PRODUCT-FEATURES.md` (v0.9), `SAAS-FOUNDATION.md` (v0.3), `BUSINESS-SCENARIOS.md`, `ECOSYSTEM-INTEGRATION-RESEARCH.md` | Read | Product evidence |
| `workmates-prototype/dist/*.js` | Inspected | Key models read (`spaces-model.js`, `channel-model.js`, `connection-model.js`); routes extracted from `app.js` |
| Prototype tests | Executed | `npm run check` passed; `npm test`: **73/73 passed** on Node 22.22.0 |

### Which documents are current

All repository documents are dated 2026-10-30. Within the repo, `docs/README.md` declares the owner of each rule, and `ARCHITECTURE-REVIEW.md` records which earlier statements were superseded. I treat them as follows:

| Document | Classification |
| --- | --- |
| `CREDENTIAL-SOLUTION.md`, `TENANCY-MODEL.md`, `API-AND-EVENTS.md` | **Current, normative** for their domains (declared in `docs/README.md`) |
| `ARCHITECTURE.md`, `CLAUDE-E2B-RUNTIME.md`, `SANDBOX-FILESYSTEM.md`, `SKILL-RUNTIME-CONTRACT.md`, `DATA-AND-TENANCY.md`, `KNOWLEDGE-PIPELINE.md`, `IMPLEMENTATION-PLAN.md`, ADR-0001/0002 | **Current, proposed design** (not validated by any implementation) |
| `NANGO-ADOPTION.md` | **Historical**; kept for link continuity, explicitly not a plan |
| `ARCHITECTURE-REVIEW.md` | **Current review log**; useful for resolved conflicts |
| Prototype `PRODUCT-FEATURES.md` v0.9, `SAAS-FOUNDATION.md` v0.3 | **Current product evidence** for UI scope and acceptance; not a backend specification |
| `ECOSYSTEM-INTEGRATION-RESEARCH.md` | **Research evidence** dated 2026-10-29 |
| `BUSINESS-SCENARIOS.md` | **Template only**; no scenario has been defined |

Remaining conflicts I found are listed in Part 1 §6.

### Status legend used throughout

| Label | Meaning |
| --- | --- |
| **[PROTO]** | Exists in the local prototype as simulated or browser-only behavior (localStorage, timers). Not a backend capability. |
| **[DOC]** | Described in the repository's design documents. Not implemented. |
| **[PO]** | Decision made by the product owner (from the request or explicitly recorded as a user decision in the repo). |
| **[REC]** | New recommendation in this package. |
| **[ASSUME]** | Assumption I made to proceed; must be confirmed. |
| **[VALIDATE]** | Needs a spike or proof of concept before commitment. |
| **[PROD]** | Implemented and verified in a production backend. **No WorkX feature currently has this status.** |

### Source verification legend (Part 99 lists every source)

| Mark | Meaning |
| --- | --- |
| ✅ | Read directly from the official page during this session |
| ◐ | Confirmed from the official page's indexed content through web search; the page itself was blocked from this session (`docs.e2b.dev`, `e2b.dev`, `modelcontextprotocol.io`, `www.meilisearch.com`) |
| ⚠ | Secondary source only; treat as unverified |
| ○ | Not verified in this session (general knowledge); re-verify before locking versions |

Network note: this cloud session could not reach `docs.e2b.dev`, `e2b.dev`, `modelcontextprotocol.io`, or `www.meilisearch.com`. To re-verify those claims from this environment, those hosts must be allowed in the session's network settings.

## The five most important findings

1. **Model-region availability is an unexamined blocker.** Anthropic's supported-countries list excludes mainland China, Hong Kong, and Macau ([Anthropic supported countries](https://www.anthropic.com/supported-countries) ✅). The product's primary channels are Feishu and WeCom. If target customers or data must stay in mainland China, the Claude Agent SDK + E2B direction cannot be deployed there as designed. This needs a product decision before any build (Part 1 §6 C-01, Part 14 spike S-00).
2. **The prototype offers models the runtime cannot use.** Prototype task creation (TK-03) offers Auto/Doubao/DeepSeek/Claude. The Claude Agent SDK runs Claude models. Either the model picker is removed or a second runtime is in scope (C-02).
3. **The repository's credential and tenancy rules are sound and are largely kept.** The main additions here are concrete enforcement points: composite tenant keys + PostgreSQL RLS, opaque attempt tickets, a single refresh owner, an operation ledger for side effects, and a policy evaluator shared by API, workers, gateways, and retrieval.
4. **"Read-only knowledge in the sandbox" is an integrity measure, not a security boundary.** The real guarantee is that nothing written inside a sandbox ever flows back except through validated output ingestion. This reframing removes a dependency on unverified E2B user/permission behavior (Part 5).
5. **The MVP can be smaller than the documents imply.** One Python codebase deployed as a modular monolith (API + workers + trusted gateway processes), PostgreSQL as system of record *and* job queue, PostgreSQL full-text + pgvector for the first knowledge release, and no Meilisearch, Temporal, OpenFGA or Nango until measured triggers fire (Part 10 §1–2).
