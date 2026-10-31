"""Agent drafts and immutable versions.

The approved UI has no separate publish step, so saving runtime fields (instructions, context, model tier,
skills, knowledge) publishes a new version immediately. Tasks pin the version current at creation, so edits
never change work already in progress (Part 4 §2).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from workx.core import ids
from workx.core.errors import validation
from workx.core.orm import utcnow
from workx.domains.agents.catalog import MODEL_TIER_IDS, normalize_skill
from workx.domains.agents.models import Agent, AgentVersion
from workx.domains.audit import service as audit
from workx.domains.tenancy.service import Actor, clean_name

RUNTIME_FIELDS = ("instructions", "context_md", "model_tier", "skills", "knowledge_source_ids")
MAX_TEXT = 20_000


def _text(value: Any, field: str, maximum: int = MAX_TEXT) -> str:
    text_value = str(value or "")
    if len(text_value) > maximum:
        raise validation(f"{field} is too long.", data={"field": field})
    return text_value


def _skills(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        skill = normalize_skill(value)
        if skill is None:
            raise validation(f"Unknown skill: {value}", data={"field": "skills"})
        if skill not in result:
            result.append(skill)
    return result


def publish(session: Session, actor: Actor, agent: Agent) -> AgentVersion:
    number = (
        session.execute(
            select(func.coalesce(func.max(AgentVersion.version_no), 0)).where(AgentVersion.agent_id == agent.id)
        ).scalar_one()
        + 1
    )
    version = AgentVersion(
        id=ids.uuid7(),
        tenant_id=agent.tenant_id,
        agent_id=agent.id,
        version_no=number,
        instructions=agent.instructions,
        context_md=agent.context_md,
        model_tier=agent.model_tier,
        skills=list(agent.skills),
        tool_refs=[],
        knowledge_source_ids=list(agent.knowledge_source_ids),
        published_by_membership_id=actor.membership.id,
        published_at=utcnow(),
    )
    session.add(version)
    session.flush()
    agent.current_version_id = version.id
    return version


def create(session: Session, actor: Actor, body: dict[str, Any]) -> Agent:
    model_tier = body.get("model_tier") or "auto"
    if model_tier not in MODEL_TIER_IDS:
        raise validation("Unknown model tier.", data={"field": "model_tier"})
    agent = Agent(
        id=ids.uuid7(),
        tenant_id=actor.tenant.id,
        name=clean_name(body.get("name", ""), maximum=40),
        description=_text(body.get("description"), "description", 200),
        tag=_text(body.get("tag") or ("Team" if actor.tenant.type == "organization" else "Personal"), "tag", 20),
        avatar=int(body.get("avatar") or 0) % 12,
        owner_membership_id=actor.membership.id,
        instructions=_text(body.get("instructions"), "instructions"),
        context_md=_text(body.get("context"), "context"),
        model_tier=model_tier,
        skills=_skills(list(body.get("skills") or [])),
        knowledge_source_ids=[],
    )
    session.add(agent)
    session.flush()
    publish(session, actor, agent)
    audit.record(
        session,
        "agent.created",
        tenant_id=actor.tenant.id,
        actor_user_id=actor.user_id,
        actor_membership_id=actor.membership.id,
        target_type="agent",
        target_id=agent.id,
    )
    return agent


def update(session: Session, actor: Actor, agent: Agent, body: dict[str, Any]) -> bool:
    """Applies a patch; returns True when a new version was published."""
    before = tuple(getattr(agent, f) for f in RUNTIME_FIELDS)
    if "name" in body:
        agent.name = clean_name(body["name"], maximum=40)
    if "description" in body:
        agent.description = _text(body["description"], "description", 200)
    if "tag" in body:
        agent.tag = _text(body["tag"], "tag", 20)
    if "avatar" in body:
        agent.avatar = int(body["avatar"]) % 12
    if "instructions" in body:
        agent.instructions = _text(body["instructions"], "instructions")
    if "context" in body:
        agent.context_md = _text(body["context"], "context")
    if "model_tier" in body:
        if body["model_tier"] not in MODEL_TIER_IDS:
            raise validation("Unknown model tier.", data={"field": "model_tier"})
        agent.model_tier = body["model_tier"]
    if "skills" in body:
        agent.skills = _skills(list(body["skills"]))
    if body.get("add_skill"):
        agent.skills = _skills([*agent.skills, body["add_skill"]])
    if "knowledge_source_ids" in body:
        agent.knowledge_source_ids = [uuid.UUID(str(v)) for v in body["knowledge_source_ids"]]
    agent.row_version += 1
    changed = tuple(getattr(agent, f) for f in RUNTIME_FIELDS) != before
    if changed:
        publish(session, actor, agent)
    audit.record(
        session,
        "agent.updated",
        tenant_id=actor.tenant.id,
        actor_user_id=actor.user_id,
        actor_membership_id=actor.membership.id,
        target_type="agent",
        target_id=agent.id,
        data={"fields": sorted(body), "published": changed},
    )
    return changed


STARTER = {
    "en": ("My Workmate", "Your general-purpose workmate. Rename it or add skills any time."),
    "zh-CN": ("我的智能伙伴", "通用智能伙伴，可随时重命名或添加能力。"),
}


def create_starter(session: Session, actor: Actor, *, locale: str) -> Agent:
    """Every new workspace starts with one workmate, as in the approved prototype. Organization starters are
    shared with all members (read/use); personal ones stay private."""
    from workx.domains.authz import policy

    name, description = STARTER.get(locale, STARTER["en"])
    agent = create(session, actor, {"name": name, "description": description, "avatar": 0})
    if actor.tenant.type == "organization":
        agent.visibility = policy.set_sharing(
            session, actor, "agent", agent, policy.Sharing("organization"), active_member_ids={actor.membership.id}
        )
    return agent
