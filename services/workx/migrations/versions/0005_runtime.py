"""Agent runtime: attempts with fencing and leases, task events, attempt tickets, tool-operation ledger,
approvals, budgets (Part 4 §3, §7, §10; Part 6 §5).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-31
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TABLES = ("task_attempts", "task_events", "credential_leases", "tool_operations", "approvals", "tenant_budgets")


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE task_attempts (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          task_id uuid NOT NULL,
          attempt_no int NOT NULL,
          fencing_token bigint NOT NULL,
          status text NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'provisioning', 'running', 'draining', 'ended')),
          end_reason text,
          sandbox_provider text,
          sandbox_ref text,
          lease_owner text,
          lease_expires_at timestamptz,
          started_at timestamptz,
          ended_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, id),
          UNIQUE (task_id, attempt_no),
          FOREIGN KEY (tenant_id, task_id) REFERENCES tasks (tenant_id, id)
        );
        -- Exactly one live Attempt per Task (Part 4 §3).
        CREATE UNIQUE INDEX task_attempts_one_live ON task_attempts (task_id) WHERE status <> 'ended';
        CREATE INDEX task_attempts_lease ON task_attempts (lease_expires_at) WHERE status <> 'ended';

        CREATE TABLE task_events (
          tenant_id uuid NOT NULL,
          task_id uuid NOT NULL,
          seq bigint NOT NULL,
          attempt_id uuid,
          runner_event_id text,
          type text NOT NULL,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (task_id, seq),
          UNIQUE (attempt_id, runner_event_id),
          FOREIGN KEY (tenant_id, task_id) REFERENCES tasks (tenant_id, id)
        );

        -- Attempt tickets (model / tool). Only SHA-256 digests are stored (Part 6 §5).
        CREATE TABLE credential_leases (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          task_id uuid NOT NULL,
          attempt_id uuid NOT NULL,
          kind text NOT NULL CHECK (kind IN ('model', 'tool')),
          token_hash bytea NOT NULL UNIQUE,
          scopes jsonb NOT NULL DEFAULT '{}'::jsonb,
          expires_at timestamptz NOT NULL,
          revoked_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          FOREIGN KEY (tenant_id, attempt_id) REFERENCES task_attempts (tenant_id, id)
        );
        CREATE INDEX credential_leases_attempt ON credential_leases (attempt_id) WHERE revoked_at IS NULL;

        -- Side-effect ledger: one row per logical operation per Task (Part 4 §10.4).
        CREATE TABLE tool_operations (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          task_id uuid NOT NULL,
          attempt_id uuid NOT NULL,
          tool text NOT NULL,
          effect text NOT NULL CHECK (effect IN ('read', 'write_idempotent', 'write_non_idempotent')),
          operation_key text NOT NULL,
          status text NOT NULL CHECK (status IN ('started', 'succeeded', 'failed', 'unknown')),
          result jsonb,
          error text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (task_id, operation_key)
        );

        CREATE TABLE approvals (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          task_id uuid NOT NULL,
          attempt_id uuid NOT NULL,
          tool text NOT NULL,
          args_digest text NOT NULL,
          summary text NOT NULL,
          status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'expired')),
          decided_by_membership_id uuid,
          decided_at timestamptz,
          expires_at timestamptz NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, id)
        );
        CREATE INDEX approvals_task ON approvals (task_id, status);

        CREATE TABLE tenant_budgets (
          tenant_id uuid PRIMARY KEY REFERENCES tenants (id),
          monthly_token_limit bigint,
          per_task_token_limit bigint,
          updated_at timestamptz NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE TRIGGER tool_operations_touch BEFORE UPDATE ON tool_operations FOR EACH ROW EXECUTE FUNCTION workx_touch_updated_at()"
    )
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} USING (tenant_id = workx_tenant_id()) "
            "WITH CHECK (tenant_id = workx_tenant_id())"
        )
    op.execute("REVOKE UPDATE, DELETE ON task_events FROM workx_app")
    op.execute(
        """
        -- Gateways receive only an opaque ticket: resolve it to its tenant, then work in that tenant's context.
        CREATE FUNCTION workx_lease_by_hash(p_hash bytea)
          RETURNS TABLE (lease_id uuid, tenant_id uuid, task_id uuid, attempt_id uuid, kind text, scopes jsonb,
                         expires_at timestamptz, revoked_at timestamptz)
          LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
          SELECT id, tenant_id, task_id, attempt_id, kind, scopes, expires_at, revoked_at
          FROM credential_leases WHERE token_hash = p_hash
        $$;

        -- Reconciler: live Attempts whose lease expired, in every tenant (ids only).
        CREATE FUNCTION workx_expired_attempts(p_limit int) RETURNS TABLE (attempt_id uuid, tenant_id uuid)
          LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
          SELECT id, tenant_id FROM task_attempts
          WHERE status <> 'ended' AND lease_expires_at < now()
          ORDER BY lease_expires_at LIMIT p_limit
        $$;

        -- Reconciler: ledger rows stuck in 'started' become 'unknown' (Part 4 §10.6).
        CREATE FUNCTION workx_mark_stale_operations(p_older_than interval) RETURNS integer
          LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public AS $$
          WITH stale AS (
            UPDATE tool_operations SET status = 'unknown', error = 'timed out without a result'
            WHERE status = 'started' AND updated_at < now() - p_older_than RETURNING 1
          ) SELECT count(*)::int FROM stale
        $$;
        GRANT EXECUTE ON FUNCTION workx_lease_by_hash(bytea), workx_expired_attempts(int),
          workx_mark_stale_operations(interval) TO workx_app;
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP FUNCTION IF EXISTS workx_lease_by_hash(bytea), workx_expired_attempts(int), workx_mark_stale_operations(interval)"
    )
    op.execute("DROP TABLE IF EXISTS " + ", ".join(reversed(TABLES)) + " CASCADE")
