from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from workx.core.orm import Base


class ChannelBinding(Base):
    __tablename__ = "channel_bindings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    public_id: Mapped[str]
    platform: Mapped[str]
    method: Mapped[str]
    name: Mapped[str]
    agent_id: Mapped[uuid.UUID]
    capabilities: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    config: Mapped[dict[str, Any]] = mapped_column(server_default="{}")
    connection_id: Mapped[uuid.UUID | None]
    enabled: Mapped[bool] = mapped_column(server_default="true")
    revision: Mapped[int] = mapped_column(server_default="1")
    created_by_membership_id: Mapped[uuid.UUID]
    deleted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(server_default="now()")


class ExternalIdentity(Base):
    __tablename__ = "external_identities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    platform: Mapped[str]
    external_tenant: Mapped[str]
    external_user_id: Mapped[str]
    membership_id: Mapped[uuid.UUID]
    verified_via: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")


class ChannelLinkCode(Base):
    __tablename__ = "channel_link_codes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    binding_id: Mapped[uuid.UUID]
    membership_id: Mapped[uuid.UUID]
    code_hash: Mapped[bytes]
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")


class InboundMessage(Base):
    __tablename__ = "inbound_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    binding_id: Mapped[uuid.UUID]
    platform_event_id: Mapped[str]
    platform_message_id: Mapped[str | None]
    conversation_ref: Mapped[str]
    conversation_kind: Mapped[str]
    external_tenant: Mapped[str] = mapped_column(server_default="")
    sender_ref: Mapped[str]
    sender_name: Mapped[str | None]
    mentioned: Mapped[bool] = mapped_column(server_default="false")
    text: Mapped[str]
    status: Mapped[str] = mapped_column(server_default="received")
    reason: Mapped[str | None]
    membership_id: Mapped[uuid.UUID | None]
    task_id: Mapped[uuid.UUID | None]
    replay_count: Mapped[int] = mapped_column(server_default="0")
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    processed_at: Mapped[datetime | None]


class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    binding_id: Mapped[uuid.UUID]
    binding_revision: Mapped[int]
    inbound_id: Mapped[uuid.UUID]
    task_id: Mapped[uuid.UUID | None]
    purpose: Mapped[str]
    target: Mapped[dict[str, Any]]
    text: Mapped[str]
    status: Mapped[str] = mapped_column(server_default="queued")
    attempts: Mapped[int] = mapped_column(server_default="0")
    platform_receipt: Mapped[str | None]
    last_error: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(server_default="now()")
