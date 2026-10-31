from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Numeric
from sqlalchemy.orm import Mapped, mapped_column

from workx.core.orm import Base


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    kind: Mapped[str]
    quantity: Mapped[Decimal] = mapped_column(Numeric)
    unit: Mapped[str]
    task_id: Mapped[uuid.UUID | None]
    attempt_id: Mapped[uuid.UUID | None]
    membership_id: Mapped[uuid.UUID | None]
    source_event_id: Mapped[str]
    data: Mapped[dict[str, Any]] = mapped_column(server_default="{}")
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
