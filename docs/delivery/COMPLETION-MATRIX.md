# Completion matrix

Every agreed capability, with three independent statuses. Updated at each phase checkpoint.

- **Impl**: code exists in the repository for the real system (not the frontend development adapter).
- **Tests**: automated tests pass in this environment against real local infrastructure (PostgreSQL, Redis) and protocol-level fakes for external services.
- **Real**: verified against the real external service. `n/a` when no external service is involved.

Legend: ✅ done · 🟡 partial (see note) · ⬜ not started · ⛔ blocked (reason in note)

| ID | Capability | Phase | Impl | Tests | Real | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| B-01 | Monorepo, CI, contracts pipeline | P-01 | ⬜ | ⬜ | n/a | |
| B-02 | Identity: OIDC login, sessions, revocation | P-02 | ⬜ | ⬜ | ⬜ | Real: Keycloak |
| B-03 | Tenancy: personal provisioning, orgs, memberships, roles | P-02 | ⬜ | ⬜ | n/a | |
| B-04 | Invitations with email outbox | P-02 | ⬜ | ⬜ | ⬜ | Real: SMTP |
| B-05 | Authz, grants, RLS, isolation suite | P-03 | ⬜ | ⬜ | n/a | |
| B-06 | Web shell/admin on real API | P-04 | 🟡 | 🟡 | n/a | UI done on the development adapter (commits be18467…2b2d603); real API pending |
| B-07 | Jobs/outbox, reconciler, audit, usage events | P-03 | ⬜ | ⬜ | n/a | |
| B-08 | Agents: drafts, versions, publish, sharing, skills | P-04 | ⬜ | ⬜ | n/a | |
| B-09 | Runtime release, E2B template, Runner v1 | P-05 | ⬜ | ⬜ | ⬜ | Real: E2B key |
| B-10 | Model Gateway, budgets, usage | P-05 | ⬜ | ⬜ | ⬜ | Real: Anthropic key |
| B-11 | Broker tickets, Tool Gateway (class 0/A), ledger | P-05 | ⬜ | ⬜ | n/a | |
| B-12 | Orchestrator, leases, fencing, events, SSE | P-05 | ⬜ | ⬜ | ⬜ | Real: with E2B + Anthropic |
| B-13 | Artifact ingestion, validation, Library | P-06 | ⬜ | ⬜ | n/a | |
| B-14 | Cancel/retry/recovery, approvals | P-05 | ⬜ | ⬜ | ⬜ | |
| B-15 | KeyProvider, secret versions, API-key connections | P-07 | ⬜ | ⬜ | ⬜ | Real: KMS/OpenBao |
| B-16 | OAuth (Feishu user, MCP), needs_auth resume | P-07 | ⬜ | ⬜ | ⬜ | Real: Feishu app, MCP server |
| B-17 | Org-shared connections, usage policies | P-07 | ⬜ | ⬜ | n/a | |
| B-18 | Member removal / revocation effects on tasks | P-07 | ⬜ | ⬜ | n/a | |
| B-19 | Knowledge ingest, parse, chunk, embed, index | P-08 | 🟡 | 🟡 | ⬜ | UI on the development adapter only; Real: Tika, embedding provider |
| B-20 | Retrieval tool, citations, ACL | P-08 | ⬜ | ⬜ | n/a | |
| B-21 | Feishu bot channel, delivery, inbox | P-09 | 🟡 | 🟡 | ⬜ | UI on the development adapter only; Real: Feishu app |
| B-22 | Security hardening, runbooks, DR drill | P-12 | ⬜ | ⬜ | ⬜ | Pen test needs an external party |
| B-UI-01 | Prototype styles, icons, i18n, React shell | done | ✅ | ✅ | n/a | Fidelity 272/274 pass, 2 proposed deviations |
| B-UI-02 | Fidelity test seed + web target | P-04 | 🟡 | ✅ | n/a | Adapter seed done; backend seed endpoint pending |
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
