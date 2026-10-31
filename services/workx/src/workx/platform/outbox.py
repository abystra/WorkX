"""Transactional outbox: call ``emit`` inside the transaction that makes the change (Part 10, Part 11 §4)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from workx.core import ids
from workx.platform.models import OutboxEvent


def emit(session: Session, topic: str, payload: dict[str, Any], *, tenant_id: uuid.UUID | None = None) -> uuid.UUID:
    event_id = ids.uuid7()
    session.add(OutboxEvent(id=event_id, tenant_id=tenant_id, topic=topic, payload=payload))
    return event_id
