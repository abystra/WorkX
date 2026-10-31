"""Tenant event stream over SSE (Part 9 §5, Part 11 §4).

* Frames are named (``event: task.queued``) with ``id: <seq>``; browsers resume with ``Last-Event-ID``.
* Payloads carry IDs only. Clients refetch through the API, where authorization applies.
* Every ``sse_revalidate_seconds`` the stream re-checks the session and the membership; a revoked session or
  removed membership ends the stream with a ``stream.closed`` frame (B-02: within 60 s).
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from workx.core import ids
from workx.core.errors import ApiError
from workx.domains.identity import service as identity
from workx.domains.identity.auth import Authenticated, State
from workx.domains.resources import events
from workx.domains.tenancy import service as tenancy
from workx.domains.tenancy.api import tenant_uuid
from workx.platform.web import AppState

router = APIRouter(tags=["events"])
POLL_SECONDS = 1.0
HEARTBEAT_SECONDS = 20.0


def _frame(event: events.TenantEvent, tenant_external: str) -> str:
    body = {
        "event_id": f"evt_{event.seq}",
        "type": event.type,
        "tenant_id": tenant_external,
        "occurred_at": event.created_at.isoformat(),
        "payload": event.payload,
    }
    return f"id: {event.seq}\nevent: {event.type}\ndata: {json.dumps(body, ensure_ascii=False)}\n\n"


def _still_allowed(state: AppState, token: str, tenant_id: uuid.UUID) -> uuid.UUID | None:
    """Returns the membership id while the session and membership are valid, else None."""
    try:
        with state.db.transaction() as session:
            principal = identity.authenticate(session, token, state.settings)
            actor = tenancy.enter(session, user_id=principal.user_id, tenant_id=tenant_id)
            return actor.membership.id
    except ApiError:
        return None


def _fetch(
    state: AppState, user_id: uuid.UUID, tenant_id: uuid.UUID, after: int, membership_id: uuid.UUID
) -> list[events.TenantEvent]:
    with state.db.transaction(principal_id=user_id) as session:
        tenancy.enter(session, user_id=user_id, tenant_id=tenant_id)
        return events.since(session, tenant_id, after, membership_id)


def _latest(state: AppState, user_id: uuid.UUID, tenant_id: uuid.UUID) -> int:
    with state.db.transaction(principal_id=user_id) as session:
        tenancy.enter(session, user_id=user_id, tenant_id=tenant_id)
        return events.latest_seq(session, tenant_id)


@router.get(
    "/tenants/{tenant_id}/events", summary="Tenant event stream (Server-Sent Events)", response_class=StreamingResponse
)
async def stream(
    tenant_id: str,
    request: Request,
    principal: Authenticated,
    state: State,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    after: int | None = None,
    max_seconds: Annotated[float | None, Query(ge=0.5, le=3600, include_in_schema=False)] = None,
) -> StreamingResponse:
    tid = tenant_uuid(tenant_id)
    membership_id = await run_in_threadpool(_still_allowed, state, principal.session_token, tid)
    if membership_id is None:
        raise ApiError(404, "NOT_FOUND", "The resource does not exist or you do not have access to it.")
    cursor = after
    if cursor is None and last_event_id and last_event_id.isdigit():
        cursor = int(last_event_id)
    if cursor is None:
        cursor = await run_in_threadpool(_latest, state, principal.user_id, tid)
    external = ids.encode("tenant", tid)
    revalidate = state.settings.sse_revalidate_seconds

    async def body() -> AsyncIterator[str]:
        position = cursor
        started = last_check = last_beat = time.monotonic()
        yield f"retry: 3000\n: stream open at {position}\n\n"
        while True:
            now = time.monotonic()
            if max_seconds is not None and now - started >= max_seconds:
                return
            if await request.is_disconnected():
                return
            if now - last_check >= revalidate:
                last_check = now
                if await run_in_threadpool(_still_allowed, state, principal.session_token, tid) is None:
                    yield 'event: stream.closed\ndata: {"reason": "session_or_membership_ended"}\n\n'
                    return
            batch = await run_in_threadpool(_fetch, state, principal.user_id, tid, position, membership_id)
            for event in batch:
                position = max(position, event.seq)
                yield _frame(event, external)
            if now - last_beat >= HEARTBEAT_SECONDS:
                last_beat = now
                yield ": ping\n\n"
            await asyncio.sleep(POLL_SECONDS)

    return StreamingResponse(
        body(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
    )
