# Part 5 — Sandbox filesystem and mounting (request §5.3)

Status: `/mnt/...` paths are **WorkX conventions** defined in `docs/SANDBOX-FILESYSTEM.md` [DOC]. Neither the Claude Agent SDK nor E2B requires them. The SDK only needs a `cwd` and a writable config directory ([SDK hosting](https://code.claude.com/docs/en/agent-sdk/hosting) ✅). E2B lets you choose mount paths for volumes, but volumes are beta (below). Nothing here is deployed.

## 1. Directory contract v1 (revised)

| Path | Purpose | Source | Writer | Agent access | Lifetime | Size cap (initial) |
| --- | --- | --- | --- | --- | --- | --- |
| `/mnt/session/uploads/` | Task inputs authorized for this Attempt | Object storage, copied by orchestrator | orchestrator (root) | read | Attempt; re-staged per Attempt | 2 GiB total |
| `/mnt/session/workspace/` | SDK `cwd`, scratch, intermediate files, Git | Checkpoint restore or empty | agent | read/write | Session; checkpointed at drain | 5 GiB |
| `/mnt/session/outputs/` | Deliverables to ingest | empty | agent | read/write | Until ingested | 500 MiB |
| `/mnt/knowledge/<revision>/` | Optional snapshot of small knowledge sources (≤ N files) | Object storage, by published revision | orchestrator | read | Attempt | 1 GiB |
| `/mnt/skills/<bundle_revision>/` | Curated Skills packaged as an SDK plugin | Skills bundle in object storage (hash-verified) | orchestrator | read | Attempt | 200 MiB |
| `/opt/workx/` | Runner and tools | Template image | image build | read/execute | Template | — |
| `/run/workx/<attempt_id>/` | RunSpec, manifests, control files, ticket bootstrap file (deleted after read) | orchestrator | orchestrator; Runner reads | Runner only (mode 0700, Runner user) | Attempt | 10 MiB |
| `/home/agent/.claude-ses/` | `CLAUDE_CONFIG_DIR`: SDK transcripts, CLI state | SDK | SDK | (agent process can read) | Session; transcripts checkpointed | 500 MiB |
| `/tmp/` | Tool temp files | — | any | rw | Sandbox | E2B disk |
| ~~`/mnt/persist/`~~ | ~~E2B volume~~ | — | — | — | **Removed from R1** (C-07) | — |

Front-end and APIs never expose these paths; they use `file_id`, `artifact_id`, `version_id`.

## 2. Mount versus copy

| Mechanism | Used for | Why |
| --- | --- | --- |
| **Copy (materialize)** from object storage into sandbox local disk, performed by orchestrator via E2B filesystem API | uploads, knowledge snapshot, skills bundle, checkpoint restore | No storage credentials in sandbox; exact revision; hash verification; works in every E2B region |
| **Upload back** by orchestrator reading sandbox files | outputs, checkpoints | Validation happens outside the sandbox |
| **Retrieval tool** (`knowledge.search`, `knowledge.read_passage` via Tool Gateway) | Large knowledge sources, connector-backed sources, anything permission-volatile | Avoids copying large corpora; permission checks at every call; revocation is immediate |
| E2B volumes | Not used in R1 | Private beta; no read-only mounts; no snapshots; permission bits not enforced between users; mounts fixed at creation; not available in APAC ([E2B volumes limitations](https://docs.e2b.dev/faq/volumes-beta-limitations.md) ◐) |
| FUSE-mounted buckets | Not used | Requires storage credentials or a signing proxy in the sandbox; weaker semantics |

Default knowledge mode is **retrieval tool**; snapshot copy is an agent-level option for small, stable reference sets (e.g., a style guide) where file tools are more effective than search.

## 3. Ownership and permissions inside the sandbox

- Template defines two Unix users: `workx` (Runner, owns `/run/workx`) and `agent` (the SDK/CLI child process and its tools). **[VALIDATE S-04]**: whether the E2B template can run the Runner as a non-root user without passwordless `sudo`, and whether E2B's command API permits starting processes as a specific user. If not possible, both run as the same user and §4 applies unchanged.
- Staged inputs: owner `root` or `workx`, mode `0444` files / `0555` directories.
- `workspace/` and `outputs/`: owner `agent`, mode `0700`.
- `/run/workx/<attempt>`: owner `workx`, mode `0700`; ticket bootstrap file read once by Runner and deleted.

## 4. What "read-only" actually guarantees

| Property | Classification | Enforcement |
| --- | --- | --- |
| Agent cannot alter the **system-of-record** copy of uploads, knowledge, or skills | **Product requirement — enforced** | Sources live in object storage/PG; nothing is ever read back from `uploads/`, `knowledge/`, `skills/`; only `outputs/` and checkpoint allow-listed paths are ingested and validated |
| Agent cannot alter the **local working copy** of inputs during an Attempt | Integrity measure (best effort) | File modes + non-root agent user (if S-04 passes) + `path_guard` hook for SDK Edit/Write. Bash running as the same user as the owner could bypass; therefore not a security claim |
| Skill instructions seen by the model are the reviewed version | Product requirement | Skills bundle hash verified at staging; plugin loaded from the staged path; after any tool call that writes under `/mnt/skills` (detected by hook or post-attempt hash check), the Attempt is flagged and skills are re-staged for the next Attempt |
| Knowledge permissions | Product requirement | Snapshot contents chosen by the orchestrator under the initiator's permissions at staging time; revocation mid-Attempt → Attempt ended and snapshot discarded (sandbox terminated) |
| Tenant isolation of files | Platform guarantee (E2B microVM per sandbox) + WorkX policy (one sandbox per Session, never reused across tenants) | Spike S-03/S-04 verify; vendor assurance reviewed |

## 5. Isolation between tenants and attempts

- **Between tenants**: separate sandboxes always; sandbox↔session mapping includes `tenant_id`; checkpoints under `t/{tenant_id}/...`, encrypted with tenant-scoped data keys (Part 13 §2).
- **Between Sessions of the same tenant**: separate sandboxes; no shared writable storage.
- **Between Attempts of the same Session**: same sandbox may be reused (Part 4 §5), but `/mnt/session/uploads`, `/mnt/knowledge`, `/mnt/skills`, and `/run/workx` are wiped and re-staged per Attempt; `outputs/` must be empty at Attempt start (leftovers from a failed ingestion are moved to `workspace/.workx-unpublished/`).
- **Participant change in a chat Session** (e.g., group chat membership changed): the Session's SDK context and workspace may contain data the new participants are not entitled to; the orchestrator starts a new SDK session and a fresh workspace.

## 6. Output ingestion and retention

| Item | Rule |
| --- | --- |
| Eligibility | Regular files under `outputs/` after realpath resolution; no symlinks/devices/FIFOs; depth ≤ 5; ≤ 200 files |
| Validation | Type sniffing, allow-list, macro rejection, size caps, filename normalization (Unicode NFC, no control chars), optional AV |
| Storage | Object key server-generated; `artifact_versions` row; sha256 recorded |
| Retention | Artifacts: tenant retention policy (default: until deleted by user); partial artifacts same, labeled; checkpoints: 14 days after Session close; staged copies: destroyed with sandbox |
| Deletion | Deleting an artifact deletes object versions after a soft-delete window (30 days) and removes search/index references |

## 7. Cleanup

| Trigger | Action |
| --- | --- |
| Attempt end | Wipe `/run/workx/<attempt>`, staged inputs; revoke tickets |
| Session close / idle TTL | Final checkpoint (if configured) → terminate sandbox |
| Reconciler orphan sweep | Terminate sandboxes without live binding |
| Tenant deletion | Terminate all sandboxes for tenant (by metadata), delete checkpoints |

## 8. Summary: requirement vs guarantee vs assumption

| Statement | Type |
| --- | --- |
| `/mnt/session/*` layout | WorkX convention (could change without vendor impact) |
| SDK uses `cwd` and `CLAUDE_CONFIG_DIR` | Platform behavior ✅ |
| Firecracker microVM isolation per E2B sandbox | Vendor claim (E2B infra README mentions Firecracker ✅); WorkX relies on it |
| Local read-only for inputs | Best-effort integrity; [VALIDATE S-04] |
| E2B volume read-only | **Not available** (vendor limitation ◐) |
| Egress allow-list effective against raw IP/DNS tricks | [VALIDATE S-03] |
| Paused sandbox retention period | Unverified (secondary source says 30 days ⚠) |
