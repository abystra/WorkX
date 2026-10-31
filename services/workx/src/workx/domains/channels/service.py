"""Inbound processing, identity linking and deliveries (Part 8 J6).

* The tenant always comes from the binding (resolved by its public id), never from the payload.
* A sender acts as a WorkX member only after linking (a code the member creates in WorkX and sends to the bot).
* Group chats: the bot must be @mentioned; replies never put member-private content in the group (link only).
* Deliveries are records with a status; the platform's dedupe key is the delivery id; a binding changed or
  disabled after the task started blocks the reply.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import exists, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from workx.core import ids
from workx.core.orm import utcnow
from workx.domains.agents.models import Agent
from workx.domains.audit import service as audit
from workx.domains.channels.models import ChannelBinding, ChannelLinkCode, Delivery, ExternalIdentity, InboundMessage
from workx.domains.channels.platforms import Inbound
from workx.domains.connections.catalog import CONNECTORS
from workx.domains.identity.models import User
from workx.domains.resources import events
from workx.domains.runtime.models import TaskEvent
from workx.domains.tasks import service as tasks
from workx.domains.tasks.models import Task, TaskMessage
from workx.domains.tenancy.models import Membership, Tenant
from workx.domains.tenancy.service import Actor
from workx.platform import outbox

LINK_TTL = timedelta(minutes=10)
LINK_COMMAND = re.compile(r"^\s*(?:link|绑定)\s+([A-Z0-9]{8})\s*$", re.IGNORECASE)
REPLY_LIMIT = 3500
USER_TOOLS = {t for c in CONNECTORS.values() if c.identity == "user" for t in c.tools}


def _hash(code: str) -> bytes:
    return hashlib.sha256(code.upper().encode()).digest()


def new_link_code(session: Session, binding: ChannelBinding, membership_id: uuid.UUID) -> tuple[str, Any]:
    code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
    expires = utcnow() + LINK_TTL
    session.add(
        ChannelLinkCode(
            id=ids.uuid7(),
            tenant_id=binding.tenant_id,
            binding_id=binding.id,
            membership_id=membership_id,
            code_hash=_hash(code),
            expires_at=expires,
        )
    )
    return code, expires


def record_inbound(session: Session, binding: ChannelBinding, message: Inbound) -> tuple[InboundMessage, bool]:
    """Inserts once per (binding, platform event); a replay only increments the counter."""
    inserted = session.execute(
        insert(InboundMessage)
        .values(
            id=ids.uuid7(),
            tenant_id=binding.tenant_id,
            binding_id=binding.id,
            platform_event_id=message.event_id,
            platform_message_id=message.message_id,
            conversation_ref=message.conversation,
            conversation_kind=message.kind,
            external_tenant=message.external_tenant,
            sender_ref=message.sender,
            sender_name=message.sender_name,
            mentioned=message.mentioned,
            text=message.text[:4000],
        )
        .on_conflict_do_nothing(index_elements=["binding_id", "platform_event_id"])
        .returning(InboundMessage.id)
    ).scalar()
    if inserted is None:
        row = session.execute(
            select(InboundMessage)
            .where(InboundMessage.binding_id == binding.id, InboundMessage.platform_event_id == message.event_id)
            .with_for_update()
        ).scalar_one()
        row.replay_count += 1
        return row, False
    created = session.get(InboundMessage, inserted)
    assert created is not None
    row = created
    outbox.emit(
        session,
        "channel.inbound",
        {"tenant_id": str(binding.tenant_id), "inbound_id": str(row.id)},
        tenant_id=binding.tenant_id,
    )
    _changed(session, row)
    return row, True


def _changed(session: Session, row: InboundMessage) -> None:
    events.publish(
        session,
        row.tenant_id,
        "channel.run.updated",
        {
            "run_id": ids.encode("channel_run", row.id),
            "task_id": ids.encode("task", row.task_id) if row.task_id else None,
        },
    )


def _notice(session: Session, binding: ChannelBinding, row: InboundMessage, text_: str) -> None:
    _queue(session, binding, row, None, "notice", text_, binding.revision)


def _queue(
    session: Session,
    binding: ChannelBinding,
    row: InboundMessage,
    task_id: uuid.UUID | None,
    purpose: str,
    text_: str,
    revision: int,
) -> Delivery | None:
    """``revision``: the binding revision the conversation started under; a later change blocks the reply."""
    target = {"chat_id": row.conversation_ref, "message_id": row.platform_message_id, "user_id": row.sender_ref}
    delivery_id = session.execute(
        insert(Delivery)
        .values(
            id=ids.uuid7(),
            tenant_id=row.tenant_id,
            binding_id=binding.id,
            binding_revision=revision,
            inbound_id=row.id,
            task_id=task_id,
            purpose=purpose,
            target=target,
            text=text_[:REPLY_LIMIT],
        )
        .on_conflict_do_nothing(index_elements=["inbound_id", "purpose"])
        .returning(Delivery.id)
    ).scalar()
    if delivery_id is None:
        return None
    outbox.emit(
        session,
        "channel.delivery_queued",
        {"tenant_id": str(row.tenant_id), "delivery_id": str(delivery_id)},
        tenant_id=row.tenant_id,
    )
    return session.get(Delivery, delivery_id)


@dataclass(frozen=True)
class Links:
    web_base: str

    def task(self, tenant_id: uuid.UUID, task_id: uuid.UUID) -> str:
        return f"{self.web_base.rstrip('/')}/t/{ids.encode('tenant', tenant_id)}/task/{ids.encode('task', task_id)}"


def process(session: Session, inbound_id: uuid.UUID, links: Links) -> str:
    """Trigger rules → link command → identity → task. Returns the inbound's final status."""
    row = session.get(InboundMessage, inbound_id, with_for_update=True)
    if row is None or row.status != "received":
        return "skipped"
    binding = session.get(ChannelBinding, row.binding_id)
    assert binding is not None

    def finish(status: str, reason: str | None = None) -> str:
        row.status, row.reason, row.processed_at = status, reason, utcnow()
        _changed(session, row)
        return status

    if binding.deleted_at is not None or not binding.enabled:
        return finish("ignored", "binding_disabled")
    if row.conversation_kind == "group" and (binding.method == "wecom-app" or not row.mentioned):
        return finish("ignored", "not_addressed")  # group messages need an @mention; WeCom apps are direct only
    command = LINK_COMMAND.match(row.text)
    if command:
        if row.conversation_kind != "direct":
            _notice(session, binding, row, "To link your WorkX account, send the link code to me in a direct message.")
            return finish("ignored", "link_in_group")
        return finish(*_link(session, binding, row, command.group(1)))
    identity = session.execute(
        select(ExternalIdentity).where(
            ExternalIdentity.platform == binding.platform,
            ExternalIdentity.external_tenant == row.external_tenant,
            ExternalIdentity.external_user_id == row.sender_ref,
        )
    ).scalar_one_or_none()
    member = session.get(Membership, identity.membership_id) if identity else None
    if member is None or member.status != "active":
        _notice(
            session,
            binding,
            row,
            "I don't know who you are in WorkX yet. In WorkX, open Settings > Channels, create a link code for "
            f'"{binding.name}" and send me: link <code>',
        )
        return finish("unlinked", "no_linked_member" if member is None else "member_inactive")
    agent = session.get(Agent, binding.agent_id)
    if agent is None or agent.deleted_at is not None or not row.text:
        _notice(session, binding, row, "This bot is not connected to a workmate right now.")
        return finish("rejected", "agent_unavailable")
    tenant, user = session.get(Tenant, row.tenant_id), session.get(User, member.user_id)
    assert tenant is not None and user is not None
    actor = Actor(user_id=user.id, tenant=tenant, membership=member)
    task = tasks.create(
        session,
        actor,
        agent=agent,
        prompt=row.text,
        project_id=None,
        model_tier="auto",
        capabilities=[],
        name=None,
        kind="channel",
    )
    task.input = {
        **task.input,
        "channel": {"binding_id": str(binding.id), "inbound_id": str(row.id), "binding_revision": binding.revision},
    }
    row.membership_id, row.task_id = member.id, task.id
    audit.record(
        session,
        "channel.inbound",
        tenant_id=row.tenant_id,
        actor_user_id=user.id,
        actor_membership_id=member.id,
        target_type="task",
        target_id=task.id,
        data={"binding": str(binding.id), "kind": row.conversation_kind},
    )
    return finish("processed")


