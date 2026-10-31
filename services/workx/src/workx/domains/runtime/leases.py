"""Attempt tickets: issued by the control plane, verified only by the trusted gateways.

A ticket is a random bearer value given to one Attempt for one purpose (model or tool calls). Only its
SHA-256 digest is stored; it expires with the Attempt's wall time and is revoked on cancel and at the end of
the Attempt (Part 6 §5). Tickets authorize nothing outside their scopes.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session

from workx.core import ids
from workx.core.orm import utcnow
from workx.domains.runtime.models import CredentialLease


def digest(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def issue(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    task_id: uuid.UUID,
    attempt_id: uuid.UUID,
    kind: str,
    scopes: dict[str, Any],
    ttl: timedelta,
) -> str:
    token = f"wxt_{kind}_{secrets.token_urlsafe(32)}"
    session.add(
        CredentialLease(
            id=ids.uuid7(),
            tenant_id=tenant_id,
            task_id=task_id,
            attempt_id=attempt_id,
            kind=kind,
            token_hash=digest(token),
            scopes=scopes,
            expires_at=utcnow() + ttl,
            created_at=utcnow(),
        )
    )
    return token


def revoke_for_attempt(session: Session, attempt_id: uuid.UUID) -> int:
    result = session.execute(
        update(CredentialLease)
        .where(CredentialLease.attempt_id == attempt_id, CredentialLease.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def revoke_for_task(session: Session, task_id: uuid.UUID) -> int:
    result = session.execute(
        update(CredentialLease)
        .where(CredentialLease.task_id == task_id, CredentialLease.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]
