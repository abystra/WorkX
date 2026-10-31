"""Channel bindings, member linking, the channel workbench, and platform ingress (Part 8 J6, Part 11 §6)."""

from __future__ import annotations

import base64
import secrets
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from workx.core import ids
from workx.core.errors import ApiError, conflict, forbidden, not_found, validation
from workx.core.orm import utcnow
from workx.domains.agents.models import Agent
from workx.domains.audit import service as audit
from workx.domains.channels import platforms, service
from workx.domains.channels.models import ChannelBinding, Delivery, InboundMessage
from workx.domains.connections.api import broker
from workx.domains.identity.auth import Authenticated, State
from workx.domains.resources.common import decode, load, require
from workx.domains.runtime import resume
from workx.domains.tasks import service as tasks
from workx.domains.tasks.models import Task
from workx.domains.tenancy.api import tenant_uuid
from workx.domains.tenancy.service import Actor, tenant_scope

router = APIRouter(tags=["channels"])
METHODS = {"feishu": ("feishu-bot",), "wecom": ("wecom-app",)}
CONFIG_FIELDS = {"feishu": ("app_id", "bot_open_id"), "wecom": ("corp_id", "agent_id")}
INGRESS_MAX_BYTES = 64 * 1024


class BindingOut(BaseModel):
    id: str
    name: str
    platform: str
    method: str
    agent_id: str
    capabilities: list[str]
    enabled: bool
    revision: int
    config: dict[str, str]
    configured: bool
    webhook_url: str | None


def _out(state: Any, binding: ChannelBinding, actor: Actor) -> BindingOut:
    manager = actor.is_manager
    base = state.settings.api_base_url.rstrip("/")
    return BindingOut(
        id=ids.encode("channel_binding", binding.id),
        name=binding.name,
        platform=binding.platform,
        method=binding.method,
        agent_id=ids.encode("agent", binding.agent_id),
        capabilities=list(binding.capabilities),
        enabled=binding.enabled,
        revision=binding.revision,
        config={k: str(v) for k, v in (binding.config or {}).items()} if manager else {},
        configured=binding.connection_id is not None,
        webhook_url=f"{base}/api/v1/channels/{binding.platform}/{binding.public_id}/events" if manager else None,
    )


def _manager(actor: Actor) -> None:
    if not actor.is_manager:
        raise forbidden("Only organization owners and admins can configure channels.")


def _binding(session: Session, actor: Actor, binding_id: str, *, lock: bool = False) -> ChannelBinding:
    row = session.get(ChannelBinding, decode("channel_binding", binding_id), with_for_update=lock)
    if row is None or row.tenant_id != actor.tenant.id or row.deleted_at is not None:
        raise not_found()
    return row


@router.get("/tenants/{tenant_id}/channel-bindings", summary="Chat bots bound to workmates in this organization")
def list_bindings(tenant_id: str, principal: Authenticated, state: State) -> list[BindingOut]:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id)) as (session, actor):
        rows = session.execute(
            select(ChannelBinding)
            .where(ChannelBinding.tenant_id == actor.tenant.id, ChannelBinding.deleted_at.is_(None))
            .order_by(ChannelBinding.created_at.desc())
        ).scalars()
        return [_out(state, b, actor) for b in rows]


class BindingIn(BaseModel):
    platform: Literal["feishu", "wecom"]
    method: str
    name: str = Field(min_length=1, max_length=80)
    agent_id: str
    capabilities: list[str] = Field(default_factory=list, max_length=10)
    config: dict[str, str] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)


def _config(platform: str, values: dict[str, str]) -> dict[str, str]:
    unknown = set(values) - set(CONFIG_FIELDS[platform])
    if unknown:
        raise validation(f"Unknown setting: {', '.join(sorted(unknown))}", data={"field": "config"})
    return {k: v.strip()[:200] for k, v in values.items() if v.strip()}


