"""Connector knowledge sync (R2, Part 7 §6): knowledge sources fed by a connection instead of a Library file.

A connector source belongs to the connection's owner and is private to them (a member's own account); each
sync builds a new revision from the documents the service returns, so documents deleted upstream disappear
when the revision is published.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-31
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE knowledge_sources ALTER COLUMN file_id DROP NOT NULL;
        ALTER TABLE knowledge_sources ADD COLUMN kind text NOT NULL DEFAULT 'file' CHECK (kind IN ('file', 'connector'));
        ALTER TABLE knowledge_sources ADD COLUMN connection_id uuid;
        ALTER TABLE knowledge_sources ADD COLUMN last_synced_at timestamptz;
        ALTER TABLE knowledge_sources ADD CONSTRAINT knowledge_sources_origin CHECK (
          (kind = 'file' AND file_id IS NOT NULL) OR (kind = 'connector' AND connection_id IS NOT NULL));
        ALTER TABLE knowledge_sources ADD CONSTRAINT knowledge_sources_connection_fk
          FOREIGN KEY (tenant_id, connection_id) REFERENCES connections (tenant_id, id);
        CREATE UNIQUE INDEX knowledge_sources_one_per_connection ON knowledge_sources (tenant_id, connection_id)
          WHERE deleted_at IS NULL AND connection_id IS NOT NULL;
        ALTER TABLE knowledge_revisions ALTER COLUMN file_version_id DROP NOT NULL;

        -- Connector sources due for a re-sync (ids only), found across tenants by the scheduler tick.
        CREATE FUNCTION workx_due_knowledge_syncs(p_before timestamptz, p_limit int)
          RETURNS TABLE (tenant_id uuid, id uuid)
          LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
          SELECT s.tenant_id, s.id FROM knowledge_sources s
          WHERE s.kind = 'connector' AND s.deleted_at IS NULL AND coalesce(s.last_synced_at, '-infinity') < p_before
            AND NOT EXISTS (SELECT 1 FROM knowledge_revisions r WHERE r.source_id = s.id AND r.state = 'building')
          ORDER BY s.last_synced_at NULLS FIRST LIMIT p_limit
        $$;
        GRANT EXECUTE ON FUNCTION workx_due_knowledge_syncs(timestamptz, int) TO workx_app;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP FUNCTION IF EXISTS workx_due_knowledge_syncs(timestamptz, int);
        DELETE FROM knowledge_chunks WHERE source_id IN (SELECT id FROM knowledge_sources WHERE kind = 'connector');
        DELETE FROM knowledge_revisions WHERE source_id IN (SELECT id FROM knowledge_sources WHERE kind = 'connector');
        DELETE FROM knowledge_sources WHERE kind = 'connector';
        DROP INDEX IF EXISTS knowledge_sources_one_per_connection;
        ALTER TABLE knowledge_sources DROP CONSTRAINT knowledge_sources_connection_fk,
          DROP CONSTRAINT knowledge_sources_origin, DROP COLUMN last_synced_at, DROP COLUMN connection_id,
          DROP COLUMN kind, ALTER COLUMN file_id SET NOT NULL;
        ALTER TABLE knowledge_revisions ALTER COLUMN file_version_id SET NOT NULL;
        """
    )
