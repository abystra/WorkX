"""Credentials and connections (Part 6 §2-§3): installations, connections, usage policies, credentials,
secret versions (envelope-encrypted), OAuth transactions, authorization requests.

Secret material is readable only by ``workx_broker`` (the broker and gateway processes). ``workx_app`` (API,
worker, orchestrator) can see connection metadata but has no privilege on ``secret_versions`` or
``oauth_transactions`` at all.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-31
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

TABLES = (
    "connector_installations",
    "connections",
    "connection_usage_policies",
    "credentials",
    "secret_versions",
    "oauth_transactions",
    "authorization_requests",
)
SECRET_TABLES = ("secret_versions", "oauth_transactions")


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE connector_installations (
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          connector_id text NOT NULL,
          enabled boolean NOT NULL DEFAULT true,
          config jsonb NOT NULL DEFAULT '{}'::jsonb,
          allowed_tools text[],
          installed_by_membership_id uuid,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (tenant_id, connector_id)
        );

        CREATE TABLE connections (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          connector_id text NOT NULL,
          name text NOT NULL,
          owner_scope text NOT NULL CHECK (owner_scope IN ('member', 'tenant')),
          owner_membership_id uuid NOT NULL,
          status text NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'active', 'needs_auth', 'suspended', 'revoked', 'error')),
          external_account text,
          granted_scopes text[] NOT NULL DEFAULT '{}',
          authz_epoch bigint NOT NULL DEFAULT 1,
          last_used_at timestamptz,
          last_refresh_at timestamptz,
          last_error text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, id),
          FOREIGN KEY (tenant_id, owner_membership_id) REFERENCES memberships (tenant_id, id)
        );
        CREATE INDEX connections_owner ON connections (tenant_id, owner_membership_id) WHERE status <> 'revoked';

        -- Who may use an organization-shared connection, and which tools (Part 6 §2 rule 3).
        CREATE TABLE connection_usage_policies (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL,
          connection_id uuid NOT NULL,
          principal_type text NOT NULL CHECK (principal_type IN ('role', 'membership', 'project', 'agent', 'tenant')),
          principal_ref text NOT NULL,
          allowed_tools text[] NOT NULL DEFAULT '{}',
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (connection_id, principal_type, principal_ref),
          FOREIGN KEY (tenant_id, connection_id) REFERENCES connections (tenant_id, id)
        );

        CREATE TABLE credentials (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL,
          connection_id uuid NOT NULL,
          usage_class text NOT NULL CHECK (usage_class IN ('tool', 'channel', 'model', 'infrastructure')),
          kind text NOT NULL CHECK (kind IN ('api_key', 'oauth_refresh', 'oauth_access', 'app_secret')),
          active_version_id uuid,
          row_version bigint NOT NULL DEFAULT 1,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, id),
          UNIQUE (connection_id, kind),
          FOREIGN KEY (tenant_id, connection_id) REFERENCES connections (tenant_id, id)
        );

        CREATE TABLE secret_versions (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL,
          credential_id uuid NOT NULL,
          version_no int NOT NULL,
          ciphertext bytea NOT NULL,
          nonce bytea NOT NULL,
          wrapped_dek bytea NOT NULL,
          key_ref text NOT NULL,
          key_version int NOT NULL,
          fingerprint bytea NOT NULL,
          not_after timestamptz,
          state text NOT NULL CHECK (state IN ('pending', 'active', 'retiring', 'destroyed')),
          created_at timestamptz NOT NULL DEFAULT now(),
          retired_at timestamptz,
          UNIQUE (credential_id, version_no),
          FOREIGN KEY (tenant_id, credential_id) REFERENCES credentials (tenant_id, id)
        );

        CREATE TABLE oauth_transactions (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          connector_id text NOT NULL,
          connection_id uuid,
          owner_scope text NOT NULL,
          initiator_membership_id uuid NOT NULL,
          state_hash bytea NOT NULL UNIQUE,
          verifier_ciphertext bytea NOT NULL,
          verifier_nonce bytea NOT NULL,
          verifier_wrapped_dek bytea NOT NULL,
          key_ref text NOT NULL,
          key_version int NOT NULL,
          redirect_uri text NOT NULL,
          return_to text NOT NULL,
          scopes text[] NOT NULL,
          expires_at timestamptz NOT NULL,
          consumed_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE authorization_requests (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          task_id uuid,
          attempt_id uuid,
          connector_id text NOT NULL,
          target_membership_id uuid NOT NULL,
          status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'cancelled')),
          created_at timestamptz NOT NULL DEFAULT now(),
          completed_at timestamptz,
          UNIQUE (tenant_id, id)
        );
        CREATE INDEX authorization_requests_open ON authorization_requests (tenant_id, target_membership_id, connector_id)
          WHERE status = 'pending';
        """
    )
    for table in ("connector_installations", "connections", "credentials"):
        op.execute(
            f"CREATE TRIGGER {table}_touch BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION workx_touch_updated_at()"
        )
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} USING (tenant_id = workx_tenant_id()) "
            "WITH CHECK (tenant_id = workx_tenant_id())"
        )
    for table in SECRET_TABLES:
        op.execute(f"REVOKE ALL ON {table} FROM workx_app")
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO workx_broker")
    op.execute(
        """
        -- OAuth callbacks arrive with only a state value: resolve it to its tenant (broker only).
        CREATE FUNCTION workx_oauth_state_tenant(p_hash bytea) RETURNS uuid
          LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
          SELECT tenant_id FROM oauth_transactions WHERE state_hash = p_hash
        $$;
        REVOKE EXECUTE ON FUNCTION workx_oauth_state_tenant(bytea) FROM PUBLIC, workx_app;
        GRANT EXECUTE ON FUNCTION workx_oauth_state_tenant(bytea) TO workx_broker;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS workx_oauth_state_tenant(bytea)")
    op.execute("DROP TABLE IF EXISTS " + ", ".join(reversed(TABLES)) + " CASCADE")
