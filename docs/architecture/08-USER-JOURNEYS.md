# Part 8 — User journeys and sequence diagrams (request C)

Each journey lists: **Auth** (authentication/authorization checks), **Tenant/SoR**, **APIs/events/states**, **Idempotency/recovery**, **Feedback/audit**. Credential internals referenced from Part 6 are not repeated.

## J1. Sign up and access the personal workspace

```mermaid
sequenceDiagram
  autonumber
  actor U as New user
  participant WEB as Web SPA
  participant API as api
  participant KC as Keycloak
  participant DB as PostgreSQL
  U->>WEB: Sign up
  WEB->>API: GET /api/v1/auth/login?intent=signup
  API-->>WEB: 302 to KC (OIDC code + PKCE, state)
  U->>KC: register (email+password or social), verify email
  KC-->>API: GET /api/v1/auth/callback?code&state
  API->>KC: token exchange (confidential client)
  API->>API: validate id_token (iss, aud, nonce), email_verified=true
  API->>DB: tx: upsert user by idp_subject · INSERT personal tenant ON CONFLICT (owner_user_id) DO NOTHING · owner membership · login_session · audit user.signed_up · outbox
  API-->>WEB: 302 /t/{personal_slug}/home + Set-Cookie wx_session (HttpOnly, Secure, SameSite=Lax)
  WEB->>API: GET /api/v1/me, GET /api/v1/me/tenants
  API-->>WEB: user + [personal tenant]
```

| Aspect | Detail |
| --- | --- |
| Auth | OIDC with PKCE; email must be verified before tenant provisioning |
| Tenant/SoR | Keycloak = credentials SoR; PG = user/tenant SoR |
| APIs/states | `auth/login`, `auth/callback`, `me`, `me/tenants`; tenant `provisioning→active` |
| Idempotency | Partial unique index on personal tenant; callback replay rejected by state |
| Feedback/audit | Lands in personal Home (empty state like prototype); `user.signed_up`, `tenant.created` |

## J2. Create an organization and invite a member

```mermaid
sequenceDiagram
  autonumber
  actor O as User (becomes owner)
  participant API as api
  participant DB as PostgreSQL
  participant W as worker (mailer)
  actor I as Invitee
  O->>API: POST /api/v1/tenants {name} (Idempotency-Key)
  API->>DB: tx: tenant(type=organization), membership(owner), audit, outbox
  API-->>O: 201 {tenant_id, slug}
  O->>API: POST /api/v1/tenants/{t}/invitations {emails:[...], role:"member"}
  API->>API: authorize_management(owner/admin, invite) · validate all emails · seat quota
  API->>DB: tx: invitations(token_digest, expires +7d) unique pending per email · outbox invitation.created
  API-->>O: 201 [{invitation_id, status:pending}]
  DB-->>W: job send_invitation_email
  W->>I: email with https://app/invite/{token}
  I->>API: GET /invite/{token} → login/signup (J1)
  I->>API: POST /api/v1/invitations/accept {token}
  API->>DB: tx: lock invitation · check pending, not expired, email == verified email, tenant active, seat · insert membership · invitation accepted · audit
  API-->>I: 200 {tenant_id} → /t/{org_slug}/home
```

| Aspect | Detail |
| --- | --- |
| Auth | Owner/admin for invite; invitee must be authenticated with matching verified email |
| Tenant/SoR | Org tenant in PG; invitation tokens only as digests |
| APIs/states | Invitation `pending→accepted/cancelled/expired`; membership `active` |
| Idempotency | Batch invite all-or-nothing; acceptance replay returns same membership; email job dedupe per invitation |
| Feedback/audit | Pending list in Members page (prototype SA-08); `invitation.created/accepted`; email delivery status recorded |

## J3. Switch workspace and load only authorized resources and connections

