"""Audit log for owners and admins (Part 3 §6.1 "View audit log"), cursor-paginated (Part 11 §3)."""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import and_, or_, select

from workx.core import ids
from workx.core.errors import forbidden, validation
from workx.domains.audit.models import AuditEvent
from workx.domains.identity.auth import Authenticated, State
from workx.domains.tenancy import service as tenancy
from workx.domains.tenancy.api import tenant_uuid

router = APIRouter(tags=["audit"])


class AuditOut(BaseModel):
    id: str
    action: str
    actor_membership_id: str | None
    target_type: str | None
    target_id: str | None
    data: dict[str, Any]
    request_id: str | None
    created_at: datetime


class AuditPage(BaseModel):
    items: list[AuditOut]
    next_cursor: str | None


def _cursor(event: AuditEvent) -> str:
    raw = json.dumps([event.created_at.isoformat(), str(event.id)]).encode()
    return base64.urlsafe_b64encode(raw).decode()


def _parse(cursor: str) -> tuple[datetime, str]:
    try:
        created, event_id = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(created), str(event_id)
    except (ValueError, TypeError) as exc:
        raise validation("Invalid cursor.") from exc


@router.get("/tenants/{tenant_id}/audit-events", summary="Audit log (owners and admins)")
def audit_events(
    tenant_id: str,
    principal: Authenticated,
    state: State,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> AuditPage:
    tid = tenant_uuid(tenant_id)
    with state.db.transaction(principal_id=principal.user_id) as session:
        actor = tenancy.enter(session, user_id=principal.user_id, tenant_id=tid)
        if not (actor.is_manager or (actor.tenant.type == "personal" and actor.role == "owner")):
            raise forbidden("Only owners and admins can view the audit log.")
        query = select(AuditEvent).where(AuditEvent.tenant_id == tid)
        if cursor:
            created, event_id = _parse(cursor)
            query = query.where(
                or_(AuditEvent.created_at < created, and_(AuditEvent.created_at == created, AuditEvent.id < event_id))
            )
        rows = (
            session.execute(query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit + 1))
            .scalars()
            .all()
        )
    page = rows[:limit]
    return AuditPage(
        items=[
            AuditOut(
                id=ids.encode("audit", e.id),
                action=e.action,
                actor_membership_id=ids.encode("membership", e.actor_membership_id) if e.actor_membership_id else None,
                target_type=e.target_type,
                target_id=str(e.target_id) if e.target_id else None,
                data=e.data,
                request_id=e.request_id,
                created_at=e.created_at,
            )
            for e in page
        ],
        next_cursor=_cursor(page[-1]) if len(rows) > limit else None,
    )
