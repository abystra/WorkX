"""Automations scheduler (R2): due automations become tasks of their owner (Part 4, Part 10 queues).

* At most one run per (automation, slot); the slot is the automation's ``next_run_at``.
* After downtime only the latest missed slot runs once (no burst of catch-up runs); the next slot is computed
  from now.
* The run acts as the owner: if the owner is no longer an active member, or no workmate is usable, the run is
  recorded as skipped with a reason.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from workx.core import ids
from workx.core.orm import utcnow
from workx.domains.agents.models import Agent
from workx.domains.authz import policy
from workx.domains.identity.models import User
from workx.domains.resources import events
from workx.domains.resources.models import Automation, AutomationRun
from workx.domains.resources.schedule import next_run
from workx.domains.tasks import service as tasks
from workx.domains.tenancy.models import Membership, Tenant
from workx.domains.tenancy.service import Actor
from workx.platform import jobs

BATCH = 100


def _agent(session: Session, actor: Actor, automation: Automation) -> Agent | None:
    candidates = (
        [session.get(Agent, automation.agent_id)]
        if automation.agent_id
        else session.execute(
            select(Agent)
            .where(Agent.tenant_id == actor.tenant.id, Agent.deleted_at.is_(None))
            .order_by(Agent.owner_membership_id != actor.membership.id, Agent.created_at)
        )
        .scalars()
        .all()
    )
    for agent in candidates:
        if (
            agent is not None
            and agent.deleted_at is None
            and "use" in policy.allowed_actions(session, actor, "agent", agent)
        ):
            return agent
    return None


def run_due(session: Session, automation_id: uuid.UUID, now: datetime) -> str:
    automation = session.execute(
        select(Automation).where(Automation.id == automation_id).with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if automation is None or not automation.enabled or automation.deleted_at or not automation.next_run_at:
        return "skipped"
    if automation.next_run_at > now:
        return "not_due"
    slot = automation.next_run_at
    automation.last_run_at = slot
    automation.next_run_at = next_run(automation.schedule, automation.timezone, now)
    inserted = session.execute(
        insert(AutomationRun)
        .values(
            id=ids.uuid7(), tenant_id=automation.tenant_id, automation_id=automation.id, slot_at=slot, status="created"
        )
        .on_conflict_do_nothing(index_elements=["automation_id", "slot_at"])
        .returning(AutomationRun.id)
    ).scalar()
    if inserted is None:
        return "duplicate"
    run = session.get(AutomationRun, inserted)
    assert run is not None
    member = session.get(Membership, automation.owner_membership_id)
    tenant = session.get(Tenant, automation.tenant_id)
    user = session.get(User, member.user_id) if member else None
    if member is None or member.status != "active" or tenant is None or user is None:
        run.status, run.reason = "skipped", "owner_inactive"
        return "skipped"
    actor = Actor(user_id=user.id, tenant=tenant, membership=member)
    agent = _agent(session, actor, automation)
    prompt = (automation.prompt or automation.description or automation.name).strip()
    if agent is None or not prompt:
        run.status, run.reason = "skipped", "no_agent" if agent is None else "no_prompt"
        return "skipped"
    task = tasks.create(
        session,
        actor,
        agent=agent,
        prompt=prompt,
        project_id=None,
        model_tier="auto",
        capabilities=[],
        name=f"{automation.name} · {slot.astimezone(UTC):%Y-%m-%d %H:%M}",
    )
    task.input = {**task.input, "automation": {"id": str(automation.id), "slot": slot.isoformat()}}
    run.task_id = task.id
    events.publish(
        session,
        automation.tenant_id,
        "automation.ran",
        {"automation_id": ids.encode("automation", automation.id), "task_id": ids.encode("task", task.id)},
        audience=[member.id],
    )
    return "created"


@jobs.handler("automation_tick")
def automation_tick(ctx: jobs.JobContext, job: jobs.Job) -> None:
    now = utcnow()
    with ctx.db.transaction() as session:
        due = session.execute(
            text("SELECT tenant_id, id FROM workx_due_automations(:now, :n)"), {"now": now, "n": BATCH}
        ).all()
    for tenant_id, automation_id in due:
        with ctx.db.transaction(tenant_id=tenant_id) as session:
            run_due(session, automation_id, now)


def schedule_tick(ctx: jobs.JobContext, now: datetime | None = None) -> None:
    """Enqueued once per minute by every worker (scheduler and knowledge re-sync); the dedupe key makes each
    run once."""
    minute = (now or datetime.now(UTC)).replace(second=0, microsecond=0)
    with ctx.db.transaction() as session:
        for kind in ("automation_tick", "knowledge_sync_tick"):
            jobs.enqueue(session, kind, {}, dedupe_key=f"{kind}:{minute.isoformat()}", max_attempts=1)
