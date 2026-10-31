"""Authorization grants, service principals, row-level security, job queue, usage events (Parts 3, 10, 11).

RLS model for the runtime role ``workx_app`` (tables are owned by ``workx_owner``, which is exempt because
policies are not FORCEd; that is what lets the SECURITY DEFINER functions below do narrow, named lookups):

* tenant tables: rows of ``app.tenant_id`` only; the API sets it after verifying an active membership
* the user's own rows (memberships, sessions, idempotency keys) through ``app.principal_id``
* cross-tenant lookups only through the definer functions in this file
* ``outbox_events`` and ``jobs`` carry IDs only and are read across tenants by workers; consumers reload the
  referenced rows under that tenant's context (Part 3 §3)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-31
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TENANT_TABLES = ("departments", "invitations", "resource_grants", "service_principals", "usage_events")


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE service_principals (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          kind text NOT NULL CHECK (kind IN ('channel_binding', 'automation', 'system')),
          ref_id uuid,
          status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
          allowed_actions text[] NOT NULL DEFAULT '{}',
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, id)
        );

        CREATE TABLE resource_grants (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          resource_type text NOT NULL,
          resource_id uuid NOT NULL,
          principal_type text NOT NULL CHECK (principal_type IN ('membership', 'project', 'tenant', 'service_principal')),
          principal_id uuid NOT NULL,
          actions text[] NOT NULL CHECK (actions <@ ARRAY['read','use','comment','edit','share','delete','export','approve']::text[]),
          granted_by_membership_id uuid,
          expires_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, resource_type, resource_id, principal_type, principal_id)
        );
        CREATE INDEX resource_grants_principal ON resource_grants (tenant_id, principal_type, principal_id);

        CREATE TABLE jobs (
          id uuid PRIMARY KEY,
          tenant_id uuid,
          kind text NOT NULL,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          dedupe_key text UNIQUE,
          status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'succeeded', 'dead')),
          attempts int NOT NULL DEFAULT 0,
          max_attempts int NOT NULL DEFAULT 8,
          run_after timestamptz NOT NULL DEFAULT now(),
          locked_by text,
          locked_until timestamptz,
          last_error text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          finished_at timestamptz
        );
        CREATE INDEX jobs_ready ON jobs (run_after) WHERE status = 'queued';
        CREATE INDEX jobs_leased ON jobs (locked_until) WHERE status = 'running';
        CREATE TRIGGER jobs_touch BEFORE UPDATE ON jobs FOR EACH ROW EXECUTE FUNCTION workx_touch_updated_at();

        CREATE TABLE usage_events (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          kind text NOT NULL CHECK (kind IN ('model_tokens', 'sandbox_seconds', 'tool_call', 'embedding_tokens', 'storage_bytes')),
          quantity numeric NOT NULL CHECK (quantity >= 0),
          unit text NOT NULL,
          task_id uuid,
          attempt_id uuid,
          membership_id uuid,
          source_event_id text NOT NULL,
          data jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, kind, source_event_id)
        );
        CREATE INDEX usage_events_tenant ON usage_events (tenant_id, created_at);
        """
    )

    # Integrity triggers must see every row regardless of RLS: run them as the owner.
    for function in ("workx_personal_single_member()", "workx_org_keeps_owner()", "workx_departments_org_only()"):
        op.execute(f"ALTER FUNCTION {function} SECURITY DEFINER SET search_path = public")

    # --- Named cross-tenant lookups (SECURITY DEFINER, owner-run, return only what the caller needs) ---
    op.execute(
        """
        CREATE FUNCTION workx_session_by_hash(p_hash bytea) RETURNS TABLE (session_id uuid, user_id uuid)
          LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
          SELECT id, user_id FROM login_sessions WHERE session_hash = p_hash
        $$;

        CREATE FUNCTION workx_user_for_login(p_issuer text, p_subject text, p_email citext)
          RETURNS TABLE (user_id uuid, by_subject boolean)
          LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
          SELECT id, true FROM users WHERE idp_issuer = p_issuer AND idp_subject = p_subject
          UNION ALL
          SELECT id, false FROM users WHERE primary_email = p_email
            AND NOT (idp_issuer = p_issuer AND idp_subject = p_subject)
        $$;

        CREATE FUNCTION workx_invitation_tenant(p_digest bytea) RETURNS uuid
          LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
          SELECT tenant_id FROM invitations WHERE token_digest = p_digest
        $$;

        CREATE FUNCTION workx_is_active_member(p_tenant uuid, p_user uuid) RETURNS boolean
          LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
          SELECT EXISTS (SELECT 1 FROM memberships WHERE tenant_id = p_tenant AND user_id = p_user AND status = 'active')
        $$;

        -- Reconciler: expire overdue invitations in every tenant (status change only, nothing returned).
        CREATE FUNCTION workx_expire_invitations() RETURNS integer
          LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public AS $$
          WITH expired AS (
            UPDATE invitations SET status = 'expired' WHERE status = 'pending' AND expires_at <= now() RETURNING 1
          ) SELECT count(*)::int FROM expired
        $$;

        CREATE FUNCTION workx_slug_taken(p_slug text) RETURNS boolean
          LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
          SELECT EXISTS (SELECT 1 FROM tenants WHERE slug = p_slug)
        $$;
        """
    )
    # SQL mirror of workx.domains.authz.policy.allowed_actions, for SQL-side filtering (retrieval, Part 7).
    # Runs as the invoker, so RLS on resource_grants still confines it to the current tenant.
    op.execute(
        """
        CREATE FUNCTION workx_member_projects(p_tenant uuid, p_membership uuid) RETURNS TABLE (project_id uuid)
          LANGUAGE sql STABLE AS $$ SELECT NULL::uuid WHERE false $$;  -- replaced when projects exist (0004)

        CREATE FUNCTION workx_can(
          p_tenant uuid, p_membership uuid, p_owner uuid, p_type text, p_resource uuid, p_action text
        ) RETURNS boolean LANGUAGE sql STABLE AS $$
          SELECT COALESCE(p_owner = p_membership, false) OR EXISTS (
            SELECT 1 FROM resource_grants g
            WHERE g.tenant_id = p_tenant AND g.resource_type = p_type AND g.resource_id = p_resource
              AND p_action = ANY (g.actions) AND (g.expires_at IS NULL OR g.expires_at > now())
              AND ((g.principal_type = 'membership' AND g.principal_id = p_membership)
                OR (g.principal_type = 'tenant' AND g.principal_id = p_tenant)
                OR (g.principal_type = 'project'
                    AND g.principal_id IN (SELECT project_id FROM workx_member_projects(p_tenant, p_membership))))
          )
        $$;
        """
    )
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
    op.execute("GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO workx_app")

    # --- Policies ---
    for table in (
        *TENANT_TABLES,
        "users",
        "login_sessions",
        "tenants",
        "memberships",
        "audit_events",
        "idempotency_keys",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    for table in TENANT_TABLES:
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
              USING (tenant_id = workx_tenant_id()) WITH CHECK (tenant_id = workx_tenant_id())
            """
        )
    op.execute(
        """
        -- Users: yourself, or people who share the current tenant. Sign-up inserts happen before any context.
        CREATE POLICY users_read ON users FOR SELECT USING (
          id = workx_principal_id()
          OR EXISTS (SELECT 1 FROM memberships m WHERE m.user_id = users.id AND m.tenant_id = workx_tenant_id())
        );
        CREATE POLICY users_signup ON users FOR INSERT WITH CHECK (true);
        CREATE POLICY users_update_self ON users FOR UPDATE USING (id = workx_principal_id());

        CREATE POLICY sessions_own ON login_sessions
          USING (user_id = workx_principal_id()) WITH CHECK (user_id = workx_principal_id());

        CREATE POLICY tenants_read ON tenants FOR SELECT USING (
          id = workx_tenant_id() OR owner_user_id = workx_principal_id()
          OR workx_is_active_member(id, workx_principal_id())
        );
        CREATE POLICY tenants_create ON tenants FOR INSERT WITH CHECK (owner_user_id = workx_principal_id());
        CREATE POLICY tenants_update ON tenants FOR UPDATE USING (id = workx_tenant_id());

        CREATE POLICY memberships_read ON memberships FOR SELECT USING (
          tenant_id = workx_tenant_id() OR user_id = workx_principal_id()
        );
        -- Insert into the current tenant, or create your own owner membership in a tenant you own.
        CREATE POLICY memberships_insert ON memberships FOR INSERT WITH CHECK (
          tenant_id = workx_tenant_id()
          OR (user_id = workx_principal_id() AND role = 'owner'
              AND EXISTS (SELECT 1 FROM tenants t WHERE t.id = tenant_id AND t.owner_user_id = workx_principal_id()))
        );
        CREATE POLICY memberships_update ON memberships FOR UPDATE USING (tenant_id = workx_tenant_id());
        CREATE POLICY memberships_delete ON memberships FOR DELETE USING (tenant_id = workx_tenant_id());

        CREATE POLICY audit_read ON audit_events FOR SELECT USING (tenant_id = workx_tenant_id());
        CREATE POLICY audit_write ON audit_events FOR INSERT WITH CHECK (tenant_id IS NULL OR tenant_id = workx_tenant_id());

        CREATE POLICY idempotency_own ON idempotency_keys
          USING (principal_id = workx_principal_id()) WITH CHECK (principal_id = workx_principal_id());
        """
    )
    op.execute("REVOKE UPDATE, DELETE ON usage_events FROM workx_app")


def downgrade() -> None:
    for table in (
        *TENANT_TABLES,
        "users",
        "login_sessions",
        "tenants",
        "memberships",
        "audit_events",
        "idempotency_keys",
    ):
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute(
        """
        DROP POLICY IF EXISTS users_read ON users; DROP POLICY IF EXISTS users_signup ON users;
        DROP POLICY IF EXISTS users_update_self ON users; DROP POLICY IF EXISTS sessions_own ON login_sessions;
        DROP POLICY IF EXISTS tenants_read ON tenants; DROP POLICY IF EXISTS tenants_create ON tenants;
        DROP POLICY IF EXISTS tenants_update ON tenants; DROP POLICY IF EXISTS memberships_read ON memberships;
        DROP POLICY IF EXISTS memberships_insert ON memberships; DROP POLICY IF EXISTS memberships_update ON memberships;
        DROP POLICY IF EXISTS memberships_delete ON memberships; DROP POLICY IF EXISTS audit_read ON audit_events;
        DROP POLICY IF EXISTS audit_write ON audit_events; DROP POLICY IF EXISTS idempotency_own ON idempotency_keys;
        DROP FUNCTION IF EXISTS workx_session_by_hash(bytea), workx_user_for_login(text, text, citext),
          workx_invitation_tenant(bytea), workx_is_active_member(uuid, uuid), workx_slug_taken(text),
          workx_can(uuid, uuid, uuid, text, uuid, text), workx_member_projects(uuid, uuid),
          workx_expire_invitations();
        DROP TABLE IF EXISTS usage_events, jobs, resource_grants, service_principals CASCADE;
        """
    )
    for function in ("workx_personal_single_member()", "workx_org_keeps_owner()", "workx_departments_org_only()"):
        op.execute(f"ALTER FUNCTION {function} SECURITY INVOKER")
