from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from workx.core.orm import Base


class WorkSession(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    project_id: Mapped[uuid.UUID | None]
    owner_membership_id: Mapped[uuid.UUID]
    visibility: Mapped[str] = mapped_column(server_default="private")
    created_at: Mapped[datetime] = mapped_column(server_default="now()")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    session_id: Mapped[uuid.UUID]
    agent_id: Mapped[uuid.UUID]
    agent_version_id: Mapped[uuid.UUID | None]
    project_id: Mapped[uuid.UUID | None]
    name: Mapped[str]
    kind: Mapped[str] = mapped_column(server_default="work")
    status: Mapped[str] = mapped_column(server_default="queued")
    status_reason: Mapped[str | None]
    model_tier: Mapped[str] = mapped_column(server_default="auto")
    capabilities: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    input: Mapped[dict[str, Any]] = mapped_column(server_default="{}")
    created_by_membership_id: Mapped[uuid.UUID]
    assignee_membership_id: Mapped[uuid.UUID | None]
    supporting_agent_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), server_default="{}")
    review_state: Mapped[str] = mapped_column(server_default="review")
    owner_membership_id: Mapped[uuid.UUID]
    visibility: Mapped[str] = mapped_column(server_default="private")
    idempotency_key: Mapped[str | None]
    cancel_requested_at: Mapped[datetime | None]
    row_version: Mapped[int] = mapped_column(server_default="1")
    deleted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(server_default="now()")
    finished_at: Mapped[datetime | None]


class TaskMemberState(Base):
    __tablename__ = "task_member_state"

    tenant_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    task_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    membership_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    pinned: Mapped[bool] = mapped_column(server_default="false")
    archived: Mapped[bool] = mapped_column(server_default="false")
    unread: Mapped[bool] = mapped_column(server_default="false")
    updated_at: Mapped[datetime] = mapped_column(server_default="now()")


class TaskMessage(Base):
    __tablename__ = "task_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    task_id: Mapped[uuid.UUID]
    role: Mapped[str]
    content: Mapped[str]
    author_membership_id: Mapped[uuid.UUID | None]
    file_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
