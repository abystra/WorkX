from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from workx.core.orm import Base


class ConnectorInstallation(Base):
    __tablename__ = "connector_installations"

    tenant_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    connector_id: Mapped[str] = mapped_column(primary_key=True)
    enabled: Mapped[bool] = mapped_column(server_default="true")
    config: Mapped[dict[str, Any]] = mapped_column(server_default="{}")
    allowed_tools: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    installed_by_membership_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(server_default="now()")


class Connection(Base):
    __tablename__ = "connections"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    connector_id: Mapped[str]
    name: Mapped[str]
    owner_scope: Mapped[str]
    owner_membership_id: Mapped[uuid.UUID]
    status: Mapped[str] = mapped_column(server_default="pending")
    external_account: Mapped[str | None]
    granted_scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    authz_epoch: Mapped[int] = mapped_column(server_default="1")
    last_used_at: Mapped[datetime | None]
    last_refresh_at: Mapped[datetime | None]
    last_error: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(server_default="now()")


class ConnectionUsagePolicy(Base):
    __tablename__ = "connection_usage_policies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    connection_id: Mapped[uuid.UUID]
    principal_type: Mapped[str]
    principal_ref: Mapped[str]
    allowed_tools: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    created_at: Mapped[datetime] = mapped_column(server_default="now()")


class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    # Either a connection's credential or an installation's (OAuth client secret); never both (migration 0008).
    connection_id: Mapped[uuid.UUID | None]
    installation_connector_id: Mapped[str | None]
    usage_class: Mapped[str]
    kind: Mapped[str]
    active_version_id: Mapped[uuid.UUID | None]
    row_version: Mapped[int] = mapped_column(server_default="1")
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(server_default="now()")


class AuthorizationRequest(Base):
    __tablename__ = "authorization_requests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    task_id: Mapped[uuid.UUID | None]
    attempt_id: Mapped[uuid.UUID | None]
    connector_id: Mapped[str]
    target_membership_id: Mapped[uuid.UUID]
    status: Mapped[str] = mapped_column(server_default="pending")
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    completed_at: Mapped[datetime | None]
