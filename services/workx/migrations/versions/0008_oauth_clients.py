"""OAuth client registrations (P-07b): installation-level credentials, the client used per transaction, and the
connectors a workmate needs.

An OAuth connector's client secret (pre-registered apps such as Feishu, or a secret returned by dynamic client
registration) belongs to the workspace's installation, not to one member's connection. ``credentials`` rows
therefore attach either to a connection or to an installation (``installation_connector_id``), never both.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-31
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE credentials ALTER COLUMN connection_id DROP NOT NULL;
        ALTER TABLE credentials ADD COLUMN installation_connector_id text;
        ALTER TABLE credentials ADD CONSTRAINT credentials_one_owner
          CHECK ((connection_id IS NULL) <> (installation_connector_id IS NULL));
        ALTER TABLE credentials ADD CONSTRAINT credentials_installation_fk
          FOREIGN KEY (tenant_id, installation_connector_id)
          REFERENCES connector_installations (tenant_id, connector_id);
        CREATE UNIQUE INDEX credentials_installation_kind ON credentials (tenant_id, installation_connector_id, kind)
          WHERE installation_connector_id IS NOT NULL;

        ALTER TABLE oauth_transactions ADD COLUMN client_id text NOT NULL DEFAULT '';

        -- Connectors a workmate needs (published into agent_versions.tool_refs; drives the needs_auth preflight).
        ALTER TABLE agents ADD COLUMN connectors text[] NOT NULL DEFAULT '{}';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE agents DROP COLUMN connectors;
        ALTER TABLE oauth_transactions DROP COLUMN client_id;
        DELETE FROM secret_versions WHERE credential_id IN
          (SELECT id FROM credentials WHERE installation_connector_id IS NOT NULL);
        DELETE FROM credentials WHERE installation_connector_id IS NOT NULL;
        DROP INDEX credentials_installation_kind;
        ALTER TABLE credentials DROP CONSTRAINT credentials_installation_fk;
        ALTER TABLE credentials DROP CONSTRAINT credentials_one_owner;
        ALTER TABLE credentials DROP COLUMN installation_connector_id;
        ALTER TABLE credentials ALTER COLUMN connection_id SET NOT NULL;
        """
    )
