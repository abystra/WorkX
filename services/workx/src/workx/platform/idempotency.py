"""Idempotency-Key handling (Part 11 §3).

The key row is inserted in the same transaction as the work. A concurrent duplicate blocks on the row lock
until the first transaction ends, then replays its stored response. A different body under the same key is
rejected with 409 IDEMPOTENCY_KEY_REUSED.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from workx.core.errors import ApiError, validation
from workx.core.orm import utcnow
from workx.platform.models import IdempotencyKey

TTL = timedelta(hours=24)


def request_hash(body: Any) -> bytes:
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).digest()


def run(
    session: Session,
    *,
    key: str | None,
    scope: str,
    principal_id: uuid.UUID,
    route: str,
    body: Any,
    work: Callable[[], tuple[int, dict[str, Any] | list[Any]]],
) -> tuple[int, Any]:
    if not key:
        raise ApiError(428, "IDEMPOTENCY_KEY_REQUIRED", "Send an Idempotency-Key header with this request.")
    if len(key) > 200:
        raise validation("Idempotency-Key is too long.")
    digest = request_hash(body)
    inserted = session.execute(
        insert(IdempotencyKey)
        .values(
            scope=scope, principal_id=principal_id, route=route, key=key, request_hash=digest, expires_at=utcnow() + TTL
        )
        .on_conflict_do_nothing()
        .returning(IdempotencyKey.key)
    ).scalar()
    if inserted is None:
        existing = session.execute(
            select(IdempotencyKey)
            .where(
                IdempotencyKey.scope == scope,
                IdempotencyKey.principal_id == principal_id,
                IdempotencyKey.route == route,
                IdempotencyKey.key == key,
            )
            .with_for_update()
        ).scalar_one()
        if existing.request_hash != digest:
            raise ApiError(
                409, "IDEMPOTENCY_KEY_REUSED", "This Idempotency-Key was already used with a different request."
            )
        if existing.status_code is not None and existing.expires_at > utcnow():
            return existing.status_code, existing.response
        existing.request_hash = digest
        existing.expires_at = utcnow() + TTL
        row = existing
    else:
        row = session.get(IdempotencyKey, (scope, principal_id, route, key))  # type: ignore[assignment]
    status, response = work()
    row.status_code = status
    row.response = response  # type: ignore[assignment]
    return status, response
