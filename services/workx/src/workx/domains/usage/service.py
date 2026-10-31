from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from workx.core import ids
from workx.core.orm import utcnow
from workx.domains.usage.models import UsageEvent


def record(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    kind: str,
    quantity: Decimal | int | float,
    unit: str,
    source_event_id: str,
    task_id: uuid.UUID | None = None,
    attempt_id: uuid.UUID | None = None,
    membership_id: uuid.UUID | None = None,
    data: dict[str, Any] | None = None,
) -> bool:
    """Returns False when this source event was already metered (retries never double-count)."""
    inserted = session.execute(
        insert(UsageEvent)
        .values(
            id=ids.uuid7(),
            tenant_id=tenant_id,
            kind=kind,
            quantity=Decimal(str(quantity)),
            unit=unit,
            task_id=task_id,
            attempt_id=attempt_id,
            membership_id=membership_id,
            source_event_id=source_event_id,
            data=data or {},
            created_at=utcnow(),
        )
        .on_conflict_do_nothing(index_elements=["tenant_id", "kind", "source_event_id"])
        .returning(UsageEvent.id)
    ).scalar()
    return inserted is not None