```mermaid
sequenceDiagram
  autonumber
  actor U as User
  participant WEB as Web SPA
  participant API as api
  participant DB as PostgreSQL
  U->>WEB: choose "Acme Org" in switcher
  WEB->>WEB: close SSE streams for old tenant · clear tenant-scoped query cache · drop sensitive drafts
  WEB->>API: PUT /api/v1/me/preferences {last_tenant_id} (navigation only)
  WEB->>API: GET /api/v1/tenants/{acme}/home-summary
  API->>DB: verify membership(acme, user) active · SET LOCAL app.tenant_id, app.membership_id
  API->>DB: SELECT tasks/agents/projects with resource_visibility RLS
  API-->>WEB: only resources visible to this membership
  WEB->>API: GET /api/v1/tenants/{acme}/connections?usable_by=me
  API-->>WEB: member-private (own) + org-shared allowed by usage policy (metadata only)
```

| Aspect | Detail |
| --- | --- |
| Auth | Per-request membership verification; RLS visibility policy |
| Tenant/SoR | Path tenant; no server "current tenant" |
| APIs | `home-summary`, list endpoints with cursor pagination |
| Idempotency/recovery | Background tasks in old tenant continue; their events arrive only to subscribers of that tenant |
| Feedback/audit | Toast "Switched to Acme"; no audit for reads except sensitive ones (connections list is not sensitive metadata) |

## J4. Create or configure an AI partner with Skills and Knowledge

```mermaid
sequenceDiagram
  autonumber
  actor U as Member/admin
  participant API as api
  participant DB as PostgreSQL
  participant BRK as broker
  U->>API: POST /tenants/{t}/agents {name, description, avatar}
  API->>DB: tx: agent(owner=membership, visibility private) + agent_version v1 (draft)
  U->>API: PATCH /tenants/{t}/agents/{a}/draft {instructions, model_tier, skills:[report-writer], knowledge_source_ids:[ks1], tools:[feishu_docs.create_doc]} If-Match: "v1-draft-3"
  API->>API: authorize use on each knowledge source · skills/connector installations enabled in tenant
  API->>BRK: preflight_bindings(agent draft, principal=me) (metadata only)
  BRK-->>API: [{connector:feishu-docs, identity:user, status:missing}]
  API->>DB: update draft (row_version check)
  API-->>U: 200 draft + dependency status (missing Feishu authorization)
  U->>API: POST /tenants/{t}/agents/{a}/publish
  API->>DB: tx: freeze agent_version v1 (immutable: instructions, model, skills bundle revision, knowledge refs, tool list, binding rules) · audit
  U->>API: PUT /tenants/{t}/resources/agent/{a}/sharing {visibility:"project", project_id, actions:["read","use"]}
  API->>DB: grants · audit sharing.changed
```

| Aspect | Detail |
| --- | --- |
| Auth | `edit` on agent; `use` on each attached knowledge source and connection; installation enabled |
| SoR | `agents`, `agent_versions` (immutable on publish), `runtime_bindings` |
| Concurrency | `If-Match` ETag on draft |
| Feedback | Dependency checklist (missing config / needs authorization / ready) mirroring `SKILL-RUNTIME-CONTRACT` states |
| Audit | `agent.published`, `sharing.changed` |

Sharing the agent shares instructions, skills, and knowledge *references*; other members still need `use` on the knowledge sources (or the share dialog offers to share them too) and their own connections for user-identity tools.

## J5. Submit a task and receive streamed progress and deliverables

