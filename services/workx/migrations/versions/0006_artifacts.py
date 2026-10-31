"""Artifacts: object-stored file versions, validation results, completeness (Part 4 §12, Part 11).

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-31
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE file_versions
          ADD COLUMN media_type text,
          ADD COLUMN completeness text NOT NULL DEFAULT 'complete' CHECK (completeness IN ('complete', 'partial')),
          ADD COLUMN source_attempt_id uuid,
          ADD COLUMN validation jsonb NOT NULL DEFAULT '{}'::jsonb;
        -- Retries of the same Attempt output never create duplicate versions (Part 4 §10.3).
        CREATE UNIQUE INDEX file_versions_dedupe ON file_versions (file_id, sha256) WHERE sha256 IS NOT NULL;
        CREATE INDEX files_by_task_name ON files (tenant_id, source_task_id, name) WHERE deleted_at IS NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS files_by_task_name;
        DROP INDEX IF EXISTS file_versions_dedupe;
        ALTER TABLE file_versions DROP COLUMN validation, DROP COLUMN source_attempt_id, DROP COLUMN completeness,
          DROP COLUMN media_type;
        """
    )
