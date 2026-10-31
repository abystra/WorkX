"""Task creation and access rules. Execution (attempts, orchestrator, runner) is added in P-05.

Read access: the initiator (owner), the assignee, active members of the task's project, and grant holders.
``created_by_membership_id`` (whose authorizations the run uses) never changes on reassignment (Part 3 §5).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from workx.core import ids
from workx.core.errors import conflict, validation
from workx.core.orm import utcnow
from workx.domains.agents.catalog import MODEL_TIER_IDS, SKILL_IDS
from workx.domains.agents.models import Agent
from workx.domains.audit import service as audit
from workx.domains.authz import policy
from workx.domains.resources import events
from workx.domains.resources.projects import project_ids_for
from workx.domains.tasks.models import Task, TaskMemberState, TaskMessage, WorkSession
from workx.domains.tenancy.service import Actor
from workx.platform import outbox

TERMINAL = {"succeeded", "failed", "cancelled", "interrupted"}
PROMPT_MAX = 20_000


def implicit_actions(session: Session, actor: Actor, task: Task) -> set[str]:
    actions: set[str] = set()
    if task.assignee_membership_id == actor.membership.id:
        actions |= {"read", "use", "comment", "edit"}
    if task.project_id and task.project_id in project_ids_for(session, actor):
        actions |= {"read", "comment"}
    return actions


def readable_clause(session: Session, actor: Actor) -> ColumnElement[bool]:
    mine = project_ids_for(session, actor)
    clauses = [
        policy.readable(actor, "task", id_column=Task.id, owner_column=Task.owner_membership_id, project_ids=mine),
        Task.assignee_membership_id == actor.membership.id,
    ]
    if mine:
        clauses.append(Task.project_id.in_(mine))
    return or_(*clauses)


def derive_name(prompt: str) -> str:
    first = " ".join(prompt.split())
    return first if len(first) <= 40 else first[:40].rstrip() + "…"


def create(
    session: Session,
    actor: Actor,
    *,
    agent: Agent,
    prompt: str,
    project_id: uuid.UUID | None,
    model_tier: str,
    capabilities: list[str],
    name: str | None,
    kind: str = "work",
) -> Task:
    prompt = prompt.strip()
    if not prompt:
        raise validation("Describe the task.", data={"field": "prompt"})
    if len(prompt) > PROMPT_MAX:
        raise validation("The request is too long.", data={"field": "prompt"})
    if model_tier not in MODEL_TIER_IDS:
        raise validation("Unknown model tier.", data={"field": "model_tier"})
    unknown = set(capabilities) - SKILL_IDS
    if unknown:
        raise validation(f"Unknown capability: {', '.join(sorted(unknown))}", data={"field": "capabilities"})
    if agent.current_version_id is None:
        raise conflict("AGENT_NOT_PUBLISHED", "This workmate has no published version yet.")
    work_session = WorkSession(
        id=ids.uuid7(), tenant_id=actor.tenant.id, project_id=project_id, owner_membership_id=actor.membership.id
    )
    session.add(work_session)
    session.flush()
    task = Task(
        id=ids.uuid7(),
        tenant_id=actor.tenant.id,
        session_id=work_session.id,
        agent_id=agent.id,
        agent_version_id=agent.current_version_id,
        project_id=project_id,
        name=(name or derive_name(prompt))[:120],
        kind=kind,
        status="queued",
        model_tier=model_tier,
        capabilities=sorted(set(capabilities)),
        input={"text": prompt},
        created_by_membership_id=actor.membership.id,
        assignee_membership_id=actor.membership.id,
        owner_membership_id=actor.membership.id,
    )
    session.add(task)
    session.flush()
    session.add(
        TaskMessage(
            id=ids.uuid7(),
            tenant_id=actor.tenant.id,
            task_id=task.id,
            role="user",
            content=prompt,
            author_membership_id=actor.membership.id,
            created_at=utcnow(),
        )
    )
    set_state(session, actor, task, unread=False)
    audit.record(
        session,
        "task.created",
        tenant_id=actor.tenant.id,
        actor_user_id=actor.user_id,
        actor_membership_id=actor.membership.id,
        target_type="task",
        target_id=task.id,
        data={"agent_version_id": str(agent.current_version_id), "model_tier": model_tier},
    )
    outbox.emit(
        session, "task.queued", {"task_id": str(task.id), "tenant_id": str(actor.tenant.id)}, tenant_id=actor.tenant.id
    )
    events.publish(
        session,
        actor.tenant.id,
        "task.queued",
        {"task_id": ids.encode("task", task.id)},
        audience=[actor.membership.id],
    )
    return task


def set_state(session: Session, actor: Actor, task: Task, **values: Any) -> None:
    session.execute(
        insert(TaskMemberState)
        .values(tenant_id=actor.tenant.id, task_id=task.id, membership_id=actor.membership.id, **values)
        .on_conflict_do_update(
            index_elements=["tenant_id", "task_id", "membership_id"], set_={**values, "updated_at": utcnow()}
        )
    )


def state_for(session: Session, actor: Actor, task_ids: list[uuid.UUID]) -> dict[uuid.UUID, TaskMemberState]:
    if not task_ids:
        return {}
    rows = session.execute(
        select(TaskMemberState).where(
            TaskMemberState.membership_id == actor.membership.id, TaskMemberState.task_id.in_(task_ids)
        )
    ).scalars()
    return {r.task_id: r for r in rows}


def add_message(session: Session, actor: Actor, task: Task, prompt: str) -> TaskMessage:
    prompt = prompt.strip()
    if not prompt or len(prompt) > PROMPT_MAX:
        raise validation("Write a message.", data={"field": "prompt"})
    message = TaskMessage(
        id=ids.uuid7(),
        tenant_id=actor.tenant.id,
        task_id=task.id,
        role="user",
        content=prompt,
        author_membership_id=actor.membership.id,
        created_at=utcnow(),
    )
    session.add(message)
    if task.status in TERMINAL:
        # A follow-up starts a new run of the same task (P-05 creates the attempt).
        task.status = "queued"
        task.finished_at = None
        task.cancel_requested_at = None
        outbox.emit(
            session,
            "task.queued",
            {"task_id": str(task.id), "tenant_id": str(actor.tenant.id), "follow_up": True},
            tenant_id=actor.tenant.id,
        )
    task.row_version += 1
    events.publish(session, actor.tenant.id, "task.updated", {"task_id": ids.encode("task", task.id)})
    return message


def request_cancel(session: Session, actor: Actor, task: Task) -> None:
    if task.status in TERMINAL:
        raise conflict("INVALID_STATE", "This task has already finished.", {"status": task.status})
    task.cancel_requested_at = utcnow()
    # Gateways reject the running Attempt's tickets from now on (Part 4 §10.1); the orchestrator stops the Runner.
    from workx.domains.runtime.leases import revoke_for_task

    revoke_for_task(session, task.id)
    if task.status == "queued":
        task.status = "cancelled"
        task.finished_at = utcnow()
    outbox.emit(
        session,
        "task.cancel_requested",
        {"task_id": str(task.id), "tenant_id": str(actor.tenant.id)},
        tenant_id=actor.tenant.id,
    )
    events.publish(
        session,
        actor.tenant.id,
        "task." + ("cancelled" if task.status == "cancelled" else "updated"),
        {"task_id": ids.encode("task", task.id)},
    )
    audit.record(
        session,
        "task.cancel_requested",
        tenant_id=actor.tenant.id,
        actor_user_id=actor.user_id,
        actor_membership_id=actor.membership.id,
        target_type="task",
        target_id=task.id,
    )
