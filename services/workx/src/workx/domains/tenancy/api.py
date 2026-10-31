"""Workspace, membership, department and invitation routes (Part 3, Part 8 J2/J3, Part 11 §3)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from workx.core import ids
from workx.core.errors import ApiError, not_found
from workx.core.orm import utcnow
from workx.domains.identity.auth import Authenticated, State
from workx.domains.identity.models import User
from workx.domains.tenancy import invitations, service
from workx.domains.tenancy.models import Department, Invitation, Membership, Tenant
from workx.platform import idempotency

router = APIRouter(tags=["tenancy"])
IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key")]


def tenant_uuid(external: str) -> uuid.UUID:
    value = ids.decode("tenant", external)
    if value is None:
        raise not_found()
    return value


def _decode(kind: str, external: str) -> uuid.UUID:
    value = ids.decode(kind, external)
    if value is None:
        raise not_found()
    return value


class TenantSummary(BaseModel):
    id: str
    slug: str
    type: Literal["personal", "organization"]
    name: str
    role: str
    status: str


class TenantOut(TenantSummary):
    plan_id: str
    member_count: int
    settings: dict[str, Any]
    preferences: dict[str, Any]


def _summary(tenant: Tenant, membership: Membership) -> TenantSummary:
    return TenantSummary(
        id=ids.encode("tenant", tenant.id),
        slug=tenant.slug,
        type=tenant.type,
        name=tenant.name,
        role=membership.role,
        status=tenant.status,
    )


def _detail(session: Session, actor: service.Actor) -> TenantOut:
    count = session.execute(
        select(Membership.id).where(Membership.tenant_id == actor.tenant.id, Membership.status == "active")
    ).all()
    return TenantOut(
        **_summary(actor.tenant, actor.membership).model_dump(),
        plan_id=actor.tenant.plan_id,
        member_count=len(count),
        settings=actor.tenant.settings,
        preferences=actor.membership.preferences,
    )


@router.get("/me/tenants", summary="Workspaces the user belongs to")
def my_tenants(principal: Authenticated, state: State) -> list[TenantSummary]:
    with state.db.transaction(principal_id=principal.user_id) as session:
        rows = session.execute(
            select(Tenant, Membership)
            .join(Membership, Membership.tenant_id == Tenant.id)
            .where(Membership.user_id == principal.user_id, Membership.status == "active")
            .where(Tenant.status.in_(("active", "suspended")))
            .order_by(Tenant.type.desc(), Tenant.created_at)
        ).all()
    return [_summary(t, m) for t, m in rows]


class TenantCreate(BaseModel):
    name: str = Field(max_length=120)


@router.post("/tenants", status_code=201, summary="Create an organization (creator becomes owner)")
def create_tenant(
    body: TenantCreate, principal: Authenticated, state: State, idempotency_key: IdempotencyKey = None
) -> JSONResponse:
    with state.db.transaction(principal_id=principal.user_id) as session:

        def work() -> tuple[int, dict[str, Any]]:
            tenant, membership = service.create_organization(session, user_id=principal.user_id, name=body.name)
            return 201, _summary(tenant, membership).model_dump()

        status, payload = idempotency.run(
            session,
            key=idempotency_key,
            scope="global",
            principal_id=principal.user_id,
            route="POST /tenants",
            body=body.model_dump(),
            work=work,
        )
    return JSONResponse(payload, status_code=status)


@router.get("/tenants/{tenant_id}", summary="Workspace detail")
def get_tenant(tenant_id: str, principal: Authenticated, state: State) -> TenantOut:
    tid = tenant_uuid(tenant_id)
    with state.db.transaction(tenant_id=tid, principal_id=principal.user_id) as session:
        return _detail(session, service.actor_for(session, user_id=principal.user_id, tenant_id=tid))


class TenantPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    settings: dict[str, Any] | None = None
    preferences: dict[str, Any] | None = None


TENANT_SETTING_KEYS = {"proactive"}
MEMBER_PREFERENCE_KEYS = {"hideQuick", "notificationsRead", "proactiveDismissed"}


@router.patch("/tenants/{tenant_id}", summary="Rename workspace, change settings or own preferences")
def patch_tenant(tenant_id: str, body: TenantPatch, principal: Authenticated, state: State) -> TenantOut:
    tid = tenant_uuid(tenant_id)
    with state.db.transaction(tenant_id=tid, principal_id=principal.user_id) as session:
        actor = service.actor_for(session, user_id=principal.user_id, tenant_id=tid)
        if body.preferences is not None:
            unknown = set(body.preferences) - MEMBER_PREFERENCE_KEYS
            if unknown:
                raise ApiError(400, "VALIDATION_FAILED", f"Unknown preferences: {', '.join(sorted(unknown))}")
            actor.membership.preferences = {**actor.membership.preferences, **body.preferences}
        if body.name is not None or body.settings is not None:
            service.require_writable(actor)
            if actor.tenant.type == "organization":
                service.require_manager(actor)
            if body.name is not None:
                actor.tenant.name = service.clean_name(body.name)
            if body.settings is not None:
                unknown = set(body.settings) - TENANT_SETTING_KEYS
                if unknown:
                    raise ApiError(400, "VALIDATION_FAILED", f"Unknown settings: {', '.join(sorted(unknown))}")
                actor.tenant.settings = {**actor.tenant.settings, **body.settings}
            actor.tenant.row_version += 1
        session.flush()
        return _detail(session, actor)


class MemberOut(BaseModel):
    id: str
    user_id: str
    name: str
    email: str
    role: str
    status: str
    department_id: str | None
    joined_at: datetime


def _member(m: Membership, u: User) -> MemberOut:
    return MemberOut(
        id=ids.encode("membership", m.id),
        user_id=ids.encode("user", u.id),
        name=m.display_name or u.display_name,
        email=u.primary_email,
        role=m.role,
        status=m.status,
        department_id=ids.encode("department", m.department_id) if m.department_id else None,
        joined_at=m.created_at,
    )


@router.get("/tenants/{tenant_id}/members", summary="Members (active and deactivated)")
def members(tenant_id: str, principal: Authenticated, state: State) -> list[MemberOut]:
    tid = tenant_uuid(tenant_id)
    with state.db.transaction(tenant_id=tid, principal_id=principal.user_id) as session:
        service.actor_for(session, user_id=principal.user_id, tenant_id=tid)
        rows = session.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.tenant_id == tid, Membership.status != "removed")
            .order_by(Membership.created_at)
        ).all()
    return [_member(m, u) for m, u in rows]


class MemberPatch(BaseModel):
    role: Literal["owner", "admin", "member"] | None = None
    status: Literal["active", "deactivated"] | None = None
    name: str | None = Field(default=None, max_length=80)
    department_id: str | None = None


def _target(session: Session, tid: uuid.UUID, member_id: str) -> tuple[Membership, User]:
    mid = _decode("membership", member_id)
    row = session.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.id == mid, Membership.tenant_id == tid)
        .with_for_update(of=Membership)
    ).first()
    if row is None or row[0].status == "removed":
        raise not_found()
    return row[0], row[1]


@router.patch("/tenants/{tenant_id}/members/{member_id}", summary="Change role, status, name or department")
def patch_member(
    tenant_id: str, member_id: str, body: MemberPatch, principal: Authenticated, state: State
) -> MemberOut:
    tid = tenant_uuid(tenant_id)
    with state.db.transaction(tenant_id=tid, principal_id=principal.user_id) as session:
        actor = service.actor_for(session, user_id=principal.user_id, tenant_id=tid)
        target, user = _target(session, tid, member_id)
        fields = body.model_fields_set
        department: Any = ...
        if "department_id" in fields:
            department = _decode("department", body.department_id) if body.department_id else None
        service.update_member(
            session, actor, target, role=body.role, status=body.status, display_name=body.name, department_id=department
        )
        session.flush()
        return _member(target, user)


@router.delete("/tenants/{tenant_id}/members/{member_id}", status_code=204, summary="Remove a member, or leave")
def remove_member(tenant_id: str, member_id: str, principal: Authenticated, state: State) -> Response:
    tid = tenant_uuid(tenant_id)
    with state.db.transaction(tenant_id=tid, principal_id=principal.user_id) as session:
        actor = service.actor_for(session, user_id=principal.user_id, tenant_id=tid)
        target, _ = _target(session, tid, member_id)
        service.remove_member(session, actor, target)
    return Response(status_code=204)


class TransferIn(BaseModel):
    membership_id: str


@router.post("/tenants/{tenant_id}/ownership-transfer", status_code=204, summary="Transfer organization ownership")
def transfer(tenant_id: str, body: TransferIn, principal: Authenticated, state: State) -> Response:
    if not principal.recently_authenticated(state.settings.reauth_window_minutes):
        raise ApiError(403, "REAUTH_REQUIRED", "Sign in again to confirm this change.")
    tid = tenant_uuid(tenant_id)
    with state.db.transaction(tenant_id=tid, principal_id=principal.user_id) as session:
        actor = service.actor_for(session, user_id=principal.user_id, tenant_id=tid, for_update=True)
        target, _ = _target(session, tid, body.membership_id)
        service.transfer_ownership(session, actor, target)
    return Response(status_code=204)


class DepartmentOut(BaseModel):
    id: str
    name: str
    parent_id: str | None


class DepartmentIn(BaseModel):
    name: str = Field(max_length=80)
    parent_id: str | None = None


def _department(d: Department) -> DepartmentOut:
    return DepartmentOut(
        id=ids.encode("department", d.id),
        name=d.name,
        parent_id=ids.encode("department", d.parent_id) if d.parent_id else None,
    )


@router.get("/tenants/{tenant_id}/departments", summary="Departments (organization attribute)")
def departments(tenant_id: str, principal: Authenticated, state: State) -> list[DepartmentOut]:
    tid = tenant_uuid(tenant_id)
    with state.db.transaction(tenant_id=tid, principal_id=principal.user_id) as session:
        service.actor_for(session, user_id=principal.user_id, tenant_id=tid)
        rows = session.execute(
            select(Department).where(Department.tenant_id == tid).order_by(Department.name)
        ).scalars()
        return [_department(d) for d in rows]


@router.post("/tenants/{tenant_id}/departments", status_code=201, summary="Create a department")
def create_department(tenant_id: str, body: DepartmentIn, principal: Authenticated, state: State) -> DepartmentOut:
    tid = tenant_uuid(tenant_id)
    with state.db.transaction(tenant_id=tid, principal_id=principal.user_id) as session:
        actor = service.actor_for(session, user_id=principal.user_id, tenant_id=tid)
        service.require_writable(actor)
        service.require_manager(actor)
        parent = _decode("department", body.parent_id) if body.parent_id else None
        if parent and session.get(Department, parent) is None:
            raise not_found()
        department = Department(
            id=ids.uuid7(), tenant_id=tid, name=service.clean_name(body.name, maximum=80), parent_id=parent
        )
        session.add(department)
        session.flush()
        return _department(department)


class InvitationOut(BaseModel):
    id: str
    email: str
    role: str
    status: str
    expires_at: datetime
    created_at: datetime


def _invitation(i: Invitation) -> InvitationOut:
    return InvitationOut(
        id=ids.encode("invitation", i.id),
        email=i.email_normalized,
        role=i.role,
        status=i.status,
        expires_at=i.expires_at,
        created_at=i.created_at,
    )


@router.get("/tenants/{tenant_id}/invitations", summary="Invitations (owners and admins)")
def list_invitations(tenant_id: str, principal: Authenticated, state: State) -> list[InvitationOut]:
    tid = tenant_uuid(tenant_id)
    with state.db.transaction(tenant_id=tid, principal_id=principal.user_id) as session:
        actor = service.actor_for(session, user_id=principal.user_id, tenant_id=tid)
        service.require_manager(actor)
        invitations.expire_stale(session, tid)
        rows = session.execute(
            select(Invitation).where(Invitation.tenant_id == tid).order_by(Invitation.created_at.desc())
        ).scalars()
        return [_invitation(i) for i in rows]


class InviteIn(BaseModel):
    emails: str | list[str]
    role: Literal["admin", "member"] = "member"


@router.post("/tenants/{tenant_id}/invitations", status_code=201, summary="Invite people by email (all or nothing)")
def invite(
    tenant_id: str, body: InviteIn, principal: Authenticated, state: State, idempotency_key: IdempotencyKey = None
) -> JSONResponse:
    tid = tenant_uuid(tenant_id)
    with state.db.transaction(tenant_id=tid, principal_id=principal.user_id) as session:
        actor = service.actor_for(session, user_id=principal.user_id, tenant_id=tid)

        def work() -> tuple[int, list[Any]]:
            created = invitations.create(session, actor, state.settings, emails=body.emails, role=body.role)
            return 201, [_invitation(i).model_dump(mode="json") for i in created]

        status, payload = idempotency.run(
            session,
            key=idempotency_key,
            scope=str(tid),
            principal_id=principal.user_id,
            route="POST /tenants/{t}/invitations",
            body=body.model_dump(),
            work=work,
        )
    return JSONResponse(payload, status_code=status)


@router.post("/tenants/{tenant_id}/invitations/{invitation_id}/cancel", status_code=204, summary="Cancel an invitation")
def cancel_invitation(tenant_id: str, invitation_id: str, principal: Authenticated, state: State) -> Response:
    tid = tenant_uuid(tenant_id)
    with state.db.transaction(tenant_id=tid, principal_id=principal.user_id) as session:
        actor = service.actor_for(session, user_id=principal.user_id, tenant_id=tid)
        invitation = session.get(Invitation, _decode("invitation", invitation_id), with_for_update=True)
        if invitation is None or invitation.tenant_id != tid:
            raise not_found()
        invitations.cancel(session, actor, invitation)
    return Response(status_code=204)


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class InvitationPreview(BaseModel):
    tenant_name: str
    role: str
    inviter_name: str
    status: str
    expires_at: datetime


@router.post("/invitations/preview", summary="What an invitation link is for (the link itself is the credential)")
def preview(body: TokenIn, state: State) -> InvitationPreview:
    with state.db.transaction() as session:
        p = invitations.preview(session, body.token)
        status = (
            "expired"
            if p.invitation.status == "pending" and p.invitation.expires_at <= utcnow()
            else p.invitation.status
        )
        return InvitationPreview(
            tenant_name=p.tenant.name,
            role=p.invitation.role,
            inviter_name=p.inviter_name,
            status=status,
            expires_at=p.invitation.expires_at,
        )


class AcceptOut(BaseModel):
    tenant_id: str
    membership_id: str


@router.post("/invitations/accept", summary="Accept an invitation as the signed-in user")
def accept(body: TokenIn, principal: Authenticated, state: State) -> AcceptOut:
    with state.db.transaction(principal_id=principal.user_id) as session:
        user = session.get(User, principal.user_id)
        assert user is not None
        membership = invitations.accept(session, user=user, token=body.token)
        return AcceptOut(
            tenant_id=ids.encode("tenant", membership.tenant_id), membership_id=ids.encode("membership", membership.id)
        )
