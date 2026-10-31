from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Mapped, mapped_column

from workx.core.orm import Base


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    scope: Mapped[str] = mapped_column(primary_key=True)
    principal_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    route: Mapped[str] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(primary_key=True)
    request_hash: Mapped[bytes]
    status_code: Mapped[int | None]
    response: Mapped[dict[str, Any] | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    expires_at: Mapped[datetime]


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID | None]
    topic: Mapped[str]
    payload: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    dispatched_at: Mapped[datetime | None]
