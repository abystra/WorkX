"""Background handlers for tenancy events."""

from __future__ import annotations

import uuid

from sqlalchemy import text

from workx.domains.tenancy import invitations
from workx.platform import jobs


@jobs.handler("send_invitation_email", topics=("invitation.created",))
def send_invitation_email(ctx: jobs.JobContext, job: jobs.Job) -> None:
    assert job.tenant_id is not None, "invitation events are tenant-scoped"
    invitations.send_invitation_email(
        ctx.db, ctx.settings, ctx.services["mailer"], uuid.UUID(job.payload["invitation_id"]), job.tenant_id
    )


@jobs.handler("reconcile")
def reconcile(ctx: jobs.JobContext, job: jobs.Job) -> None:
    """Periodic consistency sweep (Part 10 reconciler). Grows with later phases (task leases, deliveries)."""
    with ctx.db.transaction() as session:
        session.execute(text("SELECT workx_expire_invitations()"))
