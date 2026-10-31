"""Background effects of revocation and member offboarding (Part 3 §5, Part 6 Seq 8; backlog B-18)."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from workx.core.orm import utcnow
from workx.domains.connections import service
from workx.domains.connections.models import Connection
from workx.domains.runtime import leases
from workx.domains.tasks.models import Task
from workx.platform import jobs

LIVE = ("queued", "provisioning", "running", "awaiting_approval", "waiting_external", "finalizing")


@jobs.handler("destroy_connection_secrets", topics=("connection.revoked",))
def destroy_connection_secrets(ctx: jobs.JobContext, job: jobs.Job) -> None:
    ctx.services["broker"].destroy_secrets(
        tenant_id=uuid.UUID(job.payload["tenant_id"]), connection_id=uuid.UUID(job.payload["connection_id"])
    )


@jobs.handler("membership_offboarding", topics=("membership.removed", "membership.updated"))
def membership_offboarding(ctx: jobs.JobContext, job: jobs.Job) -> None:
    """Deactivated or removed members stop acting: their running tasks are cancelled (tickets revoked at once),
    their private connections suspended (deactivated, kept for reactivation) or revoked (removed)."""
    status = job.payload.get("status", "removed" if job.payload.get("topic") == "membership.removed" else None)
    if status not in ("removed", "deactivated"):
        return
    tenant_id, membership_id = uuid.UUID(job.payload["tenant_id"]), uuid.UUID(job.payload["membership_id"])
    with ctx.db.transaction(tenant_id=tenant_id) as session:
        for task in session.execute(
            select(Task).where(Task.created_by_membership_id == membership_id, Task.status.in_(LIVE)).with_for_update()
        ).scalars():
            task.cancel_requested_at = utcnow()
            if task.status == "queued":
                task.status, task.finished_at = "cancelled", utcnow()
            task.status_reason = f"member_{status}"
            leases.revoke_for_task(session, task.id)
        target = "revoked" if status == "removed" else "suspended"
        for connection in session.execute(
            select(Connection).where(
                Connection.owner_membership_id == membership_id,
                Connection.owner_scope == "member",
                Connection.status.in_(("active", "pending", "needs_auth")),
            )
        ).scalars():
            service.change_status(
                session, connection, target, actor_user_id=None, actor_membership_id=None, reason=f"member_{status}"
            )
