"""Agent routes (prototype "workmates")."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select

from workx.core import ids
from workx.core.orm import utcnow
from workx.domains.agents import service
from workx.domains.agents.catalog import MODEL_TIERS, SKILLS
from workx.domains.agents.models import Agent, AgentVersion
from workx.domains.audit import service as audit
from workx.domains.authz import policy
from workx.domains.authz.models import ResourceGrant
from workx.domains.identity.auth import Authenticated, State
from workx.domains.resources import events
from workx.domains.resources.common import load, require
from workx.domains.tasks.models import Task
from workx.domains.tenancy.api import tenant_uuid
from workx.domains.tenancy.service import Actor, tenant_scope

router = APIRouter(tags=["agents"])
KIND = "agent"


class AgentOut(BaseModel):
    id: str
    name: str
    description: str
    tag: str
    avatar: int
    instructions: str
    context: str
    model_tier: str
    skills: list[str]
    knowledge_source_ids: list[str]
    task_count: int
    version: int | None
    visibility: str
    resource_owner_id: str
    actions: list[str]
    updated_at: datetime


def _out(session: Any, actor: Actor, agent: Agent, actions: set[str], version: int | None = None) -> AgentOut:
    task_count = session.execute(
        select(func.count())
        .select_from(Task)
        .where(
            Task.tenant_id == actor.tenant.id,
            Task.agent_id == agent.id,
            Task.deleted_at.is_(None),
            Task.owner_membership_id == actor.membership.id,
        )
    ).scalar_one()
    if version is None and agent.current_version_id:
        version = session.execute(
            select(AgentVersion.version_no).where(AgentVersion.id == agent.current_version_id)
        ).scalar_one_or_none()
    return AgentOut(
        id=ids.encode(KIND, agent.id),
        name=agent.name,
        description=agent.description,
        tag=agent.tag,
        avatar=agent.avatar,
        instructions=agent.instructions,
        context=agent.context_md,
        model_tier=agent.model_tier,
        skills=list(agent.skills),
        knowledge_source_ids=[ids.encode("knowledge_source", k) for k in agent.knowledge_source_ids],
        task_count=task_count,
        version=version,
        visibility=agent.visibility,
        resource_owner_id=ids.encode("membership", agent.owner_membership_id),
        actions=sorted(actions),
        updated_at=agent.updated_at,
    )


class ModelOut(BaseModel):
    id: str
    label: str


@router.get("/models", summary="Model tiers (decision D-01: Claude tiers only)")
def models(principal: Authenticated) -> list[ModelOut]:
    return [ModelOut(id=m.id, label=m.label) for m in MODEL_TIERS]


class SkillOut(BaseModel):
    id: str
    name: str
    description: str
    category: str


@router.get("/skills", summary="Curated Skills catalog")
def skills(principal: Authenticated) -> list[SkillOut]:
    return [SkillOut(**s.__dict__) for s in SKILLS]


@router.get("/tenants/{tenant_id}/agents", summary="Workmates you own or that are shared with you")
def list_agents(tenant_id: str, principal: Authenticated, state: State) -> list[AgentOut]:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id)) as (session, actor):
        rows = (
            session.execute(
                select(Agent)
                .where(Agent.tenant_id == actor.tenant.id, Agent.deleted_at.is_(None))
                .where(policy.readable(actor, KIND, id_column=Agent.id, owner_column=Agent.owner_membership_id))
                .order_by(Agent.created_at)
            )
            .scalars()
            .all()
        )
        return [_out(session, actor, a, policy.allowed_actions(session, actor, KIND, a)) for a in rows]


class AgentIn(BaseModel):
    name: str = Field(max_length=80)
    description: str = Field(default="", max_length=400)
    tag: str | None = Field(default=None, max_length=20)
    avatar: int = 0
    instructions: str = ""
    context: str = ""
    model_tier: str = "auto"
    skills: list[str] = Field(default_factory=list)


@router.post("/tenants/{tenant_id}/agents", status_code=201, summary="Create a workmate (publishes version 1)")
def create_agent(tenant_id: str, body: AgentIn, principal: Authenticated, state: State) -> AgentOut:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id), write=True) as (
        session,
        actor,
    ):
        agent = service.create(session, actor, body.model_dump())
        events.publish(session, actor.tenant.id, "agent.created", {"agent_id": ids.encode(KIND, agent.id)})
        return _out(session, actor, agent, set(policy.ACTIONS))


@router.get("/tenants/{tenant_id}/agents/{agent_id}", summary="Workmate detail")
def get_agent(tenant_id: str, agent_id: str, principal: Authenticated, state: State) -> AgentOut:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id)) as (session, actor):
        agent = load(session, Agent, actor, agent_id, KIND)
        return _out(session, actor, agent, require(session, actor, "read", KIND, agent))


class AgentPatch(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=400)
    tag: str | None = Field(default=None, max_length=20)
    avatar: int | None = None
    instructions: str | None = None
    context: str | None = None
    model_tier: str | None = None
    skills: list[str] | None = None
    add_skill: str | None = None


@router.patch("/tenants/{tenant_id}/agents/{agent_id}", summary="Edit a workmate (runtime changes publish a version)")
def patch_agent(tenant_id: str, agent_id: str, body: AgentPatch, principal: Authenticated, state: State) -> AgentOut:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id), write=True) as (
        session,
        actor,
    ):
        agent = load(session, Agent, actor, agent_id, KIND, lock=True)
        actions = require(session, actor, "edit", KIND, agent)
        service.update(session, actor, agent, body.model_dump(exclude_unset=True))
        session.flush()
        events.publish(session, actor.tenant.id, "agent.updated", {"agent_id": agent_id})
        return _out(session, actor, agent, actions)


class VersionOut(BaseModel):
    id: str
    version: int
    model_tier: str
    skills: list[str]
    published_at: datetime
    published_by: str


@router.get("/tenants/{tenant_id}/agents/{agent_id}/versions", summary="Published versions (immutable)")
def versions(tenant_id: str, agent_id: str, principal: Authenticated, state: State) -> list[VersionOut]:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id)) as (session, actor):
        agent = load(session, Agent, actor, agent_id, KIND)
        require(session, actor, "read", KIND, agent)
        rows = session.execute(
            select(AgentVersion).where(AgentVersion.agent_id == agent.id).order_by(AgentVersion.version_no.desc())
        ).scalars()
        return [
            VersionOut(
                id=ids.encode("agent_version", v.id),
                version=v.version_no,
                model_tier=v.model_tier,
                skills=list(v.skills),
                published_at=v.published_at,
                published_by=ids.encode("membership", v.published_by_membership_id),
            )
            for v in rows
        ]


@router.delete("/tenants/{tenant_id}/agents/{agent_id}", status_code=204, summary="Delete a workmate")
def delete_agent(tenant_id: str, agent_id: str, principal: Authenticated, state: State) -> Response:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id), write=True) as (
        session,
        actor,
    ):
        agent = load(session, Agent, actor, agent_id, KIND, lock=True)
        require(session, actor, "delete", KIND, agent)
        agent.deleted_at = utcnow()
        audit.record(
            session,
            "agent.deleted",
            tenant_id=actor.tenant.id,
            actor_user_id=actor.user_id,
            actor_membership_id=actor.membership.id,
            target_type=KIND,
            target_id=agent.id,
        )
        events.publish(session, actor.tenant.id, "agent.deleted", {"agent_id": agent_id})
    return Response(status_code=204)


@router.get("/tenants/{tenant_id}/shared-agents", summary="Workmates shared with the whole organization")
def shared_agents(tenant_id: str, principal: Authenticated, state: State) -> list[str]:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id)) as (session, actor):
        rows = session.execute(
            select(Agent.id)
            .join(
                ResourceGrant,
                and_(
                    ResourceGrant.resource_id == Agent.id,
                    ResourceGrant.resource_type == KIND,
                    ResourceGrant.principal_type == "tenant",
                ),
            )
            .where(Agent.tenant_id == actor.tenant.id, Agent.deleted_at.is_(None))
        ).scalars()
        return [ids.encode(KIND, a) for a in rows]
