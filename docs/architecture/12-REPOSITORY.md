# Part 12 — Repository architecture (request G)

## 1. Monorepo

**Recommendation: one monorepo** (`abystra/WorkX`), extending the layout sketched in `ARCHITECTURE.md`. Reasons: atomic changes across API contracts, web client, and runner protocol; one CI; small team. Python workspace via `uv`, TypeScript via `pnpm`; Java (Tika config) and Go (CLI wrapper) built as containers only.

Split trigger: if security review requires a separately audited codebase for the trusted credential zone, move `services/workx/src/workx/trusted` into its own repository with a published internal SDK.

## 2. Directory tree

```text
WorkX/
├── README.md
├── CODEOWNERS
├── pyproject.toml                    # uv workspace root (ruff, mypy/pyright, import-linter config)
├── uv.lock
├── package.json / pnpm-workspace.yaml / pnpm-lock.yaml
├── .github/workflows/                # ci.yml, security.yml, e2b-template.yml, deploy-*.yml
│
├── apps/
│   └── web/                          # React + TS SPA
│       ├── src/app/                  # shell, router, providers (session, tenant, i18n, query)
│       ├── src/features/             # home, tasks, agents, projects, library, knowledge,
│       │                             # connections, inbox, admin/*, settings/*
│       ├── src/platform/             # sse-manager, api hooks, error boundary, feature flags
│       ├── src/locales/{en,zh-CN}/   # migrated from prototype messages-*.js
│       └── tests/{unit,component,e2e}/
│
├── packages/
│   ├── contracts/                    # SOURCE OF TRUTH for wire contracts
│   │   ├── openapi/workx.v1.yaml     # generated from FastAPI, committed, diff-checked
│   │   ├── events/*.schema.json      # internal + SSE event schemas
│   │   ├── runner-protocol/*.schema.json
│   │   └── connector-manifest/*.schema.json   # workx-skill.yaml, connector definitions
│   ├── api-client/                   # generated TS types + thin fetch client
│   ├── ui/                           # design tokens, primitives, icons (from prototype assets)
│   └── runner-protocol-py/           # generated/handwritten Python models shared by runner & orchestrator
│
├── services/
│   ├── workx/                        # Python modular monolith
│   │   ├── src/workx/
│   │   │   ├── core/                 # ids, errors, clock, tenancy context, db session, redaction, telemetry
│   │   │   ├── platform/             # jobs, outbox, scheduler, feature flags, config
│   │   │   ├── domains/
│   │   │   │   ├── identity/         # users, login sessions, OIDC client
│   │   │   │   ├── tenancy/          # tenants, memberships, invitations, departments
│   │   │   │   ├── authz/            # policy evaluator, grants, RLS helpers
│   │   │   │   ├── resources/        # projects, files, sharing
│   │   │   │   ├── agents/           # agents, versions, skills catalog, installations, bindings
│   │   │   │   ├── tasks/            # sessions, tasks, attempts, approvals, ledger, state machines
│   │   │   │   ├── runtime/          # orchestrator logic, SandboxProvider (e2b, local_docker), runner adapter
│   │   │   │   ├── artifacts/        # ingestion, validation, versions
│   │   │   │   ├── knowledge/        # sources, revisions, chunker, retrieval, parser client
│   │   │   │   ├── connections/      # connector registry, connections metadata, authorization requests
│   │   │   │   ├── channels/         # feishu/, wecom/ adapters: ingress verify, identity map, delivery
│   │   │   │   ├── usage/            # metering, quotas, budgets
│   │   │   │   └── audit/
│   │   │   ├── trusted/              # ONLY imported by trusted entrypoints
│   │   │   │   ├── credentials/      # secret versions, KeyProvider (kms, openbao), envelope crypto
│   │   │   │   ├── broker/           # tickets, resolution, refresh single-flight, oauth client (pre-reg/CIMD/DCR)
│   │   │   │   ├── tool_gateway/     # MCP server facade, upstream MCP/HTTP clients, SSRF guard, ledger hooks
│   │   │   │   ├── model_gateway/    # Anthropic proxy, budgets, usage, embedding gateway
│   │   │   │   ├── credential_worker/# supervisor, isolated unit drivers (gvisor/firecracker), lark-cli integration
│   │   │   │   └── adapters/         # provider adapters: feishu, wecom, generic_oauth, mcp_oauth, static_key
│   │   │   └── entrypoints/          # api.py, orchestrator.py, worker.py, knowledge_worker.py,
│   │   │                             # channel_worker.py, broker.py, tool_gateway.py, model_gateway.py,
│   │   │                             # credential_worker.py, cli.py (admin/migrations)
│   │   ├── migrations/               # Alembic versions + sql/rls/*.sql + sql/functions/*.sql
│   │   └── tests/
│   │       ├── unit/
│   │       ├── integration/          # PG, Valkey, object storage, Keycloak via testcontainers/compose
│   │       ├── contract/             # OpenAPI/event schema compatibility, provider adapter contract tests
│   │       ├── isolation/            # T-ISO-* tenant isolation suite
│   │       ├── security/             # ticket replay, SSRF, path traversal, canary secrets, authz fuzzing
│   │       └── performance/          # k6/locust scenarios, retrieval latency
│   ├── parser/                       # Tika 4 server image + config (no network), OCR language packs
│   └── lark-cli-wrapper/             # Go build of lark-cli + WorkX credential provider (R2)
│
├── runtime/
│   ├── runner/                       # Python package installed in the E2B template (NO import of services/workx)
│   │   ├── src/workx_runner/         # protocol io, sdk adapter, hooks, control loop, drain, checkpoint
│   │   └── tests/                    # fixtures of SDK message streams
│   ├── e2b-template/                 # template definition, Dockerfile, users/permissions, fonts, libs, smoke tests
│   └── skills/                       # curated Skills as SDK plugins + workx-skill.yaml manifests, review records
│
├── evals/
│   ├── agents/                       # golden tasks per agent template, rubrics
│   ├── knowledge/                    # corpus manifests (not raw private data), labeled queries, metrics scripts
│   └── red-team/                     # prompt-injection and exfiltration scenarios
│
├── infra/
│   ├── tofu/                         # OpenTofu modules + envs/{staging,prod-<cell>}
│   ├── k8s/ or containers/           # manifests/helm or service definitions
│   ├── compose/                      # local dev stack (pg+pgvector+pg_jieba, valkey, seaweedfs, keycloak, tika, otel)
│   └── policies/                     # network policies, egress allow-lists, OPA/conftest checks
│
├── tools/                            # codegen scripts, data seeders, local CLI
├── docs/
│   ├── README.md, ARCHITECTURE.md …  # existing docs, to be reconciled with this package
│   ├── adr/                          # 0001…, new ADRs from Part 1 decision log
│   ├── runbooks/                     # incidents, DLQ, key rotation, restore, tenant deletion, break-glass
│   └── api/                          # rendered OpenAPI docs
└── workmates-prototype/              # kept read-only as acceptance reference until F6
```