def _link(session: Session, binding: ChannelBinding, row: InboundMessage, code: str) -> tuple[str, str | None]:
    found = session.execute(
        select(ChannelLinkCode)
        .where(ChannelLinkCode.code_hash == _hash(code), ChannelLinkCode.used_at.is_(None))
        .where(ChannelLinkCode.binding_id == binding.id, ChannelLinkCode.expires_at > func.now())
        .with_for_update()
    ).scalar_one_or_none()
    if found is None:
        _notice(session, binding, row, "That link code is not valid or has expired. Create a new one in WorkX.")
        return "rejected", "bad_link_code"
    existing = session.execute(
        select(ExternalIdentity).where(
            ExternalIdentity.platform == binding.platform,
            ExternalIdentity.external_tenant == row.external_tenant,
            ExternalIdentity.external_user_id == row.sender_ref,
        )
    ).scalar_one_or_none()
    if existing is not None and existing.membership_id != found.membership_id:
        _notice(session, binding, row, "This chat account is already linked to another WorkX member.")
        return "rejected", "already_linked"
    found.used_at = utcnow()
    if existing is None:
        session.add(
            ExternalIdentity(
                id=ids.uuid7(),
                tenant_id=row.tenant_id,
                platform=binding.platform,
                external_tenant=row.external_tenant,
                external_user_id=row.sender_ref,
                membership_id=found.membership_id,
                verified_via="link_code",
            )
        )
    row.membership_id = found.membership_id
    audit.record(
        session,
        "channel.identity_linked",
        tenant_id=row.tenant_id,
        actor_membership_id=found.membership_id,
        target_type="channel_binding",
        target_id=binding.id,
        data={"platform": binding.platform},
    )
    _notice(session, binding, row, "Linked. You can now ask me for work here.")
    return "linked", None


