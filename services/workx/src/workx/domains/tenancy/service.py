"""Tenant provisioning and membership rules (Part 3 §2, §5, §6.1)."""

from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from workx.core import ids
from workx.core.errors import ApiError, conflict, forbidden, not_found, validation
from workx.domains.audit import service as audit
from workx.domains.tenancy.models import Department, Membership, Tenant
from workx.platform import outbox

ROLES = ("owner", "admin", "member")
NAME_MAX = 60


@dataclass(frozen=True)
class Actor:
    """The authenticated user acting in a tenant through an active membership."""

    user_id: uuid.UUID
    tenant: Tenant
    membership: Membership

    @property
    def role(self) -> str:
        return self.membership.role

    @property
    def is_manager(self) -> bool:
        return self.tenant.type == "organization" and self.role in ("owner", "admin")


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:32]
    return base or "org"


def _unique_slug(session: Session, base: str) -> str:
    candidate = base
    while session.execute(select(Tenant.id).where(Tenant.slug == candidate)).first():
        candidate = f"{base}-{secrets.token_hex(3)}"
    return candidate


def clean_name(value: str, *, field: str = "name", maximum: int = NAME_MAX) -> str:
    cleaned = " ".join(str(value or "").split())
    if not cleaned or len(cleaned) > maximum:
        raise validation(f"{field} must be 1-{maximum} characters.", data={"field": field})
    return cleaned


def ensure_personal_tenant(session: Session, *, user_id: uuid.UUID, display_name: str) -> Tenant:
    """Idempotent and safe under concurrent first logins: the partial unique index admits one personal tenant."""
    tenant_id = ids.uuid7()
    session.execute(
        insert(Tenant)
        .values(
            id=tenant_id,
            slug=f"p-{ids.encode('tenant', tenant_id)[4:].lower()}",
            type="personal",
            name=display_name,
            owner_user_id=user_id,
        )
        .on_conflict_do_nothing(index_elements=["owner_user_id"], index_where=Tenant.type == "personal")
    )
    tenant = session.execute(
        select(Tenant).where(Tenant.owner_user_id == user_id, Tenant.type == "personal")
    ).scalar_one()
    session.execute(
        insert(Membership)
        .values(id=ids.uuid7(), tenant_id=tenant.id, user_id=user_id, role="owner")
        .on_conflict_do_nothing(index_elements=["tenant_id", "user_id"])
    )
    return tenant


def create_organization(session: Session, *, user_id: uuid.UUID, name: str) -> tuple[Tenant, Membership]:
    name = clean_name(name)
    tenant = Tenant(
        id=ids.uuid7(),
        slug=_unique_slug(session, _slugify(name)),
        type="organization",
        name=name,
        owner_user_id=user_id,
    )
    session.add(tenant)
    session.flush()
    membership = Membership(id=ids.uuid7(), tenant_id=tenant.id, user_id=user_id, role="owner")
    session.add(membership)
    session.flush()
    audit.record(
        session,
        "tenant.created",
        tenant_id=tenant.id,
        actor_user_id=user_id,
        actor_membership_id=membership.id,
        target_type="tenant",
        target_id=tenant.id,
        data={"type": "organization"},
    )
    outbox.emit(session, "tenant.created", {"tenant_id": str(tenant.id)}, tenant_id=tenant.id)
    return tenant, membership


def actor_for(session: Session, *, user_id: uuid.UUID, tenant_id: uuid.UUID, for_update: bool = False) -> Actor:
    """Resolves the tenant from the path and verifies an active membership (Part 3 §3). Missing → 404."""
    query = (
        select(Tenant, Membership)
        .join(Membership, Membership.tenant_id == Tenant.id)
        .where(Tenant.id == tenant_id, Membership.user_id == user_id, Membership.status == "active")
        .where(Tenant.status.in_(("active", "suspended")))
    )
    if for_update:
        query = query.with_for_update(of=Membership)
    row = session.execute(query).first()
    if row is None:
        raise not_found()
    return Actor(user_id=user_id, tenant=row[0], membership=row[1])


def require_writable(actor: Actor) -> None:
    if actor.tenant.status == "suspended":
        raise ApiError(403, "TENANT_SUSPENDED", "This workspace is suspended. Content stays readable.")


def require_manager(actor: Actor) -> None:
    if not actor.is_manager:
        raise forbidden("Only organization owners and admins can do this.")


def bump_epoch(session: Session, membership: Membership, tenant: Tenant) -> None:
    """Invalidates cached authorization for this membership and tenant immediately (Part 3 §3)."""
    membership.authz_epoch += 1
    session.execute(update(Tenant).where(Tenant.id == tenant.id).values(authz_epoch=Tenant.authz_epoch + 1))


