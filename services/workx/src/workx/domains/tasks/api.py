"""Task routes: create (Idempotency-Key), list, detail with messages, per-member state, follow-ups, cancel."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Header, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from workx.core import ids
from workx.core.errors import not_found, validation
from workx.core.orm import utcnow
from workx.domains.agents.models import Agent
from workx.domains.authz import policy
from workx.domains.identity.auth import Authenticated, State
from workx.domains.resources import events
from workx.domains.resources.common import active_member_ids, decode, load, maybe, require
from workx.domains.resources.models import Project
from workx.domains.resources.projects import PROJECT_MEMBER_ACTIONS, project_ids_for
from workx.domains.tasks import service
from workx.domains.tasks.models import Task, TaskMemberState, TaskMessage
from workx.domains.tenancy.api import tenant_uuid
from workx.domains.tenancy.service import Actor, tenant_scope
from workx.platform import idempotency

router = APIRouter(tags=["tasks"])
IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key")]


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    file_id: str | None
    created_at: datetime


class TaskOut(BaseModel):
    id: str
    name: str
    status: str
    status_reason: str | None
    kind: str
    agent_id: str
    agent_version_id: str | None
    project_id: str | None
    model_tier: str
    capabilities: list[str]
    prompt: str
    created_by: str
    assignee_id: str | None
    supporting_agent_ids: list[str]
    review_state: str
    pinned: bool
    archived: bool
    unread: bool
    visibility: str
    actions: list[str]
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None
    # Conversation summary for list views: the latest answer and the follow-ups after the first request.
    answer: str | None = None
    answer_file_id: str | None = None
    follow_ups: list[str] = []
    messages: list[MessageOut] | None = None


def _summary(messages: list[TaskMessage]) -> dict[str, Any]:
    answers = [m for m in messages if m.role == "assistant"]
    users = [m for m in messages if m.role == "user"]
    latest = answers[-1] if answers else None
    return {
        "answer": latest.content if latest else None,
        "answer_file_id": maybe("file", latest.file_id) if latest else None,
        "follow_ups": [m.content for m in users[1:]],
    }


def _messages_by_task(session: Session, task_ids: list[Any]) -> dict[Any, list[TaskMessage]]:
    grouped: dict[Any, list[TaskMessage]] = {t: [] for t in task_ids}
    if task_ids:
        for message in session.execute(
            select(TaskMessage).where(TaskMessage.task_id.in_(task_ids)).order_by(TaskMessage.created_at)
        ).scalars():
            grouped[message.task_id].append(message)
    return grouped


def _out(
    task: Task,
    state: TaskMemberState | None,
    actions: set[str],
    messages: list[TaskMessage] | None = None,
    *,
    include_messages: bool = False,
) -> TaskOut:
    return TaskOut(
        **_summary(messages or []),
        id=ids.encode("task", task.id),
        name=task.name,
        status=task.status,
        status_reason=task.status_reason,
        kind=task.kind,
        agent_id=ids.encode("agent", task.agent_id),
        agent_version_id=maybe("agent_version", task.agent_version_id),
        project_id=maybe("project", task.project_id),
        model_tier=task.model_tier,
        capabilities=list(task.capabilities),
        prompt=str(task.input.get("text", "")),
        created_by=ids.encode("membership", task.created_by_membership_id),
        assignee_id=maybe("membership", task.assignee_membership_id),
        supporting_agent_ids=[ids.encode("agent", a) for a in task.supporting_agent_ids],
        review_state=task.review_state,
        pinned=bool(state and state.pinned),
        archived=bool(state and state.archived),
        unread=bool(state and state.unread),
        visibility=task.visibility,
        actions=sorted(actions),
        created_at=task.created_at,
        updated_at=task.updated_at,
        finished_at=task.finished_at,
        messages=[
            MessageOut(
                id=ids.encode("event", m.id),
                role=m.role,
                content=m.content,
                file_id=maybe("file", m.file_id),
                created_at=m.created_at,
            )
            for m in messages or []
        ]
        if include_messages
        else None,
    )


def _actions(session: Session, actor: Actor, task: Task) -> set[str]:
    return policy.allowed_actions(session, actor, "task", task) | service.implicit_actions(session, actor, task)


@router.get("/tenants/{tenant_id}/tasks", summary="Tasks you started, are assigned, or can see through projects/grants")
def list_tasks(tenant_id: str, principal: Authenticated, state: State, include_archived: bool = True) -> list[TaskOut]:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id)) as (session, actor):
        rows = (
            session.execute(
                select(Task)
                .where(
                    Task.tenant_id == actor.tenant.id,
                    Task.deleted_at.is_(None),
                    service.readable_clause(session, actor),
                )
                .order_by(Task.created_at.desc())
                .limit(500)
            )
            .scalars()
            .all()
        )
        states = service.state_for(session, actor, [t.id for t in rows])
        conversations = _messages_by_task(session, [t.id for t in rows])
        out = [_out(t, states.get(t.id), _actions(session, actor, t), conversations[t.id]) for t in rows]
        return out if include_archived else [t for t in out if not t.archived]


class TaskIn(BaseModel):
    agent_id: str
    prompt: str = Field(max_length=service.PROMPT_MAX)
    project_id: str | None = None
    model_tier: str = "auto"
    capabilities: list[str] = Field(default_factory=list)
    name: str | None = Field(default=None, max_length=120)


@router.post("/tenants/{tenant_id}/tasks", status_code=202, summary="Start a task (queued for the orchestrator)")
def create_task(
    tenant_id: str, body: TaskIn, principal: Authenticated, state: State, idempotency_key: IdempotencyKey = None
) -> JSONResponse:
    tid = tenant_uuid(tenant_id)
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tid, write=True) as (session, actor):

        def work() -> tuple[int, dict[str, Any]]:
            agent = load(session, Agent, actor, body.agent_id, "agent")
            require(session, actor, "use", "agent", agent)
            project_id = None
            if body.project_id:
                project = load(session, Project, actor, body.project_id, "project")
                extra = PROJECT_MEMBER_ACTIONS if project.id in project_ids_for(session, actor) else set()
                require(session, actor, "use", "project", project, extra)
                project_id = project.id
            task = service.create(
                session,
                actor,
                agent=agent,
                prompt=body.prompt,
                project_id=project_id,
                model_tier=body.model_tier,
                capabilities=body.capabilities,
                name=body.name,
            )
            session.flush()
            states = service.state_for(session, actor, [task.id])
            return 202, _out(task, states.get(task.id), set(policy.ACTIONS)).model_dump(mode="json")

        status, payload = idempotency.run(
            session,
            key=idempotency_key,
            scope=str(tid),
            principal_id=principal.user_id,
            route="POST /tenants/{t}/tasks",
            body=body.model_dump(),
            work=work,
        )
    return JSONResponse(
        payload, status_code=status, headers={"Location": f"/api/v1/tenants/{tenant_id}/tasks/{payload['id']}"}
    )


@router.get("/tenants/{tenant_id}/tasks/{task_id}", summary="Task with its conversation")
def get_task(tenant_id: str, task_id: str, principal: Authenticated, state: State) -> TaskOut:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id)) as (session, actor):
        task = load(session, Task, actor, task_id, "task")
        actions = require(session, actor, "read", "task", task, service.implicit_actions(session, actor, task))
        messages = (
            session.execute(select(TaskMessage).where(TaskMessage.task_id == task.id).order_by(TaskMessage.created_at))
            .scalars()
            .all()
        )
        return _out(
            task,
            service.state_for(session, actor, [task.id]).get(task.id),
            actions,
            list(messages),
            include_messages=True,
        )


class TaskPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    pinned: bool | None = None
    archived: bool | None = None
    unread: bool | None = None
    assignee_id: str | None = None
    supporting_agent_ids: list[str] | None = None
    review_state: str | None = Field(default=None, pattern="^(review|accepted)$")


@router.patch(
    "/tenants/{tenant_id}/tasks/{task_id}", summary="Rename, assign, review, or set your own pin/archive/unread"
)
def patch_task(tenant_id: str, task_id: str, body: TaskPatch, principal: Authenticated, state: State) -> TaskOut:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id), write=True) as (
        session,
        actor,
    ):
        task = load(session, Task, actor, task_id, "task", lock=True)
        actions = require(session, actor, "read", "task", task, service.implicit_actions(session, actor, task))
        fields = body.model_fields_set
        personal = {
            k: getattr(body, k)
            for k in ("pinned", "archived", "unread")
            if k in fields and getattr(body, k) is not None
        }
        if personal:
            service.set_state(session, actor, task, **personal)
        shared = fields - {"pinned", "archived", "unread"}
        if shared:
            in_project = task.project_id is not None and task.project_id in project_ids_for(session, actor)
            if "edit" not in actions and not in_project:
                require(session, actor, "edit", "task", task)
            if body.name is not None:
                name = " ".join(body.name.split())
                if not name:
                    raise validation("Name is required.", data={"field": "name"})
                task.name = name
            if "assignee_id" in fields:
                assignee = decode("membership", body.assignee_id) if body.assignee_id else None
                if assignee is not None and assignee not in active_member_ids(session, actor):
                    raise validation("Choose an active member.", data={"field": "assignee_id"})
                task.assignee_membership_id = assignee
            if body.supporting_agent_ids is not None:
                agent_ids = [decode("agent", a) for a in body.supporting_agent_ids]
                for agent_id in agent_ids:
                    agent = session.get(Agent, agent_id)
                    if agent is None or agent.deleted_at is not None:
                        raise not_found()
                task.supporting_agent_ids = agent_ids
            if body.review_state is not None:
                if task.status != "succeeded" and body.review_state == "accepted":
                    raise validation("Only finished tasks can be accepted.", data={"field": "review_state"})
                task.review_state = body.review_state
            task.row_version += 1
            events.publish(session, actor.tenant.id, "task.updated", {"task_id": task_id})
        session.flush()
        return _out(task, service.state_for(session, actor, [task.id]).get(task.id), actions)


class MessageIn(BaseModel):
    prompt: str = Field(max_length=service.PROMPT_MAX)


@router.post("/tenants/{tenant_id}/tasks/{task_id}/messages", status_code=202, summary="Send a follow-up")
def add_message(tenant_id: str, task_id: str, body: MessageIn, principal: Authenticated, state: State) -> TaskOut:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id), write=True) as (
        session,
        actor,
    ):
        task = load(session, Task, actor, task_id, "task", lock=True)
        actions = require(session, actor, "use", "task", task, service.implicit_actions(session, actor, task))
        service.add_message(session, actor, task, body.prompt)
        session.flush()
        return _out(task, service.state_for(session, actor, [task.id]).get(task.id), actions)


@router.post("/tenants/{tenant_id}/tasks/{task_id}/cancel", status_code=202, summary="Cancel a task")
def cancel(tenant_id: str, task_id: str, principal: Authenticated, state: State) -> TaskOut:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id), write=True) as (
        session,
        actor,
    ):
        task = load(session, Task, actor, task_id, "task", lock=True)
        actions = require(session, actor, "use", "task", task, service.implicit_actions(session, actor, task))
        service.request_cancel(session, actor, task)
        session.flush()
        return _out(task, service.state_for(session, actor, [task.id]).get(task.id), actions)


@router.delete("/tenants/{tenant_id}/tasks/{task_id}", status_code=204, summary="Delete a task")
def delete_task(tenant_id: str, task_id: str, principal: Authenticated, state: State) -> Response:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id), write=True) as (
        session,
        actor,
    ):
        task = load(session, Task, actor, task_id, "task", lock=True)
        require(session, actor, "delete", "task", task)
        task.deleted_at = utcnow()
    return Response(status_code=204)