def private_content_used(session: Session, task_id: uuid.UUID) -> bool:
    """Member-private material: knowledge from files not shared with the whole organization, or tools that act
    with the member's own account."""
    private_knowledge = session.execute(
        text(
            """
            SELECT EXISTS (
              SELECT 1 FROM retrieval_logs r, unnest(r.chunk_ids) AS c(id)
              JOIN knowledge_chunks k ON k.id = c.id
              JOIN knowledge_sources s ON s.id = k.source_id
              LEFT JOIN files f ON f.id = s.file_id
              WHERE r.task_id = :t AND (f.id IS NULL OR f.visibility <> 'organization')
            )
            """
        ),
        {"t": task_id},
    ).scalar()
    user_tools = session.execute(
        select(
            exists().where(
                TaskEvent.task_id == task_id,
                TaskEvent.type == "tool.started",
                TaskEvent.payload["tool"].astext.in_(sorted(USER_TOOLS)),
            )
        )
    ).scalar()
    return bool(private_knowledge or user_tools)


def task_finished(session: Session, task_id: uuid.UUID, links: Links) -> Delivery | None:
    """Queues the reply for a channel task that reached a final state."""
    row = session.execute(select(InboundMessage).where(InboundMessage.task_id == task_id)).scalar_one_or_none()
    task = session.get(Task, task_id)
    if row is None or task is None:
        return None
    binding = session.get(ChannelBinding, row.binding_id)
    assert binding is not None
    link = links.task(task.tenant_id, task.id)
    if task.status == "succeeded":
        answer = (
            session.execute(
                select(TaskMessage.content)
                .where(TaskMessage.task_id == task.id, TaskMessage.role == "assistant")
                .order_by(TaskMessage.created_at.desc())
            )
            .scalars()
            .first()
            or "Done."
        )
        if row.conversation_kind == "group" and private_content_used(session, task.id):
            body = f"Done. The result uses content that is private to the requester. Open it in WorkX: {link}"
        else:
            body = f"{answer.strip()[: REPLY_LIMIT - 200]}\n\n{link}"
    elif task.status == "needs_auth":
        body = f"I need access to one of your accounts before I can continue. Authorize it in WorkX: {link}"
    elif task.status in ("failed", "interrupted", "cancelled"):
        body = f"I could not finish this ({task.status}). Details in WorkX: {link}"
    else:
        return None
    started_under = int((task.input.get("channel") or {}).get("binding_revision", binding.revision))
    return _queue(session, binding, row, task.id, "result", body, started_under)


def requeue_delivery(session: Session, delivery: Delivery) -> None:
    delivery.status, delivery.last_error = "queued", None
    outbox.emit(
        session,
        "channel.delivery_queued",
        {"tenant_id": str(delivery.tenant_id), "delivery_id": str(delivery.id)},
        tenant_id=delivery.tenant_id,
    )