def active_owner_count(session: Session, tenant_id: uuid.UUID) -> int:
    return session.execute(
        select(func.count())
        .select_from(Membership)
        .where(Membership.tenant_id == tenant_id, Membership.role == "owner", Membership.status == "active")
    ).scalar_one()


def update_member(
    session: Session,
    actor: Actor,
    target: Membership,
    *,
    role: str | None = None,
    status: str | None = None,
    display_name: str | None = None,
    department_id: uuid.UUID | object | None = ...,
) -> Membership:
    """Management rules from Part 3 §6.1. Owners are managed only by owners; admins manage admins and members."""
    require_writable(actor)
    require_manager(actor)
    if target.status == "removed":
        raise not_found()
    if target.role == "owner" and actor.role != "owner":
        raise forbidden("Only an owner can change another owner.")
    changes: dict[str, object] = {}
    if role is not None and role != target.role:
        if role not in ROLES:
            raise validation("Unknown role.", data={"field": "role"})
        if role == "owner" or target.role == "owner":
            raise conflict("USE_OWNERSHIP_TRANSFER", "Change owners with an ownership transfer.")
        changes["role"] = role
    if status is not None and status != target.status:
        if status not in ("active", "deactivated"):
            raise validation("Status must be active or deactivated.", data={"field": "status"})
        if target.id == actor.membership.id:
            raise conflict("CANNOT_DEACTIVATE_SELF", "You cannot deactivate yourself. Leave the organization instead.")
        if target.role == "owner":
            raise conflict("LAST_OWNER", "Transfer ownership before deactivating an owner.")
        changes["status"] = status
    if display_name is not None:
        target.display_name = clean_name(display_name, maximum=40)
    if department_id is not ...:
        if department_id is not None and session.get(Department, department_id) is None:
            raise validation("Unknown department.", data={"field": "department_id"})
        target.department_id = department_id  # type: ignore[assignment]
    for key, value in changes.items():
        setattr(target, key, value)
    if changes:
        bump_epoch(session, target, actor.tenant)
        audit.record(
            session,
            "membership.updated",
            tenant_id=actor.tenant.id,
            actor_user_id=actor.user_id,
            actor_membership_id=actor.membership.id,
            target_type="membership",
            target_id=target.id,
            data=changes,
        )
        outbox.emit(
            session,
            "membership.updated",
            {
                "tenant_id": str(actor.tenant.id),
                "membership_id": str(target.id),
                **{k: str(v) for k, v in changes.items()},
            },
            tenant_id=actor.tenant.id,
        )
    return target


def remove_member(session: Session, actor: Actor, target: Membership) -> None:
    """Removal by a manager, or leaving when the target is the actor (members may leave, Part 3 §6.1)."""
    require_writable(actor)
    leaving = target.id == actor.membership.id
    if actor.tenant.type == "personal":
        raise conflict("PERSONAL_WORKSPACE", "You cannot leave your personal workspace.")
    if not leaving:
        require_manager(actor)
        if target.role == "owner" and actor.role != "owner":
            raise forbidden("Only an owner can remove another owner.")
    if target.role == "owner" and active_owner_count(session, actor.tenant.id) <= 1 and target.status == "active":
        raise conflict("LAST_OWNER", "Transfer ownership before the last owner leaves.")
    target.status = "removed"
    bump_epoch(session, target, actor.tenant)
    audit.record(
        session,
        "membership.left" if leaving else "membership.removed",
        tenant_id=actor.tenant.id,
        actor_user_id=actor.user_id,
        actor_membership_id=actor.membership.id,
        target_type="membership",
        target_id=target.id,
    )
    outbox.emit(
        session,
        "membership.removed",
        {"tenant_id": str(actor.tenant.id), "membership_id": str(target.id)},
        tenant_id=actor.tenant.id,
    )


def transfer_ownership(session: Session, actor: Actor, target: Membership) -> None:
    require_writable(actor)
    if actor.tenant.type != "organization" or actor.role != "owner":
        raise forbidden("Only an organization owner can transfer ownership.")
    if target.status != "active" or target.id == actor.membership.id:
        raise validation("Choose another active member.", data={"field": "membership_id"})
    target.role = "owner"
    actor.membership.role = "admin"
    actor.tenant.owner_user_id = target.user_id
    bump_epoch(session, target, actor.tenant)
    bump_epoch(session, actor.membership, actor.tenant)
    audit.record(
        session,
        "tenant.ownership_transferred",
        tenant_id=actor.tenant.id,
        actor_user_id=actor.user_id,
        actor_membership_id=actor.membership.id,
        target_type="membership",
        target_id=target.id,
    )
    outbox.emit(
        session,
        "tenant.ownership_transferred",
        {
            "tenant_id": str(actor.tenant.id),
            "from_membership_id": str(actor.membership.id),
            "to_membership_id": str(target.id),
        },
        tenant_id=actor.tenant.id,
    )
