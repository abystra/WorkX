"""Ticket verification for the gateways (trusted zone)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from workx.core.db import set_context
from workx.core.errors import ApiError
from workx.core.orm import utcnow
from workx.domains.runtime.leases import digest


@dataclass(frozen=True)
class Lease:
    lease_id: uuid.UUID
    tenant_id: uuid.UUID
    task_id: uuid.UUID
    attempt_id: uuid.UUID
    kind: str
    scopes: dict[str, Any]


def verify(session: Session, token: str | None, kind: str) -> Lease:
    """Resolves the ticket and leaves the transaction in the ticket's tenant context. 401 when unusable."""
    if not token:
        raise ApiError(401, "TICKET_REQUIRED", "A ticket is required.")
    row = session.execute(text("SELECT * FROM workx_lease_by_hash(:h)"), {"h": digest(token)}).first()
    if row is None or row.kind != kind or row.revoked_at is not None or row.expires_at <= utcnow():
        raise ApiError(401, "TICKET_INVALID", "The ticket is not valid.")
    set_context(session, tenant_id=row.tenant_id, principal_id=None)
    return Lease(row.lease_id, row.tenant_id, row.task_id, row.attempt_id, row.kind, dict(row.scopes))
