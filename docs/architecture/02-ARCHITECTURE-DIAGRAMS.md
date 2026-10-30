# Part 2 — Architecture diagrams

Conventions used in every diagram:

- **Trust zones**: *Client* (browser, untrusted), *Control plane* (WorkX API/workers, trusted for business logic), *Trusted credential zone* (Broker, gateways, Credential Worker, key provider — only zone allowed to see plaintext upstream secrets), *Execution zone* (E2B sandbox, **untrusted**: model-directed code), *External* (third parties).
- **SoR** = system of record. PostgreSQL (PG) is SoR for business facts; object storage (S3-compatible) is SoR for file bytes.
- Dashed arrows are asynchronous (jobs/events). Solid arrows are synchronous calls.

## B1. System context and actors

```mermaid
flowchart LR
  subgraph People
    U["Personal user"]
    M["Org member"]
    AD["Org owner / admin"]
    OPS["WorkX operator (platform staff)"]
  end
  subgraph Ext["External systems"]
    FS["Feishu / Lark Open Platform\n(bot events, user OAuth, APIs)"]
    WC["WeCom (R2)"]
    MCP["Third-party MCP servers\n(no-auth / API key / OAuth)"]
    SAAS["Third-party SaaS APIs"]
    ANT["Anthropic Claude API"]
    E2B["E2B sandbox cloud"]
    MAIL["Email delivery provider"]
    IDP["Social / enterprise IdPs (OIDC/SAML)"]
    EMB["Embedding model provider"]
  end
  WX(["WorkX SaaS"])
  U -- "browser" --> WX
  M -- "browser / Feishu chat" --> WX
  AD -- "org admin console" --> WX
  OPS -- "internal admin, runbooks" --> WX
  FS <-- "events / replies / API calls" --> WX
  WC <-.-> WX
  WX -- "tool calls via gateway" --> MCP
  WX -- "API calls via gateway" --> SAAS
  WX -- "model calls via Model Gateway" --> ANT
  WX -- "create/control sandboxes" --> E2B
  WX --> MAIL
  WX <-- "OIDC/SAML" --> IDP
  WX --> EMB
```

Data ownership: WorkX owns tenants, users, memberships, tasks, artifacts, knowledge, connections, audit. External providers own their accounts and data; WorkX stores only tokens/keys it was granted (encrypted) and synchronized copies explicitly authorized by a tenant.

## B2. Overall logical architecture

```mermaid
flowchart TB
  subgraph Client["Client zone (untrusted)"]
    WEB["Web SPA\nReact + TS"]
  end
  subgraph CP["Control plane (trusted business logic)"]
    API["api (FastAPI)\nREST · SSE · OAuth callbacks · channel ingress"]
    ORC["orchestrator\nscheduler · leases · sandbox lifecycle · runner adapter · artifact ingestion"]
    WRK["worker\noutbox relay · notifications · retention · reconciler"]
    CHW["channel-worker\nverify · dedupe · identity map · delivery"]
    KW["knowledge-worker\nscan · parse orchestration · chunk · embed · index"]
  end
  subgraph TZ["Trusted credential zone"]
    BRK["broker\nconnections · tickets · refresh · unwrap"]
    TGW["tool-gateway\nMCP + HTTP proxy · policy · ledger"]
    MGW["model-gateway\nAnthropic proxy · budget · usage"]
    CRW["credential-worker\nisolated CLI / raw-secret programs"]
    KP[("KeyProvider\ncloud KMS or OpenBao Transit")]
  end
  subgraph EZ["Execution zone (untrusted)"]
    SBX["E2B sandbox\nWorkX Runner + Claude Agent SDK + CLI"]
  end
  subgraph Data["Data stores"]
    PG[("PostgreSQL\nSoR · jobs · audit · FTS · pgvector")]
    OBJ[("Object storage\nfiles · artifacts · checkpoints")]
    VK[("Valkey\nSSE fan-out · rate limits · caches")]
  end
  PARSE["parser (Apache Tika 4)\nno network"]
  WEB -->|"HTTPS cookie session"| API
  API --> PG
  API --> OBJ
  API --> VK
  API -.->|"jobs"| PG
  PG -.-> ORC
  PG -.-> WRK
  PG -.-> CHW
  PG -.-> KW
  ORC -->|"E2B API (control key)"| SBX
  SBX -->|"model calls + attempt ticket"| MGW
  SBX -->|"MCP / HTTP + attempt ticket"| TGW
  TGW --> BRK
  MGW --> BRK
  CRW --> BRK
  TGW --> CRW
  CHW --> BRK
  BRK --> KP
  BRK --> PG
  KW --> PARSE
  KW --> PG
  KW --> OBJ
  ORC --> OBJ
  ORC --> PG
  MGW --> ANTX["Anthropic API"]
  TGW --> EXT["MCP servers / SaaS APIs / Feishu APIs"]
  CHW --> FEI["Feishu / WeCom"]
```