```mermaid
sequenceDiagram
  autonumber
  actor U as Member
  participant WEB as Web SPA
  participant API as api
  participant DB as PostgreSQL
  participant ORC as orchestrator
  participant BRK as broker
  participant E2B as E2B sandbox (Runner+SDK)
  participant MGW as model-gateway
  participant TGW as tool-gateway
  participant OBJ as Object storage
  U->>WEB: type goal, attach file, choose partner
  WEB->>API: POST /tenants/{t}/tasks {agent_id, session_id?, input, attachments:[file_id]} Idempotency-Key
  API->>API: authorize use(agent), read(files) · quota & budget check
  API->>DB: tx: task(queued), job(start_attempt), event task.queued
  API-->>WEB: 202 {task_id}
  WEB->>API: GET /tenants/{t}/tasks/{id}/events (SSE)
  DB-->>ORC: job
  ORC->>BRK: preflight bindings + issue tickets (tool, model)
  ORC->>DB: tx: attempt(provisioning, fence=1, lease)
  ORC->>E2B: create sandbox (egress allow-list), stage inputs from OBJ, write RunSpec
  ORC->>E2B: start Runner
  E2B->>MGW: messages (model ticket)
  E2B->>TGW: tool calls (tool ticket)
  E2B-->>ORC: NDJSON frames
  ORC->>DB: task_events (seq), notify
  API-->>WEB: SSE assistant.delta / tool.started / tool.finished
  E2B-->>ORC: sdk_result success
  ORC->>E2B: read outputs/ (validated)
  ORC->>OBJ: upload artifact versions
  ORC->>DB: tx: artifact_versions available · task succeeded · attempt ended(success) · revoke tickets
  API-->>WEB: SSE artifact.published, task.succeeded
  ORC->>E2B: checkpoint → terminate (or pause per policy)
```

| Aspect | Detail |
| --- | --- |
| Auth | Session + membership; `use` on agent; `read` on attachments; tickets per Attempt |
| SoR | PG (task, attempt, events, artifacts), object storage (files) |
| States | Task `queued→running→finalizing→succeeded`; Attempt `provisioning→running→draining→ended` |
| Idempotency | Idempotency-Key; job dedupe `task:{id}:attempt:{n}`; event `(attempt, runner_event_id)`; artifact content hash |
| Recovery | SSE reconnect with `Last-Event-ID`; orchestrator crash → lease expiry → reconciler |
| Feedback/audit | Streaming text, tool progress (redacted), artifact cards; `task.created`, tool operations (writes), `artifact.published` |

## J6. Feishu message → tenant/user/connection resolution → task → reply in channel

```mermaid
sequenceDiagram
  autonumber
  actor FU as Feishu user
  participant FS as Feishu Open Platform
  participant CI as api (channel ingress)
  participant DB as PostgreSQL
  participant CHW as channel-worker
  participant ORC as orchestrator
  participant BRK as broker
  FU->>FS: @WorkX bot "summarize this week's sales docs"
  FS->>CI: POST /channels/feishu/{binding_public_id}/events (signed/encrypted) — or long-connection client in channel-worker
  CI->>CI: resolve binding by public id (not payload tenant) · verify signature/decrypt with channel secret (via broker) · timestamp window
  CI->>DB: INSERT inbound_messages (binding_id, platform_event_id UNIQUE)  · job process_inbound
  CI-->>FS: 200 (within platform ack window)
  DB-->>CHW: job
  CHW->>DB: binding active? trigger rule (DM or group @mention)? 
  CHW->>DB: external_identities(tenant, feishu tenant_key, open_id) → membership active?
  alt mapped member
    CHW->>DB: tx: session(scope=binding+chat+participants), task(created_by=membership, source=inbound), job start_attempt
  else unmapped
    CHW->>DB: delivery: reply "Link your WorkX account" (no task) — or service principal if binding policy allows anonymous with restricted agent
  end
  ORC->>BRK: preflight bindings for membership (user-identity tools need member's own Feishu user OAuth)
  Note over ORC: execution as J5
  ORC->>DB: tx: task succeeded · deliveries(queued, target=original chat, binding_revision)
  DB-->>CHW: job deliver
  CHW->>DB: binding unchanged & still allowed to reply? else delivery blocked
  CHW->>BRK: get tenant_access_token (class C, channel usage)
  CHW->>FS: send reply (message with summary + WorkX link to artifact · uuid=delivery_id for dedupe if supported)
  FS-->>CHW: message_id
  CHW->>DB: delivery delivered + receipt
```