@router.post("/tenants/{tenant_id}/channel-bindings", status_code=201, summary="Bind a chat bot to a workmate")
def create_binding(tenant_id: str, body: BindingIn, principal: Authenticated, state: State) -> BindingOut:
    tid = tenant_uuid(tenant_id)
    if body.method not in METHODS[body.platform]:
        raise validation("This connection method is not available.", data={"field": "method"})
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tid, write=True) as (session, actor):
        _manager(actor)
        agent = load(session, Agent, actor, body.agent_id, "agent")
        require(session, actor, "use", "agent", agent)
        binding = ChannelBinding(
            id=ids.uuid7(),
            tenant_id=actor.tenant.id,
            public_id=secrets.token_urlsafe(18),
            platform=body.platform,
            method=body.method,
            name=body.name.strip(),
            agent_id=agent.id,
            capabilities=sorted(set(body.capabilities)),
            config=_config(body.platform, body.config),
            created_by_membership_id=actor.membership.id,
        )
        session.add(binding)
        session.flush()
        audit.record(
            session,
            "channel.binding_created",
            tenant_id=actor.tenant.id,
            actor_user_id=actor.user_id,
            actor_membership_id=actor.membership.id,
            target_type="channel_binding",
            target_id=binding.id,
            data={"platform": body.platform},
        )
        binding_id, membership_id = binding.id, actor.membership.id
    if body.secrets:
        broker(state).channel_secrets(
            {
                "tenant_id": str(tid),
                "binding_id": str(binding_id),
                "actor_membership_id": str(membership_id),
                "values": body.secrets,
            }
        )
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tid) as (session, actor):
        return _out(state, _binding(session, actor, ids.encode("channel_binding", binding_id)), actor)


class BindingPatch(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    agent_id: str | None = None
    capabilities: list[str] | None = None
    config: dict[str, str] | None = None
    enabled: bool | None = None


@router.patch("/tenants/{tenant_id}/channel-bindings/{binding_id}", summary="Change, pause or resume a binding")
def patch_binding(
    tenant_id: str, binding_id: str, body: BindingPatch, principal: Authenticated, state: State
) -> BindingOut:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id), write=True) as (
        session,
        actor,
    ):
        _manager(actor)
        binding = _binding(session, actor, binding_id, lock=True)
        changed = False  # rules that replies depend on: a new revision blocks replies to older conversations
        if body.name is not None:
            binding.name = body.name.strip() or binding.name
        if body.agent_id is not None:
            agent = load(session, Agent, actor, body.agent_id, "agent")
            require(session, actor, "use", "agent", agent)
            changed |= agent.id != binding.agent_id
            binding.agent_id = agent.id
        if body.capabilities is not None:
            changed |= sorted(set(body.capabilities)) != sorted(binding.capabilities)
            binding.capabilities = sorted(set(body.capabilities))
        if body.config is not None:
            binding.config = {**binding.config, **_config(binding.platform, body.config)}
        if body.enabled is not None:
            if body.enabled and binding.connection_id is None:
                raise conflict("CHANNEL_NOT_CONFIGURED", "Add the bot credentials before enabling it.")
            changed |= binding.enabled and not body.enabled
            binding.enabled = body.enabled
        if changed:
            binding.revision += 1
        audit.record(
            session,
            "channel.binding_changed",
            tenant_id=actor.tenant.id,
            actor_user_id=actor.user_id,
            actor_membership_id=actor.membership.id,
            target_type="channel_binding",
            target_id=binding.id,
            data={"revision": binding.revision, "enabled": binding.enabled},
        )
        return _out(state, binding, actor)


@router.delete("/tenants/{tenant_id}/channel-bindings/{binding_id}", status_code=204, summary="Remove a binding")
def delete_binding(tenant_id: str, binding_id: str, principal: Authenticated, state: State) -> Response:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id), write=True) as (
        session,
        actor,
    ):
        _manager(actor)
        binding = _binding(session, actor, binding_id, lock=True)
        binding.deleted_at, binding.enabled, binding.revision = utcnow(), False, binding.revision + 1
        audit.record(
            session,
            "channel.binding_deleted",
            tenant_id=actor.tenant.id,
            actor_user_id=actor.user_id,
            actor_membership_id=actor.membership.id,
            target_type="channel_binding",
            target_id=binding.id,
        )
    return Response(status_code=204)


class SecretsIn(BaseModel):
    secrets: dict[str, str]


@router.put(
    "/tenants/{tenant_id}/channel-bindings/{binding_id}/secrets",
    status_code=204,
    summary="Set the bot's secrets (stored by the broker, never returned)",
)
def put_secrets(tenant_id: str, binding_id: str, body: SecretsIn, principal: Authenticated, state: State) -> Response:
    tid = tenant_uuid(tenant_id)
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tid) as (session, actor):
        _manager(actor)
        binding = _binding(session, actor, binding_id)
        payload = {
            "tenant_id": str(tid),
            "binding_id": str(binding.id),
            "actor_membership_id": str(actor.membership.id),
        }
    broker(state).channel_secrets({**payload, "values": body.secrets})
    return Response(status_code=204)