Key rules: the sandbox reaches only the two gateways (enforced by E2B egress rules, see Part 4 §8); only the Broker can unwrap data-encryption keys; workers re-load tenant context from PG and never trust job payloads.

## B3. Frontend and workbench modules

```mermaid
flowchart TB
  subgraph Shell["App shell"]
    RT["Router\n/t/:tenantSlug/..."]
    AUTH["Session + tenant context provider"]
    I18N["i18n (en, zh-CN)"]
    SW["Workspace switcher"]
  end
  subgraph Features["Feature modules"]
    HOME["Home / task list"]
    CHAT["Task conversation\n(stream, approvals, needs_auth)"]
    AG["Partners (agents)\nconfig · versions · skills · knowledge"]
    PJ["Projects\nboard · members · context"]
    LIB["Library / artifacts\npreview · versions"]
    KN["Knowledge sources"]
    CON["Connections & credentials"]
    ECO["Channels (Feishu/WeCom bindings)"]
    INB["Channel inbox"]
    AUTO["Automations (R2)"]
    ORG["Org admin\nmembers · invites · roles · sharing · usage · audit"]
    PS["Personal settings\nprofile · language · my workspaces"]
  end
  subgraph Platform["Shared frontend platform"]
    API_C["Generated API client\n(openapi-typescript + fetch)"]
    QRY["TanStack Query cache\n(key includes tenantId)"]
    SSE["SSE manager\nper task · resume by Last-Event-ID"]
    DS["Design system\nRadix primitives + tokens"]
  end
  RT --> AUTH --> Features
  Features --> QRY --> API_C
  CHAT --> SSE
  INB --> SSE
  Features --> DS
  SW --> AUTH
```

Every query key and SSE subscription includes `tenantId`; switching workspace clears tenant-scoped caches and closes streams (Part 9 §4).

## B4. Backend domain modules and control-plane boundaries

```mermaid
flowchart LR
  subgraph Core["workx (Python package) — domain modules"]
    IDN["identity\nusers · sessions · external identities"]
    TEN["tenancy\ntenants · memberships · invitations · roles"]
    AZ["authz\npolicy evaluator · grants · RLS context"]
    RES["resources\nprojects · files · sharing"]
    AGT["agents\nagents · versions · skills catalog · installations"]
    TSK["tasks\nsessions · tasks · attempts · approvals · ledger"]
    ART["artifacts\nartifacts · versions · ingestion"]
    KNO["knowledge\nsources · revisions · chunks · retrieval"]
    CNX["connections\nconnectors · connections · bindings"]
    CRD["credentials (trusted)\nsecret versions · tickets · refresh"]
    CHN["channels\nbindings · inbound · deliveries"]
    USG["usage\nmetering · quotas · budgets"]
    AUD["audit\nappend-only log · redaction"]
    PLT["platform\njobs · outbox · config · telemetry"]
  end
  TEN --> IDN
  AZ --> TEN
  RES --> AZ
  AGT --> AZ
  TSK --> AGT
  TSK --> RES
  TSK --> USG
  ART --> RES
  KNO --> RES
  CNX --> AZ
  CRD --> CNX
  CHN --> TSK
  CHN --> CNX
  Core --> PLT
  AUD -.-> PLT
```

Dependency rule: arrows point to modules a module may import. `credentials` is importable only from trusted-zone process entrypoints (`broker`, `tool-gateway`, `model-gateway`, `credential-worker`, `channel-worker`); the `api` process accesses credentials only through Broker RPC with metadata-only responses. Enforced by import-linter contracts (Part 12 §3).

## B5. Tenant, identity, and resource authorization model

```mermaid
flowchart TB
  USER["User (global identity)"]
  SESS["Login session\n(server-side, revocable)"]
  PT["Tenant type=personal\n(exactly 1 per user)"]
  OT["Tenant type=organization"]
  MEM["Membership\n(tenant, user, role, status, department?)"]
  ROLE["Role: owner | admin | member\n(management permissions only)"]
  RSRC["Resource\n(tenant_id, owner_membership_id, visibility)"]
  GR["ResourceGrant\n(principal → actions)"]
  PRJ["Project membership"]
  SP["Service principal\n(channel bot, automation)"]
  USER --> SESS
  USER -->|"owns"| PT
  USER --> MEM
  MEM --> PT
  MEM --> OT
  MEM --> ROLE
  RSRC --> GR
  GR -->|"principal_type=membership"| MEM
  GR -->|"principal_type=project"| PRJ
  GR -->|"principal_type=tenant (all active members)"| OT
  GR -->|"principal_type=service_principal"| SP
  PRJ --> MEM
  DEC{"authorize(principal, action, resource)\n= active membership\n∧ tenant match\n∧ (owner ∨ grant ∨ role-admin-action)\n∧ resource not deleted"}
  ROLE --> DEC
  GR --> DEC
  RSRC --> DEC
```

