"""Tenant event log feeding the SSE stream (Part 11 §4). Payloads carry IDs and short summaries only;
clients refetch through the API, where authorization applies."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, select
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from workx.core.orm import Base, utcnow
from workx.core.redaction import redact


class TenantEvent(Base):
    __tablename__ = "tenant_events"

    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID]
    type: Mapped[str]
    payload: Mapped[dict[str, Any]] = mapped_column(server_default="{}")
    audience: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    created_at: Mapped[datetime] = mapped_column(server_default="now()")


def publish(
    session: Session,
    tenant_id: uuid.UUID,
    type_: str,
    payload: dict[str, Any] | None = None,
    *,
    audience: Iterable[uuid.UUID] | None = None,
) -> None:
    session.add(
        TenantEvent(
            tenant_id=tenant_id,
            type=type_,
            payload=redact(payload or {}),
            audience=list(audience) if audience is not None else None,
            created_at=utcnow(),
        )
    )


def since(
    session: Session, tenant_id: uuid.UUID, after_seq: int, membership_id: uuid.UUID, limit: int = 200
) -> list[TenantEvent]:
    rows = (
        session.execute(
            select(TenantEvent)
            .where(TenantEvent.tenant_id == tenant_id, TenantEvent.seq > after_seq)
            .order_by(TenantEvent.seq)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [e for e in rows if e.audience is None or membership_id in e.audience]


def latest_seq(session: Session, tenant_id: uuid.UUID) -> int:
    from sqlalchemy import func

    return int(
        session.execute(
            select(func.coalesce(func.max(TenantEvent.seq), 0)).where(TenantEvent.tenant_id == tenant_id)
        ).scalar_one()
    )