class LinkCodeOut(BaseModel):
    code: str
    expires_at: datetime
    instruction: str


@router.post(
    "/tenants/{tenant_id}/channel-bindings/{binding_id}/link-code",
    summary="A one-time code that links your chat account to your membership (send it to the bot)",
)
def link_code(tenant_id: str, binding_id: str, principal: Authenticated, state: State) -> LinkCodeOut:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id), write=True) as (
        session,
        actor,
    ):
        binding = _binding(session, actor, binding_id)
        code, expires = service.new_link_code(session, binding, actor.membership.id)
        return LinkCodeOut(
            code=code, expires_at=expires, instruction=f"Send this to {binding.name} in a direct message: link {code}"
        )


# ------------------------------------------------------------------------------------------- workbench


class RunOut(BaseModel):
    id: str
    task_id: str | None
    binding_id: str
    binding_name: str
    platform: str
    agent_id: str
    agent_name: str
    source: dict[str, Any]
    stage: str
    execution_status: str
    delivery_status: str
    delivery_attempts: int
    error_code: str | None
    reply: dict[str, Any] | None
    event_id: str
    replay_count: int
    created_at: datetime


def _stage(row: InboundMessage, task: Task | None, delivery: Delivery | None) -> tuple[str, str, str, str | None]:
    """(stage, execution status, delivery status, error) in the workbench's vocabulary."""
    if row.status in ("ignored", "rejected", "unlinked", "linked"):
        delivered = delivery.status if delivery else "none"
        return row.status, "none", delivered, row.reason
    if task is None:
        return "received", "queued", "pending", None
    execution = {"succeeded": "done", "queued": "queued"}.get(task.status, task.status)
    if task.status not in ("succeeded", "failed", "cancelled", "interrupted", "needs_auth"):
        return "running", "running", "pending", None
    if delivery is None:
        return "result", execution, "pending", task.status_reason
    if delivery.status == "delivered":
        return "delivered", execution, "delivered", None
    if delivery.status in ("failed", "unknown", "blocked"):
        return "delivery_failed", execution, delivery.status, delivery.last_error
    return "sending", execution, delivery.status, None


@router.get("/tenants/{tenant_id}/channel-runs", summary="Channel conversations: yours, or all for admins")
def list_runs(tenant_id: str, principal: Authenticated, state: State, limit: int = 100) -> list[RunOut]:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id)) as (session, actor):
        query = select(InboundMessage).where(InboundMessage.tenant_id == actor.tenant.id)
        if not actor.is_manager:
            query = query.where(InboundMessage.membership_id == actor.membership.id)
        rows = session.execute(query.order_by(InboundMessage.created_at.desc()).limit(min(limit, 200))).scalars().all()
        out = []
        for row in rows:
            binding = session.get(ChannelBinding, row.binding_id)
            assert binding is not None
            agent = session.get(Agent, binding.agent_id)
            task = session.get(Task, row.task_id) if row.task_id else None
            delivery = (
                session.execute(
                    select(Delivery).where(Delivery.inbound_id == row.id).order_by(Delivery.created_at.desc())
                )
                .scalars()
                .first()
            )
            stage, execution, delivered, error = _stage(row, task, delivery)
            out.append(
                RunOut(
                    id=ids.encode("channel_run", row.id),
                    task_id=ids.encode("task", row.task_id) if row.task_id else None,
                    binding_id=ids.encode("channel_binding", binding.id),
                    binding_name=binding.name,
                    platform=binding.platform,
                    agent_id=ids.encode("agent", binding.agent_id),
                    agent_name=agent.name if agent else "",
                    source={
                        "sender": row.sender_name or row.sender_ref,
                        "conversation": row.conversation_ref,
                        "kind": row.conversation_kind,
                        "message": row.text,
                        "mention": row.mentioned,
                    },
                    stage=stage,
                    execution_status=execution,
                    delivery_status=delivered,
                    delivery_attempts=delivery.attempts if delivery else 0,
                    error_code=error,
                    reply={"text": delivery.text, "at": delivery.updated_at.isoformat()}
                    if delivery and delivery.status == "delivered"
                    else None,
                    event_id=row.platform_event_id,
                    replay_count=row.replay_count,
                    created_at=row.created_at,
                )
            )
        return out