Note what is absent: no edge from Role to private resources, no department edge. Admin role grants management actions (members, invitations, connections policy, audit view) but not `read` on private resources (Part 3 §6).

## B6. Agent runtime: E2B sandbox, WorkX Runner, SDK, tools, workers

```mermaid
flowchart LR
  subgraph CP["Control plane"]
    ORC["orchestrator\nlease + fencing token"]
    PG[("PostgreSQL")]
    OBJ[("Object storage")]
  end
  subgraph SBX["E2B sandbox (one per active WorkX session)"]
    direction TB
    RUN["WorkX Runner (Python)\nRunSpec · NDJSON events · control · drain"]
    SDK["ClaudeSDKClient\nsetting_sources=[] · plugins=[skills rev]\npermission_mode=dontAsk · hooks"]
    CLI["claude CLI subprocess\n(bundled with SDK version)"]
    FS["/mnt/session/{uploads,workspace,outputs}\n/mnt/knowledge/rev · /mnt/skills/rev"]
    RUN --> SDK --> CLI
    CLI --> FS
  end
  subgraph TZ["Trusted credential zone"]
    MGW["model-gateway"]
    TGW["tool-gateway (MCP server to sandbox,\nMCP/HTTP client upstream)"]
    BRK["broker"]
    CRW["credential-worker"]
  end
  ORC -->|"create/connect, write files, start runner"| SBX
  RUN -->|"stdout NDJSON"| ORC
  ORC -->|"control file / stdin: cancel, approval"| RUN
  CLI -->|"ANTHROPIC_BASE_URL + attempt ticket"| MGW
  CLI -->|"MCP over HTTPS + attempt ticket"| TGW
  TGW --> BRK
  MGW --> BRK
  TGW --> CRW
  ORC --> PG
  ORC -->|"inputs download / outputs + checkpoints upload"| OBJ
```

Authoritative state lives in PG (task, attempt, ledger, events) and object storage (inputs, outputs, checkpoints). The sandbox holds caches and working copies only (Part 4 §3).

## B7. Credential Broker, gateways, secret storage, OAuth trust boundaries

```mermaid
flowchart TB
  subgraph Browser["Client zone"]
    UI["Web UI: connect / authorize"]
  end
  subgraph CP["Control plane"]
    API["api\n(connection metadata only)"]
  end
  subgraph TZ["Trusted credential zone (separate deploy, network policy, identities)"]
    BRK["broker\n- OAuth client (PKCE, state, CIMD/pre-reg)\n- single refresh owner (CAS)\n- ticket issue/verify\n- DEK unwrap"]
    TGW["tool-gateway\n- verify ticket per call\n- fixed routes, SSRF guard\n- inject header / token\n- operation ledger"]
    MGW["model-gateway\n- verify model ticket\n- inject Anthropic key\n- budget + usage"]
    CHW["channel-worker\n- bot secrets (usage_class=channel)"]
    CRW["credential-worker\n- per-invocation isolated unit\n- env/.env/cert files"]
    KP[("KeyProvider")]
  end
  subgraph Store["PostgreSQL"]
    META[("connections, credentials\n(metadata)")]
    SV[("secret_versions\nciphertext + wrapped DEK\nRLS + separate DB role")]
    TK[("credential_leases\nticket hash only")]
  end
  subgraph EZ["Execution zone"]
    SBX["E2B sandbox\n(holds only opaque tickets)"]
  end
  EXT["Upstream: OAuth AS, MCP servers, SaaS APIs, Feishu"]
  UI -->|"start authorization"| API
  API -->|"RPC: create auth session"| BRK
  UI -.->|"redirect"| EXT
  EXT -.->|"callback (code, state)"| BRK
  BRK --> KP
  BRK --> SV
  BRK --> META
  BRK --> TK
  SBX -->|"ticket"| TGW
  SBX -->|"ticket"| MGW
  TGW -->|"resolve(ticket, op) → short-lived material"| BRK
  MGW --> BRK
  CRW --> BRK
  CHW --> BRK
  TGW --> EXT
  CRW --> EXT
```

