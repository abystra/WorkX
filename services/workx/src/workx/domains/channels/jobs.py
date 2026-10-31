"""Channel worker (queues ``channel_in`` / ``channel_out`` in Part 10): process inbound messages, queue replies
when channel tasks finish, deliver replies through the broker."""

from __future__ import annotations

import uuid

from workx.core.orm import utcnow
from workx.domains.channels import service
from workx.domains.channels.models import ChannelBinding, Delivery, InboundMessage
from workx.domains.tasks.models import Task
from workx.platform import jobs

MAX_DELIVERY_ATTEMPTS = 5


def _links(ctx: jobs.JobContext) -> service.Links:
    return service.Links(getattr(ctx.settings, "public_base_url", ""))


@jobs.handler("channel_process_inbound", topics=("channel.inbound",))
def process_inbound(ctx: jobs.JobContext, job: jobs.Job) -> None:
    with ctx.db.transaction(tenant_id=uuid.UUID(job.payload["tenant_id"])) as session:
        service.process(session, uuid.UUID(job.payload["inbound_id"]), _links(ctx))


@jobs.handler("channel_task_finished", topics=("task.finished",))
def task_finished(ctx: jobs.JobContext, job: jobs.Job) -> None:
    with ctx.db.transaction(tenant_id=uuid.UUID(job.payload["tenant_id"])) as session:
        task = session.get(Task, uuid.UUID(job.payload["task_id"]))
        if task is not None and task.kind == "channel":
            service.task_finished(session, task.id, _links(ctx))


@jobs.handler("channel_deliver", topics=("channel.delivery_queued",))
def deliver(ctx: jobs.JobContext, job: jobs.Job) -> None:
    tenant_id = uuid.UUID(job.payload["tenant_id"])
    with ctx.db.transaction(tenant_id=tenant_id) as session:
        delivery = session.get(Delivery, uuid.UUID(job.payload["delivery_id"]), with_for_update=True)
        if delivery is None or delivery.status not in ("queued", "sending"):
            return
        binding = session.get(ChannelBinding, delivery.binding_id)
        inbound = session.get(InboundMessage, delivery.inbound_id)
        if (
            binding is None
            or binding.deleted_at is not None
            or not binding.enabled
            or binding.revision != delivery.binding_revision
        ):
            # The binding changed after this conversation started: do not reply with possibly different rules.
            delivery.status, delivery.last_error = "blocked", "binding_changed"
            _changed(session, inbound)
            return
        delivery.status, delivery.attempts = "sending", delivery.attempts + 1
        request = {
            "tenant_id": str(tenant_id),
            "binding_id": str(binding.id),
            "delivery_id": str(delivery.id),
            "target": delivery.target,
            "text": delivery.text,
        }
    result = ctx.services["broker"].channel_send(request)
    retry = False
    with ctx.db.transaction(tenant_id=tenant_id) as session:
        delivery = session.get(Delivery, uuid.UUID(job.payload["delivery_id"]), with_for_update=True)
        assert delivery is not None
        if result.get("status") == "delivered":
            delivery.status, delivery.platform_receipt, delivery.last_error = "delivered", result.get("receipt"), None
        elif result.get("status") == "unknown":
            delivery.status, delivery.last_error = "unknown", result.get("error")
        elif result.get("retryable") and delivery.attempts < MAX_DELIVERY_ATTEMPTS:
            delivery.status, delivery.last_error, retry = "queued", result.get("error"), True
        else:
            delivery.status, delivery.last_error = "failed", result.get("error")
        delivery.updated_at = utcnow()
        _changed(session, session.get(InboundMessage, delivery.inbound_id))
    if retry:
        raise RuntimeError("delivery will be retried")


def _changed(session: object, inbound: InboundMessage | None) -> None:
    if inbound is not None:
        service._changed(session, inbound)  # type: ignore[arg-type]
