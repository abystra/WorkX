"""Baseline: extensions, runtime-role privileges, RLS context helpers.

Revision ID: 0001
Revises:
Create Date: 2026-10-31
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    # Only the owner creates objects; the runtime role reads and writes rows, nothing else.
    op.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    op.execute("GRANT USAGE ON SCHEMA public TO workx_app")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO workx_app")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO workx_app")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO workx_app")
    # RLS context, set per transaction by workx.core.db.set_context. Empty means "no tenant".
    op.execute(
        """
        CREATE FUNCTION workx_tenant_id() RETURNS uuid LANGUAGE sql STABLE AS $$
          SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION workx_principal_id() RETURNS uuid LANGUAGE sql STABLE AS $$
          SELECT NULLIF(current_setting('app.principal_id', true), '')::uuid
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION workx_touch_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          NEW.updated_at := now();
          RETURN NEW;
        END $$
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS workx_touch_updated_at()")
    op.execute("DROP FUNCTION IF EXISTS workx_principal_id()")
    op.execute("DROP FUNCTION IF EXISTS workx_tenant_id()")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM workx_app")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM workx_app")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM workx_app"
    )
    op.execute("REVOKE USAGE ON SCHEMA public FROM workx_app")
