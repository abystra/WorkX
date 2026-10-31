"""Helpers shared by resource routes: id decoding, ownership, readable lookups, list filtering, pagination."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from workx.core import ids
from workx.core.errors import not_found
from workx.domains.authz import policy
from workx.domains.tenancy.service import Actor


def decode(kind: str, external: str | None) -> uuid.UUID:
    value = ids.decode(kind, external or "")
    if value is None:
        raise not_found()
    return value


def maybe(kind: str, value: uuid.UUID | None) -> str | None:
    return ids.encode(kind, value) if value else None


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def load[M](session: Session, model: type[M], actor: Actor, external: str, kind: str, *, lock: bool = False) -> M:
    row = session.get(model, decode(kind, external), with_for_update=lock)
    if (
        row is None
        or getattr(row, "tenant_id", None) != actor.tenant.id
        or getattr(row, "deleted_at", None) is not None
    ):
        raise not_found()
    return row


def require(
    session: Session, actor: Actor, action: str, resource_type: str, row: Any, extra: set[str] | None = None
) -> set[str]:
    """Policy check with optional implicit actions (e.g. project membership)."""
    actions = policy.allowed_actions(session, actor, resource_type, row) | (extra or set())
    if "read" not in actions:
        raise not_found()
    if action not in actions:
        from workx.core.errors import forbidden

        raise forbidden()
    return actions


def active_member_ids(session: Session, actor: Actor) -> set[uuid.UUID]:
    from workx.domains.tenancy.models import Membership

    return set(
        session.execute(
            select(Membership.id).where(Membership.tenant_id == actor.tenant.id, Membership.status == "active")
        ).scalars()
    )
