from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from workx.core.orm import Base


class TaskAttempt(Base):
    __tablename__ = "task_attempts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    task_id: Mapped[uuid.UUID]
    attempt_no: Mapped[int]
    fencing_token: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(server_default="pending")
    end_reason: Mapped[str | None]
    sandbox_provider: Mapped[str | None]
    sandbox_ref: Mapped[str | None]
    lease_owner: Mapped[str | None]
    lease_expires_at: Mapped[datetime | None]
    started_at: Mapped[datetime | None]
    ended_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")


class TaskEvent(Base):
    __tablename__ = "task_events"

    tenant_id: Mapped[uuid.UUID]
    task_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    attempt_id: Mapped[uuid.UUID | None]
    runner_event_id: Mapped[str | None]
    type: Mapped[str]
    payload: Mapped[dict[str, Any]] = mapped_column(server_default="{}")
    created_at: Mapped[datetime] = mapped_column(server_default="now()")


class CredentialLease(Base):
    __tablename__ = "credential_leases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    task_id: Mapped[uuid.UUID]
    attempt_id: Mapped[uuid.UUID]
    kind: Mapped[str]
    token_hash: Mapped[bytes]
    scopes: Mapped[dict[str, Any]] = mapped_column(server_default="{}")
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")


class ToolOperation(Base):
    __tablename__ = "tool_operations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    task_id: Mapped[uuid.UUID]
    attempt_id: Mapped[uuid.UUID]
    tool: Mapped[str]
    effect: Mapped[str]
    operation_key: Mapped[str]
    status: Mapped[str]
    result: Mapped[dict[str, Any] | None]
    error: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(server_default="now()")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    task_id: Mapped[uuid.UUID]
    attempt_id: Mapped[uuid.UUID]
    tool: Mapped[str]
    args_digest: Mapped[str]
    summary: Mapped[str]
    status: Mapped[str] = mapped_column(server_default="pending")
    decided_by_membership_id: Mapped[uuid.UUID | None]
    decided_at: Mapped[datetime | None]
    expires_at: Mapped[datetime]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")


class TenantBudget(Base):
    __tablename__ = "tenant_budgets"

    tenant_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    monthly_token_limit: Mapped[int | None] = mapped_column(BigInteger)
    per_task_token_limit: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(server_default="now()")
