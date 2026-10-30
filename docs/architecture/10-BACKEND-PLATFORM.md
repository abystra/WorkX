# Part 10 — Backend, middleware, and deployment (request E)

Verification marks follow Part 0 (✅ ◐ ⚠ ○). Every ○ item must be re-verified (license file + version) when versions are locked in spike S-01.

## 1. Selection summary

| Area | R1 choice | License / commercial status | Alternative(s) | Growth path / replacement trigger |
| --- | --- | --- | --- | --- |
| Backend language/framework | Python 3.12+, FastAPI, Pydantic v2, Uvicorn | MIT/BSD ○ (OSI) | Go; TypeScript (NestJS) | Keep. Extract hot paths (gateways) to Go only if p99 gateway overhead > 50 ms at target RPS after profiling |
| DB access | SQLAlchemy 2.0 (Core + ORM), psycopg 3, Alembic | MIT/LGPL-3.0 (psycopg) ○ | SQLModel; raw asyncpg | Keep |
| Database | PostgreSQL 16/17 managed (HA) + pgvector + pg_jieba (if provider supports; else self-managed PG or zhparser) | PostgreSQL License ○; pg_jieba BSD-3 ◐ | MySQL (no); CockroachDB | Read replicas → partitioning (`task_events`, `knowledge_chunks`, `audit_events` by month/tenant hash) → cells |
| Migrations | Alembic + SQL-first RLS policy files; expand/contract discipline | MIT ○ | Atlas, Flyway | Keep |
| Job queue | PostgreSQL `jobs` table (`SKIP LOCKED`) + transactional outbox (own code, ~500 LOC) | Own | Procrastinate (MIT ○), Hatchet (MIT ✅ [repo](https://github.com/hatchet-dev/hatchet)), DBOS (MIT ◐ [PyPI](https://pypi.org/pypi/dbos)), Redis Streams, Temporal (MIT ○) | Temporal/Hatchet when ≥ 3 multi-step workflows need durable timers/signals beyond the Task/Attempt machine, or sustained > 500 jobs/s, or queue lag p95 > 5 s |
| Cache / pub-sub / rate limits | Valkey (managed Redis-compatible) | BSD-3-Clause ○ (fork created after Redis relicensing; Redis 8 is RSALv2/SSPLv1/AGPLv3 tri-license — [Redis licenses](https://redis.io/legal/licenses/) ◐) | Redis 8 (AGPL option acceptable for unmodified internal use; legal review), NATS | Cluster mode when > 50k concurrent SSE subscribers or > 20k ops/s |
| Workflow engine | None in R1 (explicit state machines in PG) | — | Temporal, Hatchet, DBOS | See job-queue trigger |
| Object storage | Managed S3-compatible (AWS S3 / Alibaba OSS / Tencent COS per region); local dev: SeaweedFS | Apache-2.0 ○ (SeaweedFS) | Garage (AGPL ○), Ceph RGW (LGPL ○); **MinIO CE not recommended** (reported unmaintained/archived — [vonng](https://blog.vonng.com/en/db/minio-is-dead/) ⚠, verify on GitHub) | Bucket per cell; replication for DR |
| File serving | Presigned GET (≤ 5 min) via CDN for large files; API-proxied for small previews; `Content-Disposition: attachment` for untrusted types | — | Proxy everything | Keep |
| Identity / SSO | Keycloak (single realm for WorkX users; IdP brokering for org SSO in R2) | Apache-2.0 ○ | Ory Kratos+Hydra (Apache-2.0 ○), Zitadel (**AGPL-3.0 from v3** ◐ [Zitadel](https://zitadel.com/blog/apache-to-agpl)), Authentik, Logto, managed Auth0/Clerk | Replace if Keycloak ops cost > 0.25 FTE sustained; managed IdP if residency allows |
| Resource authorization | In-process policy module + PG grants + RLS | Own | OpenFGA (Apache-2.0, CNCF ⚠), SpiceDB (Apache-2.0 ⚠), Cerbos (Apache-2.0 ⚠) | OpenFGA when nested folders/teams/department inheritance (C-09) or > 5 relationship types make SQL predicates unmanageable, or authz query p95 > 20 ms |
| Agent harness | Claude Agent SDK (Python) | **Proprietary**: governed by Anthropic Commercial Terms ([SDK overview](https://code.claude.com/docs/en/agent-sdk/overview) ✅) | Managed Agents; own loop | Part 4 §15 |
| Model API | Anthropic Claude API via Model Gateway | Commercial API; **not available in mainland China/HK/Macau** ([supported countries](https://www.anthropic.com/supported-countries) ✅) | Claude via cloud marketplaces in supported regions ○ | C-01 |
| Sandbox | E2B cloud | E2B infra Apache-2.0 ✅ [infra](https://github.com/e2b-dev/infra); cloud service under E2B terms ○ | E2B self-hosted "Embed"/BYOC; Firecracker/gVisor fleet; Alibaba FC Agent Sandbox (E2B-SDK-compatible ⚠) | Self-host when residency or cost requires (Part 4 §15C) |
| Key management | `KeyProvider`: cloud KMS (SaaS); OpenBao Transit (self-hosted) | Cloud KMS proprietary; OpenBao MPL-2.0 ○ (2.6.x stable, 2.7 beta ◐ [release notes](https://openbao.org/community/release-notes/2-7-0/)) | HashiCorp Vault (BUSL ○) | Decision Q-07 |
| Credential Broker / Gateways | Own code (FastAPI + httpx; MCP Python SDK for MCP client/server) | Own; MCP SDK MIT ○ | Envoy `credential_injector` for class A (Apache-2.0 ○) | Envoy front for gateways if sustained > 2k RPS |
| Optional connection platform | None (Nango not adopted) | Nango: Elastic License ✅ | Part 6 §10 | Trigger in Part 6 §10 |
| Parser | Apache Tika 4.0 server + Tesseract | Apache-2.0 ○ (Tika 4.0.0 released ◐ [Tika](https://tika.apache.org/4.0.0/)); Tesseract Apache-2.0 ○ | Docling (MIT ○) for layout-heavy PDFs; Unstructured (Apache-2.0 ○) | Add Docling path if table/layout eval fails thresholds |
| Search/retrieval | PG FTS + pgvector | as above | Meilisearch CE (MIT) / EE (BUSL) ◐; OpenSearch (Apache-2.0 ○); ParadeDB pg_search (AGPL-3.0 or commercial ◐ [PGXN](https://pgxn.org/dist/pg_search)) | Part 7 §7 criteria |
| Embeddings | One hosted provider in region via Embedding Gateway | Commercial API ○ | BGE-M3 (MIT ○), Qwen3-Embedding (Apache-2.0 ○) self-hosted | Self-host when residency requires or cost > threshold |
| Malware scanning | ClamAV (optional, for shared uploads) | GPL-2.0 ○ (run as separate service; no linking) | Cloud AV services | Enable when org sharing of uploads is common |
| Email | Transactional email provider via SMTP/API, outbox-driven | Commercial ○ | Self-hosted Postal | — |
| Real-time | SSE from `api`; Valkey pub/sub fan-out | — | WebSocket gateway (Centrifugo, MIT ○) | When bi-directional real-time (co-editing) is required |
| Webhooks (outbound, R3) | Outbox → signed HTTP deliveries with retries | Own | Svix (MIT core ○) | — |
| Telemetry | OpenTelemetry SDKs + Collector | Apache-2.0 ○ | — | Keep |
| Metrics/logs/traces backend | Managed (cloud) or Grafana stack (Prometheus Apache-2.0; Loki/Tempo/Grafana AGPL-3.0 ○ — fine for internal unmodified use; legal check) | Mixed | SigNoz (MIT core/EE ○), Datadog (proprietary) | — |
| AI tracing / evaluation | Langfuse self-hosted (MIT core; `ee/` directories under a separate enterprise license ⚠ [comparison](https://langfuse.com/compare/arize-phoenix)) | MIT (core) | Arize Phoenix (Elastic License 2.0 ⚠) | Keep; only metadata + redacted prompts by default |
| Error tracking | Sentry SaaS or GlitchTip (MIT ○) | Sentry server FSL ○ | — | — |
| CI/CD | GitHub Actions; container builds; Renovate | Proprietary SaaS / AGPL (Renovate ○) | GitLab CI | — |
| IaC | OpenTofu | MPL-2.0 ○ | Terraform (BUSL ○), Pulumi (Apache-2.0 ○) | — |
| Runtime platform | MVP: managed containers (e.g., ECS Fargate / Cloud Run / Alibaba SAE per region) **or** a small managed Kubernetes cluster | Proprietary managed | Nomad | Kubernetes when > 12 services or need for gVisor node pools for Credential Worker (R2) |
| Secrets for the platform itself | Cloud secret manager (or OpenBao KV in self-hosted) injected at deploy | — | SOPS + age (MPL/BSD ○) | — |

## 2. Modular monolith versus services

**Recommendation: modular monolith with multiple process types from one image.**

| Process | Scaling signal | Separate identity / secrets |
| --- | --- | --- |
| `api` | RPS, SSE connections | DB role `app_rw`; no KMS decrypt |
| `orchestrator` | Active Attempts | DB role `worker_rw`; E2B API key |
| `worker` | Job lag | `worker_rw`; email provider key |
| `knowledge-worker` | Ingest lag | `worker_rw`; embedding ticket to gateway |
| `channel-worker` | Inbound/delivery lag | `worker_rw`; channel-class decrypt via Broker |
| `broker` | Tool call RPS | `broker_rw` (only role that reads `secret_versions`); KMS decrypt |
| `tool-gateway` | Tool call RPS | Calls Broker; no KMS |
| `model-gateway` | Model streams | Anthropic API key (from platform secret manager); usage writes |
| `credential-worker` (R2) | Invocations | Calls Broker; runs isolated units |
| `parser` (Java) | Parse queue | No DB access; no network egress |

Extraction triggers (measured, any one):

| Trigger | Extract |
| --- | --- |
| Deploy frequency conflicts: > 30% of releases blocked by unrelated module changes for 2 consecutive months | The blocking module into its own deployable with its own release cadence |
| Gateway latency/throughput: tool-gateway p99 overhead > 50 ms or > 2k RPS sustained | Gateways into a dedicated service (possibly Go/Envoy) |
| Security review requires separate codebase/audit scope for credentials | `trusted/*` into a separate repository and build pipeline |
| Team > 4 squads with conflicting ownership | Split by bounded context (identity/tenancy, runtime, knowledge, channels) |
| Data volume: `task_events` > 1 TB or `knowledge_chunks` > 200M rows | Dedicated database/cluster per context |

## 3. PostgreSQL usage rules

- Single database, schemas per bounded context (`identity`, `tenancy`, `tasks`, `knowledge`, `creds`, `platform`), shared tenant conventions.
- RLS on all tenant tables (`FORCE`); roles without `BYPASSRLS`; migrations by `owner` role in CI/CD only.
- PgBouncer in transaction mode; `SET LOCAL` per transaction; no session-level state.
- Optimistic concurrency: `row_version bigint` on mutable aggregates; `If-Match` ETags at API.
- Hot tables partitioned by time from day one: `task_events`, `audit_events`, `usage_events`, `jobs_archive`.
- Backups: provider PITR (≥ 14 days) + daily logical export of critical schemas to a different account/region.

## 4. Jobs and outbox

```sql
CREATE TABLE platform.jobs (
  id uuid PRIMARY KEY, tenant_id uuid, queue text NOT NULL, kind text NOT NULL,
  payload jsonb NOT NULL, dedupe_key text, run_at timestamptz NOT NULL DEFAULT now(),
  state text NOT NULL DEFAULT 'ready',          -- ready|leased|done|dead
  attempts int NOT NULL DEFAULT 0, max_attempts int NOT NULL DEFAULT 10,
  leased_until timestamptz, leased_by text, last_error text, created_at timestamptz DEFAULT now()
);
CREATE UNIQUE INDEX jobs_dedupe ON platform.jobs(queue, dedupe_key) WHERE state IN ('ready','leased');
CREATE INDEX jobs_ready ON platform.jobs(queue, run_at) WHERE state = 'ready';
-- consume:
-- UPDATE jobs SET state='leased', leased_until=now()+interval '60s', leased_by=:w, attempts=attempts+1
-- WHERE id IN (SELECT id FROM jobs WHERE queue=:q AND state='ready' AND run_at<=now()
--              ORDER BY run_at FOR UPDATE SKIP LOCKED LIMIT :n) RETURNING *;
```

Queues: `orchestration`, `knowledge`, `channel_in`, `channel_out`, `notify`, `maintenance`. Per-tenant fairness: consumers pick round-robin across tenants with pending work (`DISTINCT ON tenant_id` sampling) to prevent one tenant starving others.

## 5. Authentication and session details

- Keycloak realm `workx`; clients: `workx-api` (confidential, code flow + PKCE), `workx-admin` (internal ops, MFA required).
- API session: opaque cookie → `login_sessions` row (hash), sliding 7-day expiry, absolute 30 days, re-auth for sensitive actions (transfer ownership, delete tenant, create shared connection) within 10 min.
- Back-channel logout from Keycloak revokes sessions.
- MFA: optional for users R1; required for platform operators; org policy "require MFA" in R2.
- Bot/API access (R3): personal access tokens scoped to a tenant + actions, hashed, expiring.

## 6. Notifications, webhooks, SSE

| Channel | Mechanism |
| --- | --- |
| In-app | `notifications` table + tenant activity SSE |
| Email | Outbox → `notify` queue → provider; templates i18n; per-user preferences (global) and per-tenant mute |
| Feishu DM | Via channel-worker using org bot binding (only when the user has an external identity mapping in that tenant) |
| Outbound webhooks (R3) | Tenant-registered endpoints, HMAC-SHA256 signatures with timestamp, retries with backoff, event schema versioning |
| SSE | `api` instances subscribe to Valkey channels; replay from PG; heartbeat every 15 s; authorization re-check every 60 s |

## 7. Observability, audit, AI traces, evaluation

| Signal | Content | Store | Retention |
| --- | --- | --- | --- |
| Traces | OTel spans across api → jobs → orchestrator → gateways; `tenant_id`, `task_id`, `attempt_id` attributes; no payloads | Tempo/managed | 7–14 days |
| Metrics | RED per endpoint; queue lag; attempts by state; sandbox start latency; model tokens/cost; tool calls by connector/outcome; refresh failures | Prometheus/managed | 13 months (downsampled) |
| Logs | Structured JSON; redaction policy (Part 11 §6); request ids | Loki/managed | 14–30 days |
| Audit | Append-only `audit_events` (PG, partitioned) with hash chaining per tenant/day; export to object storage (WORM bucket) | PG + object storage | Per plan; default 1 year |
| AI traces | Langfuse: model, tokens, latency, tool sequence, cost, *redacted* prompt/response (opt-in full capture per tenant for debugging with expiry) | Langfuse (self-hosted, PG + ClickHouse ○) | 30 days |
| SDK telemetry | Agent SDK can export OTel spans/metrics/logs via env vars ([SDK hosting](https://code.claude.com/docs/en/agent-sdk/hosting) ✅) — would require collector egress from sandbox; R1 relies on Runner events + gateway telemetry instead; evaluate exporting through the Model Gateway host later | — | — |
| Evaluations | Golden sets per agent template and Knowledge benchmark; run on every Runner/SDK/template/prompt change | CI artifacts + Langfuse datasets | — |

## 8. CI/CD, environments, secrets, backups, DR, IaC

| Topic | Design |
| --- | --- |
| Environments | `local` (compose), `ci` (ephemeral), `staging` (prod-like, own E2B project, low budgets), `production` (per cell) |
| Pipeline | Lint/type-check (ruff, mypy/pyright, eslint, tsc) → unit → contract tests (OpenAPI diff, event schema compatibility) → import-linter boundary checks → integration (compose + E2B CI project) → security (SAST, dependency audit, container scan, secret scan, SBOM) → build image + E2B template → deploy staging → E2E + isolation suite → canary → production |
| Releases | Image digest pinned; DB migrations expand/contract; feature flags (DB-backed) per tenant |
| E2B template release | Template built in CI from `runtime/e2b-template`, smoke-tested, registered in `runtime_releases`, gradual rollout by new Sessions |
| Platform secrets | Cloud secret manager; injected as env at start for non-credential-zone services; Broker gets KMS access via workload identity |
| Backups | PG PITR + daily logical; object storage versioning + replication; Keycloak DB in same PG cluster (separate database); OpenBao (if used) Raft snapshots encrypted |
| DR | RPO ≤ 15 min, RTO ≤ 4 h for R1 (assumption to confirm); quarterly restore drills to a scratch environment |
| IaC | OpenTofu modules per cell: network, PG, object storage, Valkey, KMS, container platform, DNS, WAF; policy-as-code checks |
