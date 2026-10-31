"""Putting a stopped Task back in the queue: manual retry, and resume after the user re-authorizes (Part 4 §11)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from workx.core import ids
from workx.core.orm import utcnow
from workx.domains.connections.models import AuthorizationRequest
from workx.domains.resources import events as tenant_events
from workx.domains.runtime.models import ToolOperation
from workx.domains.tasks.models import Task
from workx.platform import outbox

RETRYABLE = ("failed", "interrupted", "cancelled", "needs_auth")


def unknown_operations(session: Session, task_id: uuid.UUID) -> list[str]:
    """Writes whose outcome is unknown: retrying could repeat them, so a person checks first."""
    return sorted(
        set(
            session.execute(
                select(ToolOperation.tool).where(ToolOperation.task_id == task_id, ToolOperation.status == "unknown")
            ).scalars()
        )
    )


def requeue(session: Session, task: Task, audience: list[uuid.UUID]) -> None:
    """The next attempt starts with the next fence; the ledger returns results of writes already done."""
    task.status, task.status_reason, task.finished_at, task.cancel_requested_at = "queued", None, None, None
    task.row_version += 1
    outbox.emit(
        session,
        "task.queued",
        {"task_id": str(task.id), "tenant_id": str(task.tenant_id), "retry": True},
        tenant_id=task.tenant_id,
    )
    tenant_events.publish(
        session, task.tenant_id, "task.queued", {"task_id": ids.encode("task", task.id)}, audience=audience
    )


def resume_authorized(session: Session, membership_id: uuid.UUID, connector_id: str) -> list[uuid.UUID]:
    """The member authorized ``connector_id``: close their open requests and requeue the tasks that waited."""
    requests = (
        session.execute(
            select(AuthorizationRequest)
            .where(
                AuthorizationRequest.target_membership_id == membership_id,
                AuthorizationRequest.connector_id == connector_id,
                AuthorizationRequest.status == "pending",
            )
            .with_for_update()
        )
        .scalars()
        .all()
    )
    resumed: list[uuid.UUID] = []
    for request in requests:
        request.status, request.completed_at = "completed", utcnow()
        if request.task_id is None or request.task_id in resumed:
            continue
        task = session.get(Task, request.task_id, with_for_update=True)
        if task is None or task.status != "needs_auth" or unknown_operations(session, task.id):
            continue
        # Other connectors may still be missing: the next attempt's preflight asks for them.
        requeue(session, task, [membership_id])
        resumed.append(task.id)
    return resumed
