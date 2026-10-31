"""Automations scheduler (R2, P-10): one run per (automation, scheduled slot); due automations are found across
tenants by a narrow SECURITY DEFINER function (ids only), then processed in each tenant's context.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-31
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE automation_runs (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          automation_id uuid NOT NULL,
          slot_at timestamptz NOT NULL,
          status text NOT NULL CHECK (status IN ('created', 'skipped')),
          reason text,
          task_id uuid,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (automation_id, slot_at),
          FOREIGN KEY (tenant_id, automation_id) REFERENCES automations (tenant_id, id)
        );
        CREATE INDEX automations_due ON automations (next_run_at) WHERE enabled AND deleted_at IS NULL;
        ALTER TABLE automation_runs ENABLE ROW LEVEL SECURITY;
        CREATE POLICY tenant_isolation ON automation_runs
          USING (tenant_id = workx_tenant_id()) WITH CHECK (tenant_id = workx_tenant_id());

        CREATE FUNCTION workx_due_automations(p_now timestamptz, p_limit int)
          RETURNS TABLE (tenant_id uuid, id uuid)
          LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
          SELECT a.tenant_id, a.id FROM automations a JOIN tenants t ON t.id = a.tenant_id
          WHERE a.enabled AND a.deleted_at IS NULL AND a.next_run_at <= p_now AND t.status = 'active'
          ORDER BY a.next_run_at LIMIT p_limit
        $$;
        GRANT EXECUTE ON FUNCTION workx_due_automations(timestamptz, int) TO workx_app;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS workx_due_automations(timestamptz, int)")
    op.execute("DROP INDEX IF EXISTS automations_due")
    op.execute("DROP TABLE IF EXISTS automation_runs")
