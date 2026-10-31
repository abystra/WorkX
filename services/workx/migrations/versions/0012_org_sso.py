"""Organization SSO policy (R2, Part 3 §3): an organization may require that members signed in through its
identity provider (brokered by Keycloak); sessions record which provider authenticated them.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-31
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE tenants ADD COLUMN sso jsonb NOT NULL DEFAULT '{}'::jsonb;
        ALTER TABLE login_sessions ADD COLUMN idp_alias text;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE login_sessions DROP COLUMN idp_alias; ALTER TABLE tenants DROP COLUMN sso;")