Boundary statements: plaintext upstream secrets exist only in trusted-zone process memory; `secret_versions` is readable only by the `broker` DB role; the OAuth callback endpoint is served by the Broker (routed via the public ingress), not by the general API process.

## B8. Skill, MCP, CLI, and connector execution routes

```mermaid
flowchart LR
  AG["Agent (in sandbox)"]
  subgraph InSbx["Inside sandbox"]
    SK["Skill instructions\n(curated, read-only copy)"]
    LOC["Local compute\n(python, node, office libs)"]
  end
  subgraph TZ["Trusted zone"]
    TGW["tool-gateway"]
    CRW["credential-worker"]
    BRK["broker"]
  end
  C0["Class 0: no-auth HTTP MCP"]
  CA["Class A: API key / bearer / custom header"]
  CB["Class B: OAuth-protected HTTP MCP / API"]
  CC["Class C: exchange / signing (Feishu tenant token, request signing)"]
  CD["Class D: raw-secret programs (stdio MCP with secrets, DB drivers, certs, Feishu CLI)"]
  WH["Webhooks / events (inbound)"]
  AG --> SK --> LOC
  AG -->|"mcp__workx__*"| TGW
  TGW -->|"no auth header"| C0
  TGW -->|"inject static header"| CA
  TGW -->|"inject access token (Broker refresh)"| CB
  TGW -->|"Broker exchange/sign"| CC
  TGW -->|"dispatch job"| CRW
  CRW -->|"env/.env/cert in isolated unit"| CD
  TGW --> BRK
  CRW --> BRK
  WH -->|"channel ingress → channel-worker"| CHW["channel-worker"]
```

The agent sees one MCP server per installed connector (all served by the Tool Gateway). Upstream transport, auth class, and execution location are hidden behind a stable tool contract.

## B9. Knowledge ingestion, indexing, retrieval

```mermaid
flowchart LR
  UP["Upload (presigned PUT)"] --> OBJ[("Object storage\nraw/")]
  CONN["Connector sync (R2)"] --> OBJ
  OBJ --> SCAN["knowledge-worker: validate\n(size, type sniff, hash, AV optional)"]
  SCAN --> PARSE["parser: Tika 4 (+Tesseract OCR)\nsandboxed, no network"]
  PARSE --> NORM["normalize → ParseResult blocks\n(locators, quality flags)"]
  NORM --> CHK["chunker (WorkX)\nheading/paragraph aware, token caps"]
  CHK --> ACL["ACL label: tenant_id, source_id,\nacl_key (resource grant snapshot ref)"]
  ACL --> EMB["embedding via Embedding Gateway\n(profile pinned)"]
  EMB --> IDX[("PostgreSQL\nchunks: tsvector + vector")]
  IDX --> PUB["publish revision (atomic switch)"]
  Q["Knowledge API / MCP tool\n(tenant + principal from ticket)"] --> FILT["permission filter in SQL\n(RLS + grant join)"]
  FILT --> HYB["hybrid: BM25-ish FTS ∪ ANN → RRF"]
  HYB --> RR["optional rerank"]
  RR --> CIT["passages + citations\n(source, revision, locator)"]
  CIT --> AGENT["Agent context (untrusted content markers)"]
```

## B10. Task queues, workers, events, recovery

```mermaid
flowchart TB
  subgraph TX["Single PG transaction"]
    W1["write domain row\n(task/attempt/delivery/...)"]
    W2["insert outbox_events"]
    W3["insert jobs (queue, run_at, dedupe_key)"]
  end
  TX --> PGJ[("jobs table")]
  PGJ -->|"SELECT ... FOR UPDATE SKIP LOCKED\nlease_until, attempt"| CONS["consumers:\norchestrator · worker · channel-worker · knowledge-worker"]
  CONS -->|"success: delete/complete"| PGJ
  CONS -->|"failure: backoff, attempt++"| PGJ
  PGJ -->|"attempt > max"| DLQ[("jobs state=dead\n+ alert")]
  TX --> OUTB[("outbox_events")]
  OUTB --> RELAY["worker: outbox relay"]
  RELAY --> VK[("Valkey pub/sub\nchannel tenant:task")]
  VK --> SSEA["api SSE endpoints"]
  SSEA -->|"miss? replay from task_events"| TEV[("task_events (seq)")]
  REC["reconciler (every 30s)"] -->|"expired leases, orphan sandboxes,\nunknown deliveries, stuck finalizing"| PGJ
```

