"""Runtime routes: task event history/stream, retry, approval decisions, workspace budgets (Part 4 §7, §10)."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from workx.core import ids
from workx.core.errors import ApiError, conflict, forbidden
from workx.core.orm import utcnow
from workx.domains.audit import service as audit
from workx.domains.identity.auth import Authenticated, State
from workx.domains.resources import events as tenant_events
from workx.domains.resources.common import load, require
from workx.domains.runtime import resume
from workx.domains.runtime.models import Approval, TaskEvent, TenantBudget
from workx.domains.tasks import service as tasks
from workx.domains.tasks.models import Task
from workx.domains.tenancy import service as tenancy
from workx.domains.tenancy.api import tenant_uuid
from workx.platform.web import AppState

router = APIRouter(tags=["runtime"])


class TaskEventOut(BaseModel):
    seq: int
    type: str
    payload: dict[str, Any]
    created_at: datetime


def _events_after(state: AppState, user_id: Any, tenant_id: Any, task_external: str, after: int) -> list[TaskEvent]:
    with tenancy.tenant_scope(state.db, user_id=user_id, tenant_id=tenant_id) as (session, actor):
        task = load(session, Task, actor, task_external, "task")
        require(session, actor, "read", "task", task, tasks.implicit_actions(session, actor, task))
        return list(
            session.execute(
                select(TaskEvent)
                .where(TaskEvent.task_id == task.id, TaskEvent.seq > after)
                .order_by(TaskEvent.seq)
                .limit(500)
            ).scalars()
        )


@router.get(
    "/tenants/{tenant_id}/tasks/{task_id}/events",
    summary="Task events (JSON, or SSE with Accept: text/event-stream)",
    response_model=None,
)
async def task_events(
    tenant_id: str,
    task_id: str,
    request: Request,
    principal: Authenticated,
    state: State,
    after: int = 0,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    max_seconds: Annotated[float | None, Query(ge=0.5, le=3600, include_in_schema=False)] = None,
) -> Any:
    tid = tenant_uuid(tenant_id)
    if last_event_id and last_event_id.isdigit():
        after = int(last_event_id)
    first = await run_in_threadpool(_events_after, state, principal.user_id, tid, task_id, after)
    if "text/event-stream" not in request.headers.get("accept", ""):
        return [TaskEventOut(seq=e.seq, type=e.type, payload=e.payload, created_at=e.created_at) for e in first]

    async def body() -> AsyncIterator[str]:
        position, started = after, time.monotonic()
        batch = first
        while True:
            for event in batch:
                position = event.seq
                data = {
                    "seq": event.seq,
                    "type": event.type,
                    "payload": event.payload,
                    "created_at": event.created_at.isoformat(),
                }
                yield f"id: {event.seq}\nevent: {event.type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                if event.type in (
                    "task.succeeded",
                    "task.failed",
                    "task.cancelled",
                    "task.interrupted",
                    "task.needs_auth",
                ):
                    return
            if (max_seconds and time.monotonic() - started > max_seconds) or await request.is_disconnected():
                return
            await asyncio.sleep(0.5)
            try:
                batch = await run_in_threadpool(_events_after, state, principal.user_id, tid, task_id, position)
            except ApiError:
                yield 'event: stream.closed\ndata: {"reason": "access_ended"}\n\n'
                return

    return StreamingResponse(body(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})


@router.post("/tenants/{tenant_id}/tasks/{task_id}/retry", status_code=202, summary="Run a finished task again")
def retry(tenant_id: str, task_id: str, principal: Authenticated, state: State) -> dict[str, str]:
    with tenancy.tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id), write=True) as (
        session,
        actor,
    ):
        task = load(session, Task, actor, task_id, "task", lock=True)
        require(session, actor, "use", "task", task, tasks.implicit_actions(session, actor, task))
        if task.status not in resume.RETRYABLE:
            raise conflict(
                "INVALID_STATE",
                "Only failed, interrupted, cancelled or blocked tasks can be retried.",
                {"status": task.status},
            )
        unknown = resume.unknown_operations(session, task.id)
        if unknown:
            raise conflict(
                "RECONCILIATION_REQUIRED",
                "Some actions may have happened already; check them before retrying.",
                {"tools": unknown},
            )
        resume.requeue(session, task, [actor.membership.id])
        audit.record(
            session,
            "task.retried",
            tenant_id=actor.tenant.id,
            actor_user_id=actor.user_id,
            actor_membership_id=actor.membership.id,
            target_type="task",
            target_id=task.id,
        )
        return {"id": task_id, "status": "queued"}


class ApprovalOut(BaseModel):
    id: str
    tool: str
    summary: str
    status: str
    expires_at: datetime


@router.get("/tenants/{tenant_id}/tasks/{task_id}/approvals", summary="Approval requests for a task")
def approvals(tenant_id: str, task_id: str, principal: Authenticated, state: State) -> list[ApprovalOut]:
    with tenancy.tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id)) as (
        session,
        actor,
    ):
        task = load(session, Task, actor, task_id, "task")
        require(session, actor, "read", "task", task, tasks.implicit_actions(session, actor, task))
        rows = session.execute(
            select(Approval).where(Approval.task_id == task.id).order_by(Approval.created_at)
        ).scalars()
        return [
            ApprovalOut(
                id=ids.encode("approval", a.id),
                tool=a.tool,
                summary=a.summary,
                status=a.status,
                expires_at=a.expires_at,
            )
            for a in rows
        ]


class DecisionIn(BaseModel):
    decision: Literal["approve", "reject"]


@router.post(
    "/tenants/{tenant_id}/tasks/{task_id}/approvals/{approval_id}/decision", summary="Approve or reject an action"
)
def decide(
    tenant_id: str, task_id: str, approval_id: str, body: DecisionIn, principal: Authenticated, state: State
) -> ApprovalOut:
    with tenancy.tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id), write=True) as (
        session,
        actor,
    ):
        task = load(session, Task, actor, task_id, "task", lock=True)
        actions = require(session, actor, "read", "task", task, tasks.implicit_actions(session, actor, task))
        if "approve" not in actions:
            raise forbidden("Only the person who started the task, or someone granted approval, can decide.")
        approval = load(session, Approval, actor, approval_id, "approval", lock=True)
        if approval.task_id != task.id:
            raise ApiError(404, "NOT_FOUND", "The resource does not exist or you do not have access to it.")
        if approval.status != "pending":
            raise conflict("INVALID_STATE", "This request was already decided.", {"status": approval.status})
        if approval.expires_at <= utcnow():
            approval.status = "expired"
            raise conflict("APPROVAL_EXPIRED", "This request expired. Retry the task to ask again.")
        approval.status = "approved" if body.decision == "approve" else "rejected"
        approval.decided_by_membership_id, approval.decided_at = actor.membership.id, utcnow()
        audit.record(
            session,
            f"approval.{approval.status}",
            tenant_id=actor.tenant.id,
            actor_user_id=actor.user_id,
            actor_membership_id=actor.membership.id,
            target_type="approval",
            target_id=approval.id,
            data={"tool": approval.tool},
        )
        tenant_events.publish(
            session, actor.tenant.id, "task.updated", {"task_id": task_id, "step": "approval.decided"}
        )
        return ApprovalOut(
            id=approval_id,
            tool=approval.tool,
            summary=approval.summary,
            status=approval.status,
            expires_at=approval.expires_at,
        )


class BudgetIn(BaseModel):
    monthly_token_limit: int | None = Field(default=None, ge=0)
    per_task_token_limit: int | None = Field(default=None, ge=0)


@router.get("/tenants/{tenant_id}/budgets", summary="Token budgets")
def get_budget(tenant_id: str, principal: Authenticated, state: State) -> BudgetIn:
    with tenancy.tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id)) as (
        session,
        actor,
    ):
        budget = session.get(TenantBudget, actor.tenant.id)
        return BudgetIn(
            monthly_token_limit=budget.monthly_token_limit if budget else None,
            per_task_token_limit=budget.per_task_token_limit if budget else None,
        )


@router.put("/tenants/{tenant_id}/budgets", summary="Set token budgets (owners and admins)")
def put_budget(tenant_id: str, body: BudgetIn, principal: Authenticated, state: State) -> BudgetIn:
    with tenancy.tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id), write=True) as (
        session,
        actor,
    ):
        if not (actor.is_manager or actor.tenant.type == "personal"):
            raise forbidden("Only owners and admins can set budgets.")
        budget = session.get(TenantBudget, actor.tenant.id) or TenantBudget(tenant_id=actor.tenant.id)
        budget.monthly_token_limit, budget.per_task_token_limit, budget.updated_at = (
            body.monthly_token_limit,
            body.per_task_token_limit,
            utcnow(),
        )
        session.add(budget)
        audit.record(
            session,
            "budget.changed",
            tenant_id=actor.tenant.id,
            actor_user_id=actor.user_id,
            actor_membership_id=actor.membership.id,
            data=body.model_dump(),
        )
        return body
