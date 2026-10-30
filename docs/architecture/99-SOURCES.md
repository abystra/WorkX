# Part 99 — Sources and verification status

Accessed 2026-10-30. Marks: ✅ fetched and read; ◐ official page content seen through search indexing (page host blocked from this session); ⚠ secondary source; ○ not verified this session.

## Anthropic / Claude

| Source | Used for | Mark |
| --- | --- | --- |
| [Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview) | Commercial Terms license; claude.ai login not allowed for third-party products; branding rules; Python/TypeScript | ✅ |
| [Hosting the Agent SDK](https://code.claude.com/docs/en/agent-sdk/hosting) | Subprocess model, resources, SessionStore semantics, multi-tenant isolation options, token cost dominance, OTel | ✅ |
| [Securely deploying AI agents](https://code.claude.com/docs/en/agent-sdk/secure-deployment) | Proxy pattern, `ANTHROPIC_BASE_URL`, CONNECT tunnel limits, isolation technologies | ✅ |
| [Configure permissions](https://code.claude.com/docs/en/agent-sdk/permissions) | Evaluation order; `allowed_tools` semantics; `dontAsk`; bypass caveats | ✅ |
| [Connect to external tools with MCP](https://code.claude.com/docs/en/agent-sdk/mcp) | Transports, headers/env, no OAuth flow in SDK, `needs-auth` status | ✅ |
| [Extend agents with skills](https://code.claude.com/docs/en/agent-sdk/skills) | Skill discovery, `plugins`, `skills` allow-list | ✅ |
| [Supported countries and regions](https://www.anthropic.com/supported-countries) | Mainland China, Hong Kong, Macau not supported | ✅ |
| [Managed Agents secure deployment](https://platform.claude.com/docs/en/managed-agents/secure-deployment) | Vault header injection; self-hosted sandboxes beta; env credentials unsupported in self-hosted | ◐ |

## E2B

| Source | Used for | Mark |
| --- | --- | --- |
| [e2b-dev/infra](https://github.com/e2b-dev/infra) | Apache-2.0; Embed single-host package for GCP/AWS/Azure + Kubernetes; Firecracker; Enterprise BYOC | ✅ |
| [Internet access](https://docs.e2b.dev/network/internet-access) | `allowInternetAccess`, `allowOut`/`denyOut`, live updates | ◐ |
| [Bring your own proxy](https://docs.e2b.dev/network/byop.md) | SOCKS5 proxy private beta | ◐ |
| [Volumes beta limitations](https://docs.e2b.dev/faq/volumes-beta-limitations.md) | No read-only mounts, no snapshots, permissions not enforced, mounts fixed, not available in APAC | ◐ |
| [Sandbox persistence](https://docs.e2b.dev/sandbox/persistence) | Pause keeps memory + filesystem; filesystem-only option; resume timeout reset; auto-pause | ◐ |
| [Secrets injection](https://docs.e2b.dev/secrets/inject) | Per-host HTTPS header transforms outside sandbox | ◐ |
| [Novita guide (E2B-compatible)](https://novita.ai/docs/guides/sandbox-e2b-sandbox-persistence) | 30-day paused retention claim | ⚠ |
| [Alibaba Cloud FC Agent Sandbox release log](https://help.aliyun.com/en/functioncompute/feature-release-log-for-fc-agent-sandbox-2026) | E2B-SDK-compatible sandbox with China regions | ⚠ (third-party relative to E2B) |

## Protocols and integrations

| Source | Used for | Mark |
| --- | --- | --- |
| [MCP specification directory](https://github.com/modelcontextprotocol/modelcontextprotocol/tree/main/docs/specification) | Latest dated version 2026-07-28 | ✅ |
| [MCP authorization 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization) | CIMD SHOULD, DCR MAY, registration order | ◐ |
| [SSOJet: MCP auth 2026-07-28 changes](https://ssojet.com/blog/mcp-authorization-spec-2026-07-28-what-changed) | DCR deprecated in favor of CIMD | ⚠ |
| [Nango repository](https://github.com/NangoHQ/nango) | Elastic License; free self-hosting limited | ✅ |
| [Nango free self-hosting](https://nango.dev/docs/guides/platform/free-self-hosting.md) | Auth + proxy only; MCP server not in free self-hosting | ◐ |
| [lark-cli sidecar package](https://pkg.go.dev/github.com/larksuite/cli/sidecar) | Same-machine only; MIT | ◐ |
| [Feishu: embed CLI in agent](https://open.larkoffice.com/document/mcp_open_tools/feishu-cli/embed-feishu-cli-in-agent.md) | Credential provider and transport extensions | ◐ |
| [Feishu refresh user_access_token](https://open.feishu.cn/document/authentication-management/access-token/refresh-user-access-token.md) | Single-use refresh tokens; `offline_access` | ◐ |

## Infrastructure and licenses

| Source | Used for | Mark |
| --- | --- | --- |
| [Redis licenses](https://redis.io/legal/licenses/) | Redis 8 tri-license incl. AGPLv3 | ◐ |
| [vonng: MinIO is dead](https://blog.vonng.com/en/db/minio-is-dead/) | MinIO CE maintenance/archival | ⚠ |
| [Zitadel AGPL announcement](https://zitadel.com/blog/apache-to-agpl) | AGPL-3.0 from v3 | ◐ |
| [Hatchet repository](https://github.com/hatchet-dev/hatchet) | MIT, Postgres-only dependency | ◐ |
| [DBOS on PyPI](https://pypi.org/pypi/dbos) | MIT, Postgres-backed durable execution | ◐ |
| [Langfuse vs Phoenix](https://langfuse.com/compare/arize-phoenix) | Langfuse MIT core with `ee/`; Phoenix ELv2 | ⚠ (vendor page) |
| [OpenBao 2.7.0 release notes](https://openbao.org/community/release-notes/2-7-0/) | Release line status | ◐ |
| [Apache Tika 4.0.0](https://tika.apache.org/4.0.0/) | 4.0 release; in-process Tesseract; Markdown output | ◐ |
| [pg_search on PGXN](https://pgxn.org/dist/pg_search) | AGPL-3.0 or commercial | ◐ |
| [pg_jieba](https://pigsty.io/ext/e/pg_jieba/) | BSD-3-Clause Chinese segmentation for PG | ◐ |
| [Meilisearch Enterprise Edition](https://www.meilisearch.com/docs/resources/self_hosting/enterprise_edition) | CE MIT, EE BUSL, sharding EE-only | ◐ |
| OpenFGA / SpiceDB / Cerbos license comparison ([startwithidentity](https://startwithidentity.com/articles/top-7-open-source-authorization-tools/)) | Apache-2.0 (SpiceDB conflicting report) | ⚠ |

## Not verified this session (re-verify before locking versions)

Keycloak (Apache-2.0), Valkey (BSD-3-Clause), SeaweedFS (Apache-2.0), Garage (AGPL-3.0), pgvector (PostgreSQL License) and iterative-scan features, Temporal (MIT), Procrastinate (MIT), OpenTelemetry (Apache-2.0), Grafana/Loki/Tempo (AGPL-3.0), Prometheus (Apache-2.0), ClamAV (GPL-2.0), Docling (MIT), Unstructured (Apache-2.0), BGE-M3 (MIT), Qwen3-Embedding (Apache-2.0), OpenTofu (MPL-2.0), Envoy (Apache-2.0), OpenBao (MPL-2.0), FastAPI/SQLAlchemy/Pydantic/React/Vite/TanStack/i18next/Radix (MIT), psycopg (LGPL-3.0), Sentry server (FSL), Feishu vs Lark platform separation details, Feishu message `uuid` dedupe parameter, availability of pg_jieba/zhparser on candidate managed PostgreSQL services.

## Repository evidence

All files under `abystra/WorkX@f262dc5` (Part 0 inventory). Prototype verification: `npm run check` OK; `npm test` 73/73 pass (Node 22.22.0); no `fetch`/`XMLHttpRequest`/`EventSource` usage in `dist/*.js` (WebSocket appears only in UI strings); persistence via `localStorage`.
