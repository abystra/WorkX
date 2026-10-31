from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from workx.core.orm import Base


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    name: Mapped[str]
    description: Mapped[str] = mapped_column(server_default="")
    tag: Mapped[str] = mapped_column(server_default="Personal")
    avatar: Mapped[int] = mapped_column(server_default="0")
    owner_membership_id: Mapped[uuid.UUID]
    visibility: Mapped[str] = mapped_column(server_default="private")
    instructions: Mapped[str] = mapped_column(server_default="")
    context_md: Mapped[str] = mapped_column(server_default="")
    model_tier: Mapped[str] = mapped_column(server_default="auto")
    skills: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    knowledge_source_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), server_default="{}")
    current_version_id: Mapped[uuid.UUID | None]
    row_version: Mapped[int] = mapped_column(server_default="1")
    deleted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(server_default="now()")


class AgentVersion(Base):
    __tablename__ = "agent_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    agent_id: Mapped[uuid.UUID]
    version_no: Mapped[int]
    instructions: Mapped[str]
    context_md: Mapped[str]
    model_tier: Mapped[str]
    skills: Mapped[list[str]] = mapped_column(ARRAY(Text))
    tool_refs: Mapped[list[Any]] = mapped_column(JSONB, server_default="[]")
    knowledge_source_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)))
    published_by_membership_id: Mapped[uuid.UUID]
    published_at: Mapped[datetime] = mapped_column(server_default="now()")
