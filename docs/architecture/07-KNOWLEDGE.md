# Part 7 — Knowledge system (request §5.5)

Status: **[PROTO]** has only a free-text "work context" on agents (AG-04) and Markdown downloads; no upload parsing or retrieval. **[DOC]** `KNOWLEDGE-PIPELINE.md` proposes Tika + Meilisearch (auto-embedding, hybrid) evaluated against a PG + pgvector baseline. This part recommends shipping the PG baseline in R1 and running the Meilisearch evaluation as a spike (C-04).

## 1. Pipeline and component responsibilities

| Stage | Component | Responsibility | Output |
| --- | --- | --- | --- |
| Ingest | `api` (presigned upload) / connector sync job (R2) | Create `file` + `knowledge_source`; signed PUT to `t/{tenant}/raw/{file_id}/{version}`; on completion verify size + SHA-256 | `file_version(state=uploaded)` |
| Security checks | `knowledge-worker` | Magic-byte sniffing vs declared type; allow-list; size/page limits; archive policy (no nested archives in R1); encrypted-file detection; optional ClamAV | `scan_status` |
| Parse | `parser` (Apache Tika 4 server, isolated) | Text + metadata extraction; OCR for images/scanned PDFs with Tesseract (Tika 4 adds in-process Tesseract and Markdown output — [Tika 4.0.0](https://tika.apache.org/4.0.0/) ◐) | Raw parse output |
| Normalize | `knowledge-worker` | Convert to `ParseResult`: ordered blocks (heading/paragraph/table/list/image-caption), locators (page, sheet+range, slide, Feishu block id), quality flags, warnings | `parse_results` JSON in object storage |
| Chunk | `knowledge-worker` (**WorkX owns chunking** — Meilisearch and pgvector do not chunk long documents; Meilisearch guidance is to split documents into logical records before indexing per repo research) | Structure-aware chunks with stable `chunk_key` | `knowledge_chunks` rows |
| ACL labeling | `knowledge-worker` | Stamp `tenant_id`, `source_id`, `revision_id`, `acl_key` | columns on chunks |
| Embed | `knowledge-worker` → Embedding Gateway (part of `model-gateway`) | Batch embeddings with pinned `embedding_profile` | `vector` column |
| Index | PostgreSQL | `tsvector` (FTS) + `vector` (HNSW) | indexes |
| Publish | `knowledge-worker` | Atomic switch `knowledge_sources.published_revision_id` after all chunks indexed | `revision(state=published)` |
| Retrieve | `api` Knowledge API + Tool Gateway tool `knowledge_search` | Permission-filtered hybrid retrieval, optional rerank, citations | passages |

## 2. Supported formats (R1)

| Category | Formats | Parser path | Notes |
| --- | --- | --- | --- |
| Text | txt, md, csv, json, html | native (no Tika) | HTML sanitized; scripts dropped |
| PDF (text layer) | pdf | Tika | Page locators |
| PDF (scanned) | pdf | Tika + OCR (chi_sim + eng) | Flag `ocr=true`, `ocr_confidence` |
| Office | docx, xlsx, pptx | Tika | Sheet/range, slide locators; formulas as values |
| Legacy Office | doc, xls, ppt | Tika | Best effort; warn |
| Images | png, jpg, webp, tiff | OCR | R2: optional vision-model captioning via Model Gateway |
| Feishu Docs (R2) | via Open API structured blocks | connector adapter | Block-id locators; permissions synced |
| Rejected | executables, archives (R1), encrypted PDFs/Office | — | Clear error to user |

Limits (initial): 100 MB per file, 2,000 pages, 50 sheets, 2 million characters extracted; parse timeout 10 min; OCR page cap 300.

**Failures**: each file shows `uploaded → scanning → parsing → chunking → embedding → indexed` or `failed(reason)`, with partial results allowed when ≥ 90% of pages parsed (`completeness=partial`). Original files are always retained even when parsing fails.

**Large files**: streamed to Tika; pages processed in batches; embedding batched with backpressure; work is resumable by `(revision_id, batch_no)`.

## 3. Chunk design

| Field | Purpose |
| --- | --- |
| `chunk_key` | Stable hash of `(source_id, structural path, normalized text)` → enables incremental re-indexing |
| `text` | Chunk content, target 300–800 tokens (CJK-aware tokenizer), 10–15% overlap only across paragraph splits |
| `heading_path` | e.g., `Policy > Travel > Reimbursement` (prepended to embedding input, not to citation text) |
| `locator` | `{page: 12}` / `{sheet: "Q3", range: "A1:F40"}` / `{slide: 7}` / `{block_id: "doxcn…"}`; `locator_quality: exact|approximate|none` |
| `tsv` | `tsvector` built with a Chinese-capable parser (pg_jieba, BSD-3-Clause — [pg_jieba](https://pigsty.io/ext/e/pg_jieba/) ◐; or zhparser ○) plus `simple`/`english` config for Latin text |
| `embedding` | `vector(d)` per profile |
| `acl_key` | Identifier of the source's access rule (see §4) |
| `content_flags` | `ocr`, `table`, `suspected_instructions` (prompt-injection heuristic) |

Tables are chunked by row groups with header repetition; slides one chunk per slide unless large.

## 4. Permissions: document and chunk level

Knowledge sources are resources (Part 3): owner + grants. Chunks inherit their **source's** permission; R1 does not support per-chunk ACLs inside one source. For connector-synced content (R2), each external document becomes its own `knowledge_document` with an ACL mapped from the provider's permissions (see §6), and chunks inherit the document ACL.

Retrieval query (single SQL statement under RLS):

```sql
WITH allowed_sources AS (               -- sources the principal can USE in this tenant
  SELECT s.id, s.published_revision_id FROM knowledge_sources s
  WHERE s.tenant_id = :tenant AND s.deleted_at IS NULL
    AND s.id = ANY(:requested_source_ids)           -- the agent version's attached sources
    AND workx_can(:principal, 'use', 'knowledge_source', s.id)  -- SQL function mirroring authorize()
),
fts AS (
  SELECT c.id, ts_rank_cd(c.tsv, q) AS r FROM knowledge_chunks c
  JOIN allowed_sources a ON a.id = c.source_id AND a.published_revision_id = c.revision_id,
       websearch_to_tsquery('jieba_cfg', :q) q
  WHERE c.tenant_id = :tenant AND c.tsv @@ q
  ORDER BY r DESC LIMIT 50
),
ann AS (
  SELECT c.id, c.embedding <=> :qvec AS d FROM knowledge_chunks c
  JOIN allowed_sources a ON a.id = c.source_id AND a.published_revision_id = c.revision_id
  WHERE c.tenant_id = :tenant AND c.embedding_profile = :profile
  ORDER BY d LIMIT 50
)
SELECT id, sum(1.0 / (60 + rank)) AS rrf   -- reciprocal rank fusion
FROM (SELECT id, row_number() OVER (ORDER BY r DESC) rank FROM fts
      UNION ALL SELECT id, row_number() OVER (ORDER BY d) FROM ann) x
GROUP BY id ORDER BY rrf DESC LIMIT :k;
```

Authorization is applied **before** ranking (inside the CTEs), so unauthorized chunks never compete for top-K or leak through snippets. Note on pgvector HNSW with filters: post-filtering inside the index can reduce recall when the allowed set is small; mitigations are per-tenant partial indexes for large tenants, `hnsw.ef_search` tuning, and iterative scans (pgvector ≥ 0.8 ○) — measured in spike S-09.

Revocation is immediate: the next query re-evaluates `workx_can`. Sandboxes holding snapshots of a revoked source are terminated (Part 5 §4).

## 5. Versions, incremental indexing, deletion, retention

- `knowledge_revisions` per source: new upload or sync creates `revision n+1` in `building`; chunks are written with `revision_id`; unchanged `chunk_key`s copy their embedding from the previous revision (no re-embedding cost).
- Publish = single UPDATE of `published_revision_id` after all batches succeed. Running Attempts keep their pinned revision (Task records `knowledge_revision_ids`).
- Previous revision retained 7 days (for in-flight tasks and citations), then chunks deleted; citations to older revisions show "source updated since this answer" with a link to the current version.
- Source deletion: soft-delete (immediately excluded from retrieval) → purge job deletes chunks, parse results, raw objects after the tenant's retention window; checkpoints referencing the snapshot expire with their normal TTL.
- Embedding profile change (model/dimension): build a parallel profile column/table, backfill, switch, drop old — never mix profiles in one ANN query.

## 6. External connector content and permissions (R2)

| Concern | Design |
| --- | --- |
| Sync identity | Org-shared app connection (class C) for org-wide spaces, or member-private user connection for "my docs" |
| Scope | Admin selects spaces/folders; never "everything the app can see" by default |
| Permission mapping | Provider ACL (users/groups/departments) mapped to WorkX principals through `external_identities` and group mappings; unmappable principals are dropped (fail closed) |
| Freshness | Webhook/event subscriptions where available + periodic reconcile; ACL changes processed before content changes |
| Deletion | Upstream deletion → soft-delete within one sync cycle |
| Department principals | Provider "department" grants cannot map to WorkX departments in R1 (no department principal), so such documents are visible only to explicitly mapped users — a known limitation pending C-09 |

## 7. Search engine comparison and recommendation

| Criterion | **PG FTS + pgvector (R1 recommendation)** | Meilisearch (candidate) | OpenSearch (alternative) |
| --- | --- | --- | --- |
| License | PostgreSQL License (pgvector ○); pg_jieba BSD-3 ◐ | Community Edition MIT; Enterprise Edition BUSL; sharding is EE-only per docs ◐ ([Meilisearch editions](https://www.meilisearch.com/docs/resources/self_hosting/enterprise_edition)) | Apache-2.0 ○ |
| Hybrid search | Manual RRF (above) | Built-in hybrid with configured embedders, `semanticRatio` (repo research ◐) | Built-in |
| Embedding | WorkX computes (one pipeline) | Auto-embedder can call a provider; WorkX must then not embed again | Ingest pipelines or WorkX |
| Chinese text | pg_jieba/zhparser extension (managed PG support varies — **check provider**) | Built-in tokenizer with Chinese segmentation ○ | Analysis plugins (IK etc.) |
| ACL filtering | Same transaction, RLS + joins; revocation immediate | Filter expressions on indexed attributes; ACL changes require reindex of attributes; eventual consistency | Filters; eventual |
| Consistency with SoR | Transactional | Async tasks; must wait for task completion | Async |
| Ops burden | None extra | One more stateful service; backups/snapshots; HA requires EE sharding/replication or app-level duplication | Heavy |
| Scale ceiling | Tens of millions of chunks with partitioning [VALIDATE] | High for search; vector scale per instance [VALIDATE] | Very high |

Recommendation: R1 ships PG. Meilisearch replaces the PG search path only if spike S-09 on the same Chinese/English corpus shows ≥ 10% relative improvement in Recall@10/nDCG@10 or ≥ 2× lower p95 latency at target scale, **and** an ACL-revocation design with ≤ 5 s exposure window is demonstrated. In that case PG remains SoR and Meilisearch becomes a projection; WorkX keeps chunking; exactly one component computes embeddings.

## 8. Embedding providers

| Option | License / terms | Fit |
| --- | --- | --- |
| Hosted embedding API reachable from the deployment region (e.g., OpenAI, Voyage, Cohere; Alibaba DashScope for China) | Commercial API terms ○ | Fastest to ship; data leaves to provider; per-token cost |
| Self-hosted open models: BGE-M3 (MIT ○), Qwen3-Embedding (Apache-2.0 ○) on GPU behind Embedding Gateway | Open weights | Strong Chinese/English; data stays in region; GPU ops cost |

Anthropic does not provide an embeddings model of its own in its API ○; this is a separate provider decision (Q-09). R1: one hosted provider in the deployment region via Embedding Gateway; profile pinned; option to move to self-hosted for China/residency cells.

## 9. Retrieval quality, citations, deduplication, prompt-injection defense

- **Citations**: every passage returned to the agent carries `citation_id = (source_id, revision_id, chunk_id, locator)`. The agent is instructed to cite with `[[cite:<citation_id>]]`; the orchestrator validates that cited ids were actually returned to this Attempt (stored in `retrieval_logs`) and renders them as links; invalid citations are stripped and flagged.
- **Dedup**: near-duplicate chunks (same `chunk_key` text hash or MinHash > 0.9) collapsed at query time; per-source result caps for diversity.
- **Prompt injection**: retrieved text is wrapped as quoted, attributed data (`<document source=… untrusted="true">`); chunks flagged `suspected_instructions` are still returned but marked; tools with side effects require explicit user intent or approval when the triggering instruction appeared only in retrieved content (heuristic + approval policy).
- **Evaluation datasets**: per tenant-agnostic benchmark (internal corpus of mixed Chinese/English policy docs, spreadsheets, scanned PDFs) with 200+ labeled queries (exact terms, IDs, paraphrases, cross-lingual, table lookups). Metrics: Recall@k, nDCG@10, citation precision, answer faithfulness (LLM-judge with human calibration). Regression gate on parser/chunker/embedding changes.

## 10. Index repair, backfill, monitoring, disaster recovery

| Topic | Design |
| --- | --- |
| Repair | `reindex(source_id or tenant_id)` job rebuilds a new revision from stored `parse_results` (no re-parse) |
| Backfill | New embedding profile → background job by tenant with rate limits; progress table |
| Monitoring | Per-stage latency and failure rate; queue depth; OCR ratio; parse failure by type; retrieval latency p50/p95; zero-result rate; citation-invalid rate |
| DR | PG backups include chunks and vectors (restorable without re-embedding); raw files and parse results in versioned object storage; RPO/RTO as Part 13 §6 |
