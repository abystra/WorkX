from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Mapped, mapped_column

from workx.core.orm import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID | None]
    actor_user_id: Mapped[uuid.UUID | None]
    actor_membership_id: Mapped[uuid.UUID | None]
    action: Mapped[str]
    target_type: Mapped[str | None]
    target_id: Mapped[uuid.UUID | None]
    data: Mapped[dict[str, Any]] = mapped_column(server_default="{}")
    request_id: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
