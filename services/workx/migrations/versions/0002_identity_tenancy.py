"""Identity, tenancy, invitations, idempotency, outbox and audit (Parts 3 and 11 §2.1).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-31
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE users (
          id uuid PRIMARY KEY,
          idp_issuer text NOT NULL,
          idp_subject text NOT NULL,
          primary_email citext NOT NULL,
          email_verified_at timestamptz NOT NULL,
          display_name text NOT NULL,
          locale text NOT NULL DEFAULT 'en',
          status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled', 'deleted')),
          notifications_enabled boolean NOT NULL DEFAULT true,
          last_tenant_id uuid,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (idp_issuer, idp_subject),
          UNIQUE (primary_email)
        );

        CREATE TABLE login_sessions (
          id uuid PRIMARY KEY,
          user_id uuid NOT NULL REFERENCES users (id),
          session_hash bytea NOT NULL UNIQUE,
          auth_strength text NOT NULL DEFAULT 'password',
          idp_sid text,
          id_token_hint text,
          created_at timestamptz NOT NULL DEFAULT now(),
          last_seen_at timestamptz NOT NULL DEFAULT now(),
          expires_at timestamptz NOT NULL,
          absolute_expires_at timestamptz NOT NULL,
          revoked_at timestamptz,
          ip_hash bytea,
          user_agent text
        );
        CREATE INDEX login_sessions_user ON login_sessions (user_id) WHERE revoked_at IS NULL;

        -- Single-use OIDC authorization transactions (state, PKCE, nonce), bound to the browser.
        CREATE TABLE oidc_login_transactions (
          id uuid PRIMARY KEY,
          state_hash bytea NOT NULL UNIQUE,
          browser_binding_hash bytea NOT NULL,
          code_verifier text NOT NULL,
          nonce text NOT NULL,
          intent text NOT NULL CHECK (intent IN ('login', 'signup')),
          return_to text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          expires_at timestamptz NOT NULL,
          consumed_at timestamptz
        );

        CREATE TABLE tenants (
          id uuid PRIMARY KEY,
          slug text NOT NULL UNIQUE,
          type text NOT NULL CHECK (type IN ('personal', 'organization')),
          name text NOT NULL,
          owner_user_id uuid NOT NULL REFERENCES users (id),
          status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'pending_deletion', 'deleted')),
          plan_id text NOT NULL DEFAULT 'free',
          region_cell text NOT NULL DEFAULT 'default',
          authz_epoch bigint NOT NULL DEFAULT 1,
          settings jsonb NOT NULL DEFAULT '{}'::jsonb,
          row_version bigint NOT NULL DEFAULT 1,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE UNIQUE INDEX tenants_one_personal_per_user ON tenants (owner_user_id) WHERE type = 'personal';

        CREATE TABLE departments (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          name text NOT NULL,
          parent_id uuid,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, id),
          FOREIGN KEY (tenant_id, parent_id) REFERENCES departments (tenant_id, id)
        );

        CREATE TABLE memberships (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          user_id uuid NOT NULL REFERENCES users (id),
          role text NOT NULL CHECK (role IN ('owner', 'admin', 'member')),
          status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'deactivated', 'removed')),
          display_name text,
          department_id uuid,
          preferences jsonb NOT NULL DEFAULT '{}'::jsonb,
          authz_epoch bigint NOT NULL DEFAULT 1,
          row_version bigint NOT NULL DEFAULT 1,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, user_id),
          UNIQUE (tenant_id, id),
          FOREIGN KEY (tenant_id, department_id) REFERENCES departments (tenant_id, id)
        );
        CREATE INDEX memberships_user ON memberships (user_id) WHERE status = 'active';

        CREATE TABLE invitations (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          email_normalized citext NOT NULL,
          role text NOT NULL CHECK (role IN ('admin', 'member')),
          token_digest bytea NOT NULL UNIQUE,
          status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'cancelled', 'expired')),
          expires_at timestamptz NOT NULL,
          invited_by_membership_id uuid NOT NULL,
          consumed_by_user_id uuid REFERENCES users (id),
          accepted_membership_id uuid,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, id),
          FOREIGN KEY (tenant_id, invited_by_membership_id) REFERENCES memberships (tenant_id, id)
        );
        CREATE UNIQUE INDEX invitations_one_pending ON invitations (tenant_id, email_normalized) WHERE status = 'pending';

        -- Idempotency-Key store (Part 11 §3): replay returns the original response.
        CREATE TABLE idempotency_keys (
          scope text NOT NULL,
          principal_id uuid NOT NULL,
          route text NOT NULL,
          key text NOT NULL,
          request_hash bytea NOT NULL,
          status_code int,
          response jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          expires_at timestamptz NOT NULL,
          PRIMARY KEY (scope, principal_id, route, key)
        );

        -- Transactional outbox: written in the same transaction as the state change.
        CREATE TABLE outbox_events (
          id uuid PRIMARY KEY,
          tenant_id uuid,
          topic text NOT NULL,
          payload jsonb NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          dispatched_at timestamptz
        );
        CREATE INDEX outbox_pending ON outbox_events (created_at) WHERE dispatched_at IS NULL;

        CREATE TABLE audit_events (
          id uuid PRIMARY KEY,
          tenant_id uuid,
          actor_user_id uuid,
          actor_membership_id uuid,
          action text NOT NULL,
          target_type text,
          target_id uuid,
          data jsonb NOT NULL DEFAULT '{}'::jsonb,
          request_id text,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX audit_events_tenant ON audit_events (tenant_id, created_at DESC);
        """
    )
    for table in ("users", "tenants", "departments", "memberships", "invitations"):
        op.execute(
            f"CREATE TRIGGER {table}_touch BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION workx_touch_updated_at()"
        )
    # Audit is append-only for the runtime role.
    op.execute("REVOKE UPDATE, DELETE ON audit_events FROM workx_app")
    op.execute(
        """
        -- A personal tenant has exactly one membership: its owner. (A duplicate row for the same user is left
        -- to the unique constraint, so INSERT ... ON CONFLICT DO NOTHING stays a no-op.)
        CREATE FUNCTION workx_personal_single_member() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF (SELECT type FROM tenants WHERE id = NEW.tenant_id) = 'personal' THEN
            IF NEW.role <> 'owner'
               OR NEW.user_id <> (SELECT owner_user_id FROM tenants WHERE id = NEW.tenant_id)
               OR EXISTS (
                 SELECT 1 FROM memberships WHERE tenant_id = NEW.tenant_id AND id <> NEW.id AND user_id <> NEW.user_id
               ) THEN
              RAISE EXCEPTION 'personal tenant allows only its owner' USING ERRCODE = 'check_violation';
            END IF;
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER memberships_personal_single BEFORE INSERT OR UPDATE ON memberships
          FOR EACH ROW EXECUTE FUNCTION workx_personal_single_member();

        -- Every active organization keeps at least one active owner (checked at commit).
        CREATE FUNCTION workx_org_keeps_owner() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE t uuid := COALESCE(NEW.tenant_id, OLD.tenant_id);
        BEGIN
          IF (SELECT type FROM tenants WHERE id = t) = 'organization'
             AND (SELECT status FROM tenants WHERE id = t) IN ('active', 'suspended')
             AND NOT EXISTS (SELECT 1 FROM memberships WHERE tenant_id = t AND role = 'owner' AND status = 'active') THEN
            RAISE EXCEPTION 'organization must keep an active owner' USING ERRCODE = 'check_violation';
          END IF;
          RETURN NULL;
        END $$;
        CREATE CONSTRAINT TRIGGER memberships_org_owner AFTER INSERT OR UPDATE OR DELETE ON memberships
          DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION workx_org_keeps_owner();

        -- Departments exist only in organizations.
        CREATE FUNCTION workx_departments_org_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF (SELECT type FROM tenants WHERE id = NEW.tenant_id) <> 'organization' THEN
            RAISE EXCEPTION 'departments require an organization' USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER departments_org_only BEFORE INSERT OR UPDATE ON departments
          FOR EACH ROW EXECUTE FUNCTION workx_departments_org_only();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS audit_events, outbox_events, idempotency_keys, invitations, memberships, departments,
          tenants, oidc_login_transactions, login_sessions, users CASCADE;
        DROP FUNCTION IF EXISTS workx_departments_org_only(), workx_org_keeps_owner(), workx_personal_single_member();
        """
    )