| Aspect | Detail |
| --- | --- |
| Auth | Platform signature; binding active; identity mapping to active membership; bot identity never substitutes user consent for user-identity tools |
| Tenant/SoR | Tenant from binding; PG for inbound/task/delivery |
| States | Inbound `received→processed`; Task as J5; Delivery `queued→sending→delivered/failed/unknown/blocked` |
| Idempotency | `(binding_id, platform_event_id)`; delivery record per (task, artifact_version, target); Feishu message `uuid` when supported ○ |
| Recovery | Delivery retry reuses artifact; `unknown` → receipt query or manual |
| Feedback/audit | Bot typing/ack message optional; in-app inbox shows source; `channel.inbound`, `delivery.*` |

Group-chat privacy: replies in a group contain only content the group may see; if the task used member-private sources, the reply is posted as a WorkX link requiring login, not inline content (policy default).

## J7. Upload a document and later retrieve an authorized passage with citation

```mermaid
sequenceDiagram
  autonumber
  actor U as Member
  participant API as api
  participant OBJ as Object storage
  participant DB as PostgreSQL
  participant KW as knowledge-worker
  participant TK as parser (Tika)
  participant EG as embedding gateway
  participant TGW as tool-gateway
  participant SDK as Agent (E2B)
  U->>API: POST /tenants/{t}/knowledge-sources/{ks}/uploads {filename, size, sha256}
  API->>DB: file_version(uploading) · presigned PUT (5 min, exact length)
  U->>OBJ: PUT bytes
  U->>API: POST .../uploads/{id}/complete
  API->>OBJ: HEAD (size, checksum)
  API->>DB: tx: uploaded · revision(building) · job ingest
  DB-->>KW: job
  KW->>TK: parse (stream)
  TK-->>KW: content + metadata
  KW->>KW: normalize, chunk, label ACL
  KW->>EG: embed batches
  KW->>DB: chunks · publish revision (atomic)
  Note over U,SDK: later, during a task
  SDK->>TGW: knowledge_search {q} + ticket
  TGW->>DB: SQL hybrid search filtered by principal use(source) & published revision
  TGW->>DB: retrieval_logs(attempt, citation_ids)
  TGW-->>SDK: passages with citation ids
  SDK-->>U: answer with [[cite:...]] → rendered as source + page link
```

| Aspect | Detail |
| --- | --- |
| Auth | `edit` on knowledge source to upload; `use` at retrieval through the initiator principal |
| SoR | Object storage (raw, parse results), PG (chunks) |
| States | File `uploading→uploaded→scanning→parsing→indexed/failed`; Revision `building→published→superseded` |
| Idempotency | Upload complete idempotent by file version; ingest job dedupe by revision; chunk upsert by `chunk_key` |
| Feedback/audit | Per-file status; citations clickable; `knowledge.uploaded`, `knowledge.published` |

## J8. Execute a Skill or MCP tool using scoped credentials

Sequences: Part 6 Seq 3 (OAuth MCP), Seq 4 (API key), Seq 5 (env/.env Skill), Seq 6 (Feishu CLI). Summary of the shared checks:

```mermaid
sequenceDiagram
  autonumber
  participant SDK as Agent
  participant TGW as tool-gateway
  participant BRK as broker
  participant UP as Upstream / credential-worker
  SDK->>TGW: tools/call + ticket
  TGW->>BRK: ticket valid (tenant, attempt, fence, epochs, tool)
  TGW->>TGW: policy: principal use(connection), installation enabled, approval if high risk, rate limit
  TGW->>TGW: ledger: operation_key reserve (writes)
  TGW->>BRK: resolve credential material (class A/B/C) or dispatch (D)
  TGW->>UP: execute
  UP-->>TGW: result
  TGW->>TGW: ledger commit, redact, usage, audit
  TGW-->>SDK: result
```

| Aspect | Detail |
| --- | --- |
| Auth | Ticket + policy + connection usage policy + approval |
| SoR | `tool_operations`, `audit_events`, upstream |
| Idempotency | Operation ledger |
| Feedback | `tool.started/finished` events with redacted summary; approval prompts in chat |

## J9. Suspend for missing authorization, authorize, resume safely

Part 6 Seq 7 is the full diagram. User-facing summary:

```mermaid
sequenceDiagram
  autonumber
  actor U as Initiator
  participant WEB as Web SPA
  participant API as api
  participant ORC as orchestrator
  WEB-->>U: Task card: "Needs Feishu Docs authorization to continue" [Authorize]
  U->>WEB: click Authorize
  WEB->>API: POST /tenants/{t}/authorization-requests/{id}/start
  API-->>WEB: authorize_url (Part 6 Seq 1)
  Note over U,API: consent completes, connection active
  API-->>WEB: SSE auth.resolved, task.queued
  ORC-->>WEB: (via SSE) new attempt running "Resuming from checkpoint"
```

| Aspect | Detail |
| --- | --- |
| Auth | Only the target principal can complete the request; group chats receive only a WorkX login link |
| States | Task `running→needs_auth→queued→running`; old Attempt `ended(waiting_auth)`; new Attempt fence+1 |
| Idempotency | Resume job dedupe per authorization request; duplicate callbacks schedule once |
| Recovery | Expiry (default 7 days) → task `failed(auth_timeout)`; cancel while waiting → request cancelled; late consent stores connection only |
| Audit | `auth.required`, `connection.authorized`, `task.resumed` |

## J10. Cancel, retry, recover failed sandbox, partial results

```mermaid
sequenceDiagram
  autonumber
  actor U as Member
  participant API as api
  participant DB as PostgreSQL
  participant ORC as orchestrator
  participant E2B as Sandbox
  participant REC as reconciler
  U->>API: POST /tasks/{id}/cancel
  API->>DB: tx: cancel_requested · revoke leases · outbox
  API-->>U: 202
  ORC->>E2B: control cancel → interrupt → drain
  alt exits ≤20s
    E2B-->>ORC: exit
  else hung
    ORC->>E2B: kill runner / terminate sandbox (≤60s)
  end
  ORC->>DB: ingest valid outputs as partial · task cancelled
  Note over U,REC: Separate case: sandbox crash
  REC->>DB: attempt lease expired
  REC->>E2B: probe → unreachable
  REC->>DB: attempt interrupted(sandbox_lost) · tool_operations started→unknown
  alt no unknown operations and auto-retry budget left
    REC->>DB: job start_attempt (fence+1)
  else
    REC->>DB: task failed(recoverable) — needs user retry/reconcile
  end
  U->>API: POST /tasks/{id}/retry
  API->>DB: unknown ops? → 409 RECONCILIATION_REQUIRED {operations} : new attempt
```

| Aspect | Detail |
| --- | --- |
| Auth | `edit`/initiator or admin can cancel; retry requires `use` again (re-evaluated) |
| States | Task `cancel_requested→cancelled`; Attempt `interrupted`; partial artifacts |
| Idempotency | Cancel idempotent; retry uses Idempotency-Key; fencing blocks old attempt writes |
| Feedback/audit | "Stopped. 2 files saved as partial results"; "Needs your review: 1 action may or may not have completed" |

## J11. Remove a member or revoke a connection while tasks are active

Part 6 Seq 8 covers the credential side. User-facing and task outcomes:

```mermaid
sequenceDiagram
  autonumber
  actor A as Admin
  participant API as api
  participant DB as PostgreSQL
  participant ORC as orchestrator
  participant SSE as api SSE
  actor M as Removed member
  actor P as Project teammate
  A->>API: DELETE /tenants/{t}/members/{m}
  API->>DB: tx: membership removed · epochs++ · revoke leases · tasks initiated by m → cancel_requested(principal_removed)
  ORC->>ORC: cancel attempts (as J10)
  SSE-->>M: stream closed (403 on next check)
  SSE-->>P: shared task shows "Stopped: initiator no longer a member" + partial artifacts
  A->>API: (optional) reassign resources owned by m → P
  API->>DB: owner_membership_id updated, audit
```

| Aspect | Detail |
| --- | --- |
| Auth | Admin management action; cannot remove last owner |
| States | Tasks → `cancelled(principal_removed)`; connections owned by m → `revoked` |
| Recovery | A teammate can start a new task from the partial result under their own authorizations |
| Audit | `member.removed`, `connection.revoked`, `task.cancelled`, `resource.reassigned` |
