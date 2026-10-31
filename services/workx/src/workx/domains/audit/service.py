from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from workx.core import context, ids
from workx.core.redaction import redact
from workx.domains.audit.models import AuditEvent


def record(
    session: Session,
    action: str,
    *,
    tenant_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_membership_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditEvent(
            id=ids.uuid7(),
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            actor_membership_id=actor_membership_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            data=redact(data or {}),
            request_id=context.request_id.get() or None,
        )
    )
