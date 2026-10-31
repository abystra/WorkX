"""Knowledge (Part 7): sources made from Library files, revisions, chunks with full-text and embedding columns,
retrieval logs for citation validation, citations on task messages.

Embeddings are stored as ``real[]`` and ranked in SQL, which needs no extension. When pgvector is installed, a
deployment adds a ``vector`` column and an HNSW index (runbook in docs/delivery); the query falls back to the
array path otherwise.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-31
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

TABLES = ("knowledge_sources", "knowledge_revisions", "knowledge_chunks", "retrieval_logs")


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE knowledge_sources (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          file_id uuid NOT NULL,
          name text NOT NULL,
          owner_membership_id uuid NOT NULL,
          status text NOT NULL DEFAULT 'processing' CHECK (status IN ('processing', 'ready', 'failed')),
          error_code text,
          published_revision_id uuid,
          deleted_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, id),
          FOREIGN KEY (tenant_id, file_id) REFERENCES files (tenant_id, id)
        );
        CREATE UNIQUE INDEX knowledge_sources_one_per_file ON knowledge_sources (tenant_id, file_id)
          WHERE deleted_at IS NULL;

        CREATE TABLE knowledge_revisions (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL,
          source_id uuid NOT NULL,
          revision_no int NOT NULL,
          file_version_id uuid NOT NULL,
          state text NOT NULL DEFAULT 'building' CHECK (state IN ('building', 'published', 'failed', 'superseded')),
          stage text NOT NULL DEFAULT 'queued'
            CHECK (stage IN ('queued', 'scanning', 'parsing', 'chunking', 'embedding', 'indexing', 'done')),
          completeness text NOT NULL DEFAULT 'complete' CHECK (completeness IN ('complete', 'partial')),
          parser text,
          error_code text,
          error_detail text,
          chunk_count int NOT NULL DEFAULT 0,
          embedding_profile text,
          created_at timestamptz NOT NULL DEFAULT now(),
          published_at timestamptz,
          UNIQUE (tenant_id, id),
          UNIQUE (source_id, revision_no),
          FOREIGN KEY (tenant_id, source_id) REFERENCES knowledge_sources (tenant_id, id)
        );

        CREATE TABLE knowledge_chunks (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL,
          source_id uuid NOT NULL,
          revision_id uuid NOT NULL,
          ordinal int NOT NULL,
          chunk_key text NOT NULL,
          text text NOT NULL,
          heading_path text NOT NULL DEFAULT '',
          locator jsonb NOT NULL DEFAULT '{}'::jsonb,
          locator_quality text NOT NULL DEFAULT 'exact' CHECK (locator_quality IN ('exact', 'approximate', 'none')),
          content_flags text[] NOT NULL DEFAULT '{}',
          tsv tsvector NOT NULL,
          embedding real[],
          embedding_profile text,
          created_at timestamptz NOT NULL DEFAULT now(),
          FOREIGN KEY (tenant_id, revision_id) REFERENCES knowledge_revisions (tenant_id, id)
        );
        CREATE INDEX knowledge_chunks_tsv ON knowledge_chunks USING gin (tsv);
        CREATE INDEX knowledge_chunks_revision ON knowledge_chunks (revision_id, ordinal);
        CREATE INDEX knowledge_chunks_key ON knowledge_chunks (source_id, chunk_key);

        -- Passages returned to an Attempt: citations in its answer must refer to these (Part 7 §9).
        CREATE TABLE retrieval_logs (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          task_id uuid,
          attempt_id uuid,
          membership_id uuid NOT NULL,
          query text NOT NULL,
          chunk_ids uuid[] NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX retrieval_logs_task ON retrieval_logs (tenant_id, task_id);

        ALTER TABLE task_messages ADD COLUMN citations jsonb NOT NULL DEFAULT '[]'::jsonb;

        -- Cosine similarity on real[] embeddings (no extension needed; pgvector replaces it when installed).
        CREATE FUNCTION workx_cosine(a real[], b real[]) RETURNS double precision
          LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
          SELECT CASE WHEN na = 0 OR nb = 0 THEN 0 ELSE dot / (na * nb) END FROM (
            SELECT sum(x * y) AS dot, sqrt(sum(x * x)) AS na, sqrt(sum(y * y)) AS nb
            FROM unnest(a, b) AS t(x, y)
          ) s
        $$;
        GRANT EXECUTE ON FUNCTION workx_cosine(real[], real[]) TO workx_app;
        """
    )
    op.execute(
        "CREATE TRIGGER knowledge_sources_touch BEFORE UPDATE ON knowledge_sources FOR EACH ROW EXECUTE FUNCTION workx_touch_updated_at()"
    )
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} USING (tenant_id = workx_tenant_id()) "
            "WITH CHECK (tenant_id = workx_tenant_id())"
        )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS workx_cosine(real[], real[])")
    op.execute("ALTER TABLE task_messages DROP COLUMN IF EXISTS citations")
    op.execute("DROP TABLE IF EXISTS " + ", ".join(reversed(TABLES)) + " CASCADE")
