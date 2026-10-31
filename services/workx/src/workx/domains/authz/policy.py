"""Policy evaluator (Part 3 §6.2). Grants are authoritative; ``visibility`` is a summary kept in sync here.

* The owner (``owner_membership_id``) may do everything.
* Grants add actions for a membership, every active member of a project, or every active member of the tenant.
* An org owner/admin without a grant has **no** access to a private resource (management ≠ content access).
* Personal workspaces support ``private`` only.
* Unreadable resources are reported as 404 so their existence is not disclosed.

``workx_can()`` in the database mirrors ``allowed_actions`` for SQL-side filtering (retrieval, Part 7); a test
keeps the two in agreement.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import ColumnElement, and_, delete, exists, func, or_, select
from sqlalchemy.orm import Session

from workx.core import ids
from workx.core.errors import forbidden, not_found, validation
from workx.core.orm import utcnow
from workx.domains.audit import service as audit
from workx.domains.authz.models import ResourceGrant
from workx.domains.tenancy.service import Actor

ACTIONS = ("read", "use", "comment", "edit", "share", "delete", "export", "approve")
VISIBILITIES = ("private", "selected", "project", "organization")
DEFAULT_ACTIONS = {"selected": ("read", "use"), "project": ("read", "use", "comment"), "organization": ("read", "use")}
# Actions a share may never grant implicitly (Part 3 §6.2).
EXPLICIT_ONLY = {"edit", "share", "delete", "export"}


_KIND = {"membership": "membership", "project": "project", "tenant": "tenant", "service_principal": "membership"}


class Resource(Protocol):
    @property
    def id(self) -> uuid.UUID: ...
    @property
    def tenant_id(self) -> uuid.UUID: ...
    @property
    def owner_membership_id(self) -> uuid.UUID | None: ...


@dataclass(frozen=True)
class ResourceRef:
    resource_type: str
    id: uuid.UUID
    tenant_id: uuid.UUID
    owner_membership_id: uuid.UUID | None


# Project membership lookup is provided by the resources domain once projects exist (P-04).
_project_ids_provider: Any = None


def register_project_membership(provider: Any) -> None:
    global _project_ids_provider
    _project_ids_provider = provider


def _project_ids(session: Session, actor: Actor) -> list[uuid.UUID]:
    if _project_ids_provider is None:
        return []
    result: list[uuid.UUID] = _project_ids_provider(session, actor)
    return result


def _principal_clause(actor: Actor, project_ids: Iterable[uuid.UUID]) -> ColumnElement[bool]:
    clauses = [
        and_(ResourceGrant.principal_type == "membership", ResourceGrant.principal_id == actor.membership.id),
        and_(ResourceGrant.principal_type == "tenant", ResourceGrant.principal_id == actor.tenant.id),
    ]
    project_ids = list(project_ids)
    if project_ids:
        clauses.append(and_(ResourceGrant.principal_type == "project", ResourceGrant.principal_id.in_(project_ids)))
    return or_(*clauses)


def _live() -> ColumnElement[bool]:
    return or_(ResourceGrant.expires_at.is_(None), ResourceGrant.expires_at > func.now())


def allowed_actions(session: Session, actor: Actor, resource_type: str, resource: Resource) -> set[str]:
    if resource.tenant_id != actor.tenant.id:
        return set()
    if resource.owner_membership_id == actor.membership.id:
        return set(ACTIONS)
    rows = session.execute(
        select(ResourceGrant.actions).where(
            ResourceGrant.tenant_id == actor.tenant.id,
            ResourceGrant.resource_type == resource_type,
            ResourceGrant.resource_id == resource.id,
            _principal_clause(actor, _project_ids(session, actor)),
            _live(),
        )
    ).scalars()
    return {action for actions in rows for action in actions}


def authorize(session: Session, actor: Actor, action: str, resource_type: str, resource: Resource) -> set[str]:
    """Raises 404 when the resource is not readable, 403 when readable but ``action`` is not allowed."""
    actions = allowed_actions(session, actor, resource_type, resource)
    if "read" not in actions:
        raise not_found()
    if action not in actions:
        raise forbidden()
    return actions


def readable(
    actor: Actor, resource_type: str, *, id_column: Any, owner_column: Any, project_ids: Iterable[uuid.UUID] = ()
) -> ColumnElement[bool]:
    """SQL filter for list endpoints: owned by the actor, or granted ``read`` to one of its principals."""
    granted = exists().where(
        ResourceGrant.tenant_id == actor.tenant.id,
        ResourceGrant.resource_type == resource_type,
        ResourceGrant.resource_id == id_column,
        ResourceGrant.actions.contains(["read"]),
        _principal_clause(actor, project_ids),
        _live(),
    )
    return or_(owner_column == actor.membership.id, granted)


@dataclass(frozen=True)
class Sharing:
    visibility: str
    member_ids: tuple[uuid.UUID, ...] = ()
    project_id: uuid.UUID | None = None
    actions: tuple[str, ...] = ()


def current_sharing(session: Session, actor: Actor, resource_type: str, resource: Resource) -> dict[str, Any]:
    grants = (
        session.execute(
            select(ResourceGrant).where(
                ResourceGrant.tenant_id == actor.tenant.id,
                ResourceGrant.resource_type == resource_type,
                ResourceGrant.resource_id == resource.id,
            )
        )
        .scalars()
        .all()
    )
    return {
        "visibility": summarize(grants),
        "grants": [
            {
                "principal_type": g.principal_type,
                "principal_id": ids.encode(_KIND[g.principal_type], g.principal_id),
                "actions": sorted(g.actions),
            }
            for g in grants
        ],
    }


def summarize(grants: Iterable[ResourceGrant]) -> str:
    types = {g.principal_type for g in grants}
    if "tenant" in types:
        return "organization"
    if "project" in types:
        return "project"
    if "membership" in types:
        return "selected"
    return "private"


def set_sharing(
    session: Session,
    actor: Actor,
    resource_type: str,
    resource: Resource,
    sharing: Sharing,
    *,
    active_member_ids: set[uuid.UUID],
) -> str:
    """Replaces the resource's grants. Requires ``share``; the owner always has it."""
    authorize(session, actor, "share", resource_type, resource)
    if sharing.visibility not in VISIBILITIES:
        raise validation("Unknown visibility.", data={"field": "visibility"})
    if actor.tenant.type == "personal" and sharing.visibility != "private":
        raise validation("Personal workspaces keep content private.", data={"field": "visibility"})
    extra = set(sharing.actions)
    if not extra <= set(ACTIONS):
        raise validation("Unknown action.", data={"field": "actions"})
    session.execute(
        delete(ResourceGrant).where(
            ResourceGrant.tenant_id == actor.tenant.id,
            ResourceGrant.resource_type == resource_type,
            ResourceGrant.resource_id == resource.id,
        )
    )
    principals: list[tuple[str, uuid.UUID]] = []
    if sharing.visibility == "selected":
        if not sharing.member_ids:
            raise validation("Choose at least one member.", data={"field": "member_ids"})
        unknown = set(sharing.member_ids) - active_member_ids
        if unknown:
            raise validation("Some members are not active in this workspace.", data={"field": "member_ids"})
        principals = [("membership", m) for m in sharing.member_ids if m != resource.owner_membership_id]
    elif sharing.visibility == "project":
        if sharing.project_id is None:
            raise validation("Choose a project.", data={"field": "project_id"})
        principals = [("project", sharing.project_id)]
    elif sharing.visibility == "organization":
        principals = [("tenant", actor.tenant.id)]
    actions = sorted(set(DEFAULT_ACTIONS.get(sharing.visibility, ())) | extra)
    for principal_type, principal_id in principals:
        session.add(
            ResourceGrant(
                id=ids.uuid7(),
                tenant_id=actor.tenant.id,
                resource_type=resource_type,
                resource_id=resource.id,
                principal_type=principal_type,
                principal_id=principal_id,
                actions=actions,
                granted_by_membership_id=actor.membership.id,
                created_at=utcnow(),
            )
        )
    audit.record(
        session,
        "resource.sharing_changed",
        tenant_id=actor.tenant.id,
        actor_user_id=actor.user_id,
        actor_membership_id=actor.membership.id,
        target_type=resource_type,
        target_id=resource.id,
        data={"visibility": sharing.visibility, "actions": actions, "principals": len(principals)},
    )
    return sharing.visibility


def require_known_action(action: str) -> None:
    if action not in ACTIONS:
        raise validation("Unknown action.")