## 3. Dependency direction and enforcement

| Rule | Enforcement |
| --- | --- |
| `domains/*` may import `core`, `platform`, other domains only along the allowed graph (Part 2 B4) | import-linter `layers` + `forbidden` contracts in CI |
| `trusted/*` may import `domains/*` and `core`; **no domain imports `trusted`** | import-linter `forbidden` |
| Only trusted entrypoints import `trusted/*` | import-linter + entrypoint allow-list |
| `runtime/runner` imports only `packages/runner-protocol-py` and the SDK | separate package; CI check that it has no dependency on `workx` |
| `apps/web` uses only `packages/api-client` for HTTP | eslint `no-restricted-imports` |
| Contracts change only via generator; breaking changes require a new version | OpenAPI diff (oasdiff ○) + JSON Schema compatibility check |

## 4. Shared types and contracts

- **REST**: FastAPI models are the authoring source → `openapi/workx.v1.yaml` committed → TS types generated. CI fails if the committed spec is stale.
- **Events and runner protocol**: JSON Schema authored in `packages/contracts`; Python models generated (datamodel-code-generator ○) for orchestrator and runner; TS types for SSE.
- **Connector/Skill manifests**: JSON Schema validated in CI for every curated Skill and connector definition.

## 5. Environment configuration

- Twelve-factor env vars, typed with `pydantic-settings`; one `Settings` per entrypoint exposing only what that process needs (e.g., `api` settings have no KMS key ref; `broker` settings have no E2B key).
- Non-secret config in repo (`infra/envs/*/config.yaml`); secrets from the platform secret manager; local dev uses `.env.local` with fake values and a local KeyProvider (AES key file) — never real provider credentials in local defaults.
- Feature flags in DB (per tenant), cached.

## 6. Migration from prototype to repository layout

1. Add root workspace files and empty packages; keep `workmates-prototype/` untouched.
2. Move prototype i18n dictionaries into `apps/web/src/locales` via a conversion script (keeps keys).
3. Port prototype test scenarios into `apps/web/tests/e2e` specs (initially `test.fixme`) to track parity.
4. Reconcile `docs/` with this package: superseded statements edited in place (per repo rule "conflicts must modify the original paragraph"), new ADRs added for decisions 10–14 in Part 1 §8.
