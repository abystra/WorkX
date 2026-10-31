"""Workspace resources: projects, agents (+ immutable versions), files, sessions/tasks, automations, scenarios,
tenant event log (Parts 3, 4, 11 §2).

Every resource row carries ``tenant_id``, ``owner_membership_id`` and the ``visibility`` summary; grants in
``resource_grants`` are authoritative (Part 3 §1). All tables use the tenant RLS policy.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-31
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TABLES = (
    "projects",
    "project_members",
    "project_agents",
    "agents",
    "agent_versions",
    "files",
    "file_versions",
    "sessions",
    "tasks",
    "task_member_state",
    "task_messages",
    "automations",
    "scenarios",
    "tenant_events",
)
VISIBILITY = "visibility text NOT NULL DEFAULT 'private' CHECK (visibility IN ('private', 'selected', 'project', 'organization'))"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE projects (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          name text NOT NULL,
          description text NOT NULL DEFAULT '',
          color text,
          context_md text NOT NULL DEFAULT '',
          owner_membership_id uuid NOT NULL,
          {VISIBILITY},
          row_version bigint NOT NULL DEFAULT 1,
          deleted_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, id),
          FOREIGN KEY (tenant_id, owner_membership_id) REFERENCES memberships (tenant_id, id)
        );

        CREATE TABLE project_members (
          tenant_id uuid NOT NULL,
          project_id uuid NOT NULL,
          membership_id uuid NOT NULL,
          project_role text NOT NULL DEFAULT 'member' CHECK (project_role IN ('lead', 'member')),
          status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'removed')),
          created_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (tenant_id, project_id, membership_id),
          FOREIGN KEY (tenant_id, project_id) REFERENCES projects (tenant_id, id),
          FOREIGN KEY (tenant_id, membership_id) REFERENCES memberships (tenant_id, id)
        );

        CREATE TABLE agents (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          name text NOT NULL,
          description text NOT NULL DEFAULT '',
          tag text NOT NULL DEFAULT 'Personal',
          avatar int NOT NULL DEFAULT 0,
          owner_membership_id uuid NOT NULL,
          {VISIBILITY},
          -- Editable draft; publishing freezes it into agent_versions.
          instructions text NOT NULL DEFAULT '',
          context_md text NOT NULL DEFAULT '',
          model_tier text NOT NULL DEFAULT 'auto',
          skills text[] NOT NULL DEFAULT '{{}}',
          knowledge_source_ids uuid[] NOT NULL DEFAULT '{{}}',
          current_version_id uuid,
          row_version bigint NOT NULL DEFAULT 1,
          deleted_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, id),
          FOREIGN KEY (tenant_id, owner_membership_id) REFERENCES memberships (tenant_id, id)
        );

        CREATE TABLE agent_versions (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL,
          agent_id uuid NOT NULL,
          version_no int NOT NULL,
          instructions text NOT NULL,
          context_md text NOT NULL,
          model_tier text NOT NULL,
          skills text[] NOT NULL,
          tool_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
          knowledge_source_ids uuid[] NOT NULL,
          published_by_membership_id uuid NOT NULL,
          published_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, id),
          UNIQUE (agent_id, version_no),
          FOREIGN KEY (tenant_id, agent_id) REFERENCES agents (tenant_id, id)
        );

        CREATE TABLE project_agents (
          tenant_id uuid NOT NULL,
          project_id uuid NOT NULL,
          agent_id uuid NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (tenant_id, project_id, agent_id),
          FOREIGN KEY (tenant_id, project_id) REFERENCES projects (tenant_id, id),
          FOREIGN KEY (tenant_id, agent_id) REFERENCES agents (tenant_id, id)
        );

        CREATE TABLE files (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          name text NOT NULL,
          kind text NOT NULL DEFAULT 'doc' CHECK (kind IN ('doc', 'slides', 'sheet', 'pdf', 'image', 'other')),
          media_type text NOT NULL DEFAULT 'text/markdown',
          project_id uuid,
          source_task_id uuid,
          owner_membership_id uuid NOT NULL,
          {VISIBILITY},
          current_version_id uuid,
          deleted_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, id),
          FOREIGN KEY (tenant_id, owner_membership_id) REFERENCES memberships (tenant_id, id),
          FOREIGN KEY (tenant_id, project_id) REFERENCES projects (tenant_id, id)
        );

        CREATE TABLE file_versions (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL,
          file_id uuid NOT NULL,
          version_no int NOT NULL,
          size_bytes bigint NOT NULL DEFAULT 0,
          sha256 bytea,
          storage_key text,
          -- Small text bodies (Markdown results, previews) live here until object storage takes over (P-06).
          text_content text,
          created_by_membership_id uuid,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, id),
          UNIQUE (file_id, version_no),
          FOREIGN KEY (tenant_id, file_id) REFERENCES files (tenant_id, id)
        );

        CREATE TABLE sessions (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          project_id uuid,
          owner_membership_id uuid NOT NULL,
          {VISIBILITY},
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, id),
          FOREIGN KEY (tenant_id, owner_membership_id) REFERENCES memberships (tenant_id, id)
        );

        CREATE TABLE tasks (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          session_id uuid NOT NULL,
          agent_id uuid NOT NULL,
          agent_version_id uuid,
          project_id uuid,
          name text NOT NULL,
          kind text NOT NULL DEFAULT 'work' CHECK (kind IN ('work', 'code', 'channel')),
          status text NOT NULL DEFAULT 'queued' CHECK (status IN (
            'queued', 'provisioning', 'running', 'awaiting_approval', 'needs_auth', 'waiting_external', 'finalizing',
            'succeeded', 'failed', 'cancelled', 'interrupted')),
          status_reason text,
          model_tier text NOT NULL DEFAULT 'auto',
          capabilities text[] NOT NULL DEFAULT '{{}}',
          input jsonb NOT NULL DEFAULT '{{}}'::jsonb,
          created_by_membership_id uuid NOT NULL,
          assignee_membership_id uuid,
          supporting_agent_ids uuid[] NOT NULL DEFAULT '{{}}',
          review_state text NOT NULL DEFAULT 'review' CHECK (review_state IN ('review', 'accepted')),
          owner_membership_id uuid NOT NULL,
          {VISIBILITY},
          idempotency_key text,
          cancel_requested_at timestamptz,
          row_version bigint NOT NULL DEFAULT 1,
          deleted_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          finished_at timestamptz,
          UNIQUE (tenant_id, id),
          FOREIGN KEY (tenant_id, session_id) REFERENCES sessions (tenant_id, id),
          FOREIGN KEY (tenant_id, agent_id) REFERENCES agents (tenant_id, id),
          FOREIGN KEY (tenant_id, created_by_membership_id) REFERENCES memberships (tenant_id, id)
        );
        CREATE INDEX tasks_tenant_recent ON tasks (tenant_id, created_at DESC) WHERE deleted_at IS NULL;
        CREATE INDEX tasks_queued ON tasks (created_at) WHERE status = 'queued';

        -- Per-member view state (pinned, archived, unread) for shared tasks.
        CREATE TABLE task_member_state (
          tenant_id uuid NOT NULL,
          task_id uuid NOT NULL,
          membership_id uuid NOT NULL,
          pinned boolean NOT NULL DEFAULT false,
          archived boolean NOT NULL DEFAULT false,
          unread boolean NOT NULL DEFAULT false,
          updated_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (tenant_id, task_id, membership_id),
          FOREIGN KEY (tenant_id, task_id) REFERENCES tasks (tenant_id, id)
        );

        CREATE TABLE task_messages (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL,
          task_id uuid NOT NULL,
          role text NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
          content text NOT NULL,
          author_membership_id uuid,
          file_id uuid,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, id),
          FOREIGN KEY (tenant_id, task_id) REFERENCES tasks (tenant_id, id)
        );
        CREATE INDEX task_messages_task ON task_messages (tenant_id, task_id, created_at);

        CREATE TABLE automations (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          name text NOT NULL,
          description text NOT NULL DEFAULT '',
          schedule text NOT NULL,
          timezone text NOT NULL DEFAULT 'UTC',
          agent_id uuid,
          prompt text NOT NULL DEFAULT '',
          enabled boolean NOT NULL DEFAULT true,
          next_run_at timestamptz,
          last_run_at timestamptz,
          owner_membership_id uuid NOT NULL,
          {VISIBILITY},
          deleted_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, id),
          FOREIGN KEY (tenant_id, owner_membership_id) REFERENCES memberships (tenant_id, id)
        );

        CREATE TABLE scenarios (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          name text NOT NULL,
          problem text NOT NULL,
          role text NOT NULL DEFAULT '',
          input text NOT NULL DEFAULT '',
          output text NOT NULL DEFAULT '',
          ecosystems text[] NOT NULL DEFAULT '{{}}',
          owner_membership_id uuid NOT NULL,
          {VISIBILITY},
          deleted_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, id)
        );

        -- Tenant event log for the SSE stream (IDs and summaries only; Part 11 §4). Clients refetch through the API.
        CREATE TABLE tenant_events (
          seq bigserial PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          type text NOT NULL,
          payload jsonb NOT NULL DEFAULT '{{}}'::jsonb,
          -- NULL: everyone in the tenant may be notified; else only these memberships.
          audience uuid[],
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX tenant_events_stream ON tenant_events (tenant_id, seq);
        GRANT USAGE, SELECT ON SEQUENCE tenant_events_seq_seq TO workx_app;
        """
    )
    for table in ("projects", "agents", "files", "tasks", "automations", "scenarios"):
        op.execute(
            f"CREATE TRIGGER {table}_touch BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION workx_touch_updated_at()"
        )
    op.execute(
        """
        -- Published agent versions are immutable (Part 11 agent_versions).
        CREATE FUNCTION workx_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION '% rows are immutable', TG_TABLE_NAME USING ERRCODE = 'check_violation';
        END $$;
        CREATE TRIGGER agent_versions_immutable BEFORE UPDATE OR DELETE ON agent_versions
          FOR EACH ROW EXECUTE FUNCTION workx_immutable();
        CREATE TRIGGER file_versions_immutable BEFORE UPDATE OR DELETE ON file_versions
          FOR EACH ROW EXECUTE FUNCTION workx_immutable();

        -- Project principals for grants (replaces the placeholder from 0003).
        CREATE OR REPLACE FUNCTION workx_member_projects(p_tenant uuid, p_membership uuid) RETURNS TABLE (project_id uuid)
          LANGUAGE sql STABLE AS $$
          SELECT project_id FROM project_members
          WHERE tenant_id = p_tenant AND membership_id = p_membership AND status = 'active'
        $$;
        """
    )
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} USING (tenant_id = workx_tenant_id()) "
            "WITH CHECK (tenant_id = workx_tenant_id())"
        )
    op.execute("REVOKE UPDATE, DELETE ON tenant_events FROM workx_app")


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION workx_member_projects(p_tenant uuid, p_membership uuid) RETURNS TABLE (project_id uuid)
          LANGUAGE sql STABLE AS $$ SELECT NULL::uuid WHERE false $$;
        """
    )
    op.execute("DROP TABLE IF EXISTS " + ", ".join(reversed(TABLES)) + " CASCADE")
    op.execute("DROP FUNCTION IF EXISTS workx_immutable()")