@router.post("/tenants/{tenant_id}/channel-runs/{run_id}/{action}", summary="Retry, cancel or replay a channel run")
def run_action(tenant_id: str, run_id: str, action: str, principal: Authenticated, state: State) -> dict[str, Any]:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id), write=True) as (
        session,
        actor,
    ):
        row = session.get(InboundMessage, decode("channel_run", run_id), with_for_update=True)
        if (
            row is None
            or row.tenant_id != actor.tenant.id
            or not (actor.is_manager or row.membership_id == actor.membership.id)
        ):
            raise not_found()
        task = session.get(Task, row.task_id, with_for_update=True) if row.task_id else None
        if action == "replay":
            # The platform redelivered the same event: it is recorded, never processed twice.
            row.replay_count += 1
            service._changed(session, row)
            return {"message": "channel.duplicate", "replay_count": row.replay_count}
        if action == "cancel" and task is not None:
            tasks.request_cancel(session, actor, task)
            return {"status": task.status}
        if action == "retry-execution" and task is not None and task.status in resume.RETRYABLE:
            resume.requeue(session, task, [actor.membership.id])
            for old in session.execute(
                select(Delivery).where(Delivery.inbound_id == row.id, Delivery.purpose == "result")
            ).scalars():
                session.delete(old)  # the next result gets a fresh delivery
            return {"status": "queued"}
        if action == "retry-delivery":
            delivery = (
                session.execute(
                    select(Delivery)
                    .where(Delivery.inbound_id == row.id)
                    .order_by(Delivery.created_at.desc())
                    .with_for_update()
                )
                .scalars()
                .first()
            )
            if delivery is not None and delivery.status in ("failed", "unknown", "blocked"):
                binding = session.get(ChannelBinding, row.binding_id)
                assert binding is not None
                delivery.binding_revision = binding.revision  # a person decided to reply under the current rules
                service.requeue_delivery(session, delivery)
                return {"status": "queued"}
        raise conflict("INVALID_STATE", "This action is not available for the run now.")


# ------------------------------------------------------------------------------------------ ingress


def _resolve(state: Any, platform: str, public_id: str) -> tuple[uuid.UUID, uuid.UUID]:
    with state.db.transaction() as session:
        row = session.execute(
            text("SELECT tenant_id, id FROM workx_binding_by_public_id(:p)"), {"p": public_id}
        ).first()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Not found.")
    return row.tenant_id, row.id


@router.post(
    "/channels/{platform}/{public_id}/events",
    summary="Platform callbacks (Feishu events, WeCom messages); authenticated by the platform's signature",
    operation_id="channel_ingress_post",
)
@router.get(
    "/channels/{platform}/{public_id}/events",
    summary="Platform URL verification (WeCom echostr)",
    operation_id="channel_ingress_get",
)
async def ingress(platform: str, public_id: str, request: Request, state: State) -> Response:
    from starlette.concurrency import run_in_threadpool

    if platform not in ("feishu", "wecom") or len(public_id) > 64:
        raise ApiError(404, "NOT_FOUND", "Not found.")
    body = await request.body()
    if len(body) > INGRESS_MAX_BYTES:
        raise ApiError(413, "TOO_LARGE", "Payload too large.")

    def handle() -> Response:
        tenant_id, binding_id = _resolve(state, platform, public_id)
        opened = broker(state).channel_open(
            {
                "tenant_id": str(tenant_id),
                "binding_id": str(binding_id),
                "method": request.method,
                "headers": {
                    k: v for k, v in request.headers.items() if k.lower().startswith(("x-lark", "content-type"))
                },
                "query": dict(request.query_params),
                "body_b64": base64.b64encode(body).decode(),
            }
        )
        if opened["kind"] == "challenge":
            media = "application/json" if platform == "feishu" else "text/plain"
            return Response(opened["body"], media_type=media)
        with state.db.transaction(tenant_id=tenant_id) as session:
            binding = session.get(ChannelBinding, binding_id)
            assert binding is not None
            if platform == "feishu":
                message = platforms.feishu(opened["payload"], (binding.config or {}).get("bot_open_id"))
            else:
                message = platforms.wecom(opened["payload"], str((binding.config or {}).get("corp_id", "")))
            if message is not None and message.event_id:
                service.record_inbound(session, binding, message)
        return Response(
            "success" if platform == "wecom" else "{}",
            media_type="text/plain" if platform == "wecom" else "application/json",
        )

    return await run_in_threadpool(handle)
