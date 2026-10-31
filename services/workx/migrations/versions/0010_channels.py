"""Channels (Part 8 J6, Part 11): bindings with a public ingress id, external identities linked to memberships,
link codes, inbound messages (deduplicated per binding and platform event) and deliveries.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-31
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

TABLES = ("channel_bindings", "external_identities", "channel_link_codes", "inbound_messages", "deliveries")


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE channel_bindings (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          public_id text NOT NULL UNIQUE,
          platform text NOT NULL CHECK (platform IN ('feishu', 'wecom')),
          method text NOT NULL CHECK (method IN ('feishu-bot', 'wecom-app', 'wecom-ai-bot')),
          name text NOT NULL,
          agent_id uuid NOT NULL,
          capabilities text[] NOT NULL DEFAULT '{}',
          config jsonb NOT NULL DEFAULT '{}'::jsonb,
          connection_id uuid,
          enabled boolean NOT NULL DEFAULT true,
          revision int NOT NULL DEFAULT 1,
          created_by_membership_id uuid NOT NULL,
          deleted_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, id)
        );

        -- A platform user linked to a membership: only through a WorkX-initiated link code (or admin mapping
        -- by verified email, R2). Never by display name (Part 6 §9).
        CREATE TABLE external_identities (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          platform text NOT NULL,
          external_tenant text NOT NULL,
          external_user_id text NOT NULL,
          membership_id uuid NOT NULL,
          verified_via text NOT NULL CHECK (verified_via IN ('link_code', 'admin')),
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, platform, external_tenant, external_user_id),
          FOREIGN KEY (tenant_id, membership_id) REFERENCES memberships (tenant_id, id)
        );

        CREATE TABLE channel_link_codes (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          binding_id uuid NOT NULL,
          membership_id uuid NOT NULL,
          code_hash bytea NOT NULL,
          expires_at timestamptz NOT NULL,
          used_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          FOREIGN KEY (tenant_id, binding_id) REFERENCES channel_bindings (tenant_id, id)
        );
        CREATE INDEX channel_link_codes_hash ON channel_link_codes (tenant_id, code_hash) WHERE used_at IS NULL;

        CREATE TABLE inbound_messages (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          binding_id uuid NOT NULL,
          platform_event_id text NOT NULL,
          platform_message_id text,
          conversation_ref text NOT NULL,
          conversation_kind text NOT NULL CHECK (conversation_kind IN ('direct', 'group')),
          external_tenant text NOT NULL DEFAULT '',
          sender_ref text NOT NULL,
          sender_name text,
          mentioned boolean NOT NULL DEFAULT false,
          text text NOT NULL,
          status text NOT NULL DEFAULT 'received'
            CHECK (status IN ('received', 'processed', 'ignored', 'unlinked', 'linked', 'rejected')),
          reason text,
          membership_id uuid,
          task_id uuid,
          replay_count int NOT NULL DEFAULT 0,
          created_at timestamptz NOT NULL DEFAULT now(),
          processed_at timestamptz,
          UNIQUE (binding_id, platform_event_id),
          FOREIGN KEY (tenant_id, binding_id) REFERENCES channel_bindings (tenant_id, id)
        );
        CREATE INDEX inbound_messages_task ON inbound_messages (tenant_id, task_id);

        CREATE TABLE deliveries (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL REFERENCES tenants (id),
          binding_id uuid NOT NULL,
          binding_revision int NOT NULL,
          inbound_id uuid NOT NULL,
          task_id uuid,
          purpose text NOT NULL CHECK (purpose IN ('result', 'notice')),
          target jsonb NOT NULL,
          text text NOT NULL,
          status text NOT NULL DEFAULT 'queued'
            CHECK (status IN ('queued', 'sending', 'delivered', 'failed', 'unknown', 'blocked')),
          attempts int NOT NULL DEFAULT 0,
          platform_receipt text,
          last_error text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (inbound_id, purpose),
          FOREIGN KEY (tenant_id, binding_id) REFERENCES channel_bindings (tenant_id, id)
        );

        -- Ingress arrives with only the binding's public id: resolve it to its tenant (no other columns).
        CREATE FUNCTION workx_binding_by_public_id(p_public_id text) RETURNS TABLE (tenant_id uuid, id uuid)
          LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
          SELECT tenant_id, id FROM channel_bindings WHERE public_id = p_public_id AND deleted_at IS NULL
        $$;
        GRANT EXECUTE ON FUNCTION workx_binding_by_public_id(text) TO workx_app;
        """
    )
    for table in ("channel_bindings", "deliveries"):
        op.execute(
            f"CREATE TRIGGER {table}_touch BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION workx_touch_updated_at()"
        )
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} USING (tenant_id = workx_tenant_id()) "
            "WITH CHECK (tenant_id = workx_tenant_id())"
        )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS workx_binding_by_public_id(text)")
    op.execute("DROP TABLE IF EXISTS " + ", ".join(reversed(TABLES)) + " CASCADE")