Recovery invariants: (1) jobs are at-least-once, handlers idempotent by `dedupe_key`; (2) an Attempt's writes are accepted only with the current fencing token; (3) Valkey loss loses only live fan-out — clients replay from `task_events`.

## B11. Deployment — MVP and scaled production

### B11a. MVP (single region)

```mermaid
flowchart TB
  subgraph Edge["Edge"]
    CDN["CDN + static SPA"]
    LB["HTTPS load balancer / WAF"]
  end
  subgraph CPNet["Private network: control plane"]
    APIx["api ×2"]
    ORCx["orchestrator ×2"]
    WRKx["worker ×1–2"]
    CHWx["channel-worker ×1"]
    KWx["knowledge-worker ×1"]
    PRS["parser (Tika) ×1"]
    KC["Keycloak ×2"]
  end
  subgraph TZNet["Private network: trusted zone (separate SG / namespace)"]
    BRKx["broker ×2"]
    TGWx["tool-gateway ×2 (public ingress for sandbox)"]
    MGWx["model-gateway ×2 (public ingress for sandbox)"]
    CRWx["credential-worker pool (gVisor/Firecracker) — R2"]
  end
  subgraph Managed["Managed services"]
    PGm[("Managed PostgreSQL (HA)")]
    OBJm[("Object storage")]
    VKm[("Managed Valkey/Redis-compatible")]
    KMSm[("Cloud KMS")]
  end
  E2Bc["E2B cloud"]
  CDN --> LB
  LB --> APIx
  LB --> KC
  LB -->|"/oauth/callback/*"| BRKx
  E2Bc -->|"sandbox egress (allow-listed)"| TGWx
  E2Bc --> MGWx
  ORCx --> E2Bc
  APIx --> PGm
  ORCx --> PGm
  BRKx --> PGm
  BRKx --> KMSm
  APIx --> OBJm
  APIx --> VKm
```

The gateways must be reachable from E2B's egress, so they have their own internet-facing ingress restricted to E2B egress IP ranges when available ([VALIDATE] S-03) and authenticated by attempt tickets regardless.

### B11b. Scaled production (multi-AZ, optional multi-region)

```mermaid
flowchart TB
  subgraph R1["Region A (primary)"]
    K8S["Kubernetes cluster\nnamespaces: control, trusted, jobs"]
    PGP[("PostgreSQL primary + sync replica\n+ read replicas")]
    PGB["PgBouncer (transaction mode)"]
    OBJA[("Object storage (versioned, replicated)")]
    VKA[("Valkey cluster")]
    OTL["OTel collector → metrics/logs/traces"]
  end
  subgraph R2["Region B (DR / data residency)"]
    PGS[("PostgreSQL async standby")]
    OBJB[("Object storage replica")]
    K8SB["Warm standby cluster"]
  end
  K8S --> PGB --> PGP
  PGP -.->|"async replication"| PGS
  OBJA -.->|"bucket replication"| OBJB
  K8S --> OBJA
  K8S --> VKA
  K8S --> OTL
  K8S --> E2BS["E2B (cloud or BYOC/self-hosted infra)"]
```

Data-residency deployments become *cells*: a full stack per jurisdiction with tenant-to-cell routing; tenants never span cells (Part 13 §9).

## B12. Repository and package dependency direction

```mermaid
flowchart BT
  CONTRACTS["packages/contracts\n(OpenAPI + JSON Schema + event schemas)"]
  TSCLIENT["packages/api-client (generated TS)"]
  UI["packages/ui (design system)"]
  WEBAPP["apps/web"]
  CORE["services/workx/src/workx/core\n(shared kernel: ids, errors, tenancy ctx, db)"]
  DOM["workx/domains/*"]
  TRUST["workx/trusted/* (credentials, broker, gateways)"]
  ENTRY["workx/entrypoints/* (api, orchestrator, worker, ...)"]
  RUNNER["runtime/runner (Python, runs in E2B)"]
  RPROTO["packages/runner-protocol (Python + JSON Schema)"]
  TPL["runtime/e2b-template"]
  TSCLIENT --> CONTRACTS
  WEBAPP --> TSCLIENT
  WEBAPP --> UI
  DOM --> CORE
  TRUST --> DOM
  TRUST --> CORE
  ENTRY --> DOM
  ENTRY --> TRUST
  RUNNER --> RPROTO
  DOM --> RPROTO
  TPL --> RUNNER
  CONTRACTS -. "generated from" .-> ENTRY
```

Arrows point from dependent to dependency. `runtime/runner` must not import `services/workx` (it runs in the untrusted zone and only knows the protocol). `domains/*` must not import `trusted/*`.
