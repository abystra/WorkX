"""Invitations (Part 3 §2.3, Part 8 J2).

The emailed token is HMAC(secret, invitation id); only its SHA-256 digest is stored, and the email job
re-derives the token, so no plaintext token exists at rest. Acceptance is one transaction holding the row lock.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from workx.core import ids
from workx.core.db import Database
from workx.core.errors import ApiError, conflict, forbidden, not_found, validation
from workx.core.orm import utcnow
from workx.core.settings import ApiSettings
from workx.domains.audit import service as audit
from workx.domains.identity import tokens
from workx.domains.identity.models import User
from workx.domains.tenancy import service as tenancy
from workx.domains.tenancy.models import Invitation, Membership, Tenant
from workx.platform import outbox
from workx.platform.mail import Mail, Mailer

EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")
MAX_BATCH = 50


def token_for(settings: ApiSettings, invitation_id: uuid.UUID) -> str:
    return tokens.derive(settings.secret_key.get_secret_value(), "invitation", invitation_id.bytes)


def parse_emails(raw: str | list[str]) -> list[str]:
    parts = raw if isinstance(raw, list) else re.split(r"[\s,;]+", raw)
    emails: list[str] = []
    for part in parts:
        email = part.strip().lower()
        if not email:
            continue
        if not EMAIL.match(email) or len(email) > 254:
            raise validation(f"Not a valid email address: {email}", data={"field": "emails", "code": "INVALID_EMAIL"})
        if email not in emails:
            emails.append(email)
    if not emails:
        raise validation("Enter at least one email address.", data={"field": "emails", "code": "INVALID_EMAIL"})
    if len(emails) > MAX_BATCH:
        raise validation(f"Invite at most {MAX_BATCH} people at once.", data={"field": "emails"})
    return emails


def expire_stale(session: Session, tenant_id: uuid.UUID) -> None:
    for invitation in session.execute(
        select(Invitation).where(
            Invitation.tenant_id == tenant_id, Invitation.status == "pending", Invitation.expires_at <= utcnow()
        )
    ).scalars():
        invitation.status = "expired"


def create(
    session: Session, actor: tenancy.Actor, settings: ApiSettings, *, emails: str | list[str], role: str
) -> list[Invitation]:
    """All-or-nothing batch (Part 8 J2)."""
    tenancy.require_writable(actor)
    if actor.tenant.type != "organization":
        raise conflict("PERSONAL_WORKSPACE", "Personal workspaces cannot invite members.")
    tenancy.require_manager(actor)
    if role not in ("admin", "member"):
        raise validation("Invitations can grant admin or member.", data={"field": "role"})
    addresses = parse_emails(emails)
    expire_stale(session, actor.tenant.id)
    pending = set(
        session.execute(
            select(Invitation.email_normalized).where(
                Invitation.tenant_id == actor.tenant.id,
                Invitation.status == "pending",
                func.lower(Invitation.email_normalized).in_(addresses),
            )
        ).scalars()
    )
    if pending:
        raise conflict(
            "INVITATION_PENDING", "Some addresses already have a pending invitation.", {"emails": sorted(pending)}
        )
    members = set(
        session.execute(
            select(func.lower(User.primary_email))
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.tenant_id == actor.tenant.id,
                Membership.status != "removed",
                func.lower(User.primary_email).in_(addresses),
            )
        ).scalars()
    )
    if members:
        raise conflict("ALREADY_MEMBER", "Some addresses already belong to members.", {"emails": sorted(members)})
    created = []
    for email in addresses:
        invitation_id = ids.uuid7()
        invitation = Invitation(
            id=invitation_id,
            tenant_id=actor.tenant.id,
            email_normalized=email,
            role=role,
            token_digest=tokens.digest(token_for(settings, invitation_id)),
            expires_at=utcnow() + timedelta(days=settings.invitation_ttl_days),
            invited_by_membership_id=actor.membership.id,
        )
        session.add(invitation)
        created.append(invitation)
        outbox.emit(
            session,
            "invitation.created",
            {"invitation_id": str(invitation_id), "tenant_id": str(actor.tenant.id)},
            tenant_id=actor.tenant.id,
        )
    session.flush()
    audit.record(
        session,
        "invitation.created",
        tenant_id=actor.tenant.id,
        actor_user_id=actor.user_id,
        actor_membership_id=actor.membership.id,
        data={"count": len(created), "role": role},
    )
    return created


def cancel(session: Session, actor: tenancy.Actor, invitation: Invitation) -> None:
    tenancy.require_manager(actor)
    if invitation.status != "pending":
        raise conflict("INVITATION_CLOSED", "This invitation was already used, cancelled or expired.")
    invitation.status = "cancelled"
    audit.record(
        session,
        "invitation.cancelled",
        tenant_id=actor.tenant.id,
        actor_user_id=actor.user_id,
        actor_membership_id=actor.membership.id,
        target_type="invitation",
        target_id=invitation.id,
    )


def _by_token(session: Session, token: str, *, lock: bool) -> Invitation:
    query = select(Invitation).where(Invitation.token_digest == tokens.digest(token))
    if lock:
        query = query.with_for_update()
    invitation = session.execute(query).scalar_one_or_none()
    if invitation is None:
        raise ApiError(404, "INVITATION_NOT_FOUND", "This invitation link is not valid.")
    return invitation


@dataclass(frozen=True)
class Preview:
    invitation: Invitation
    tenant: Tenant
    inviter_name: str


def preview(session: Session, token: str) -> Preview:
    invitation = _by_token(session, token, lock=False)
    tenant = session.get(Tenant, invitation.tenant_id)
    inviter = session.execute(
        select(Membership.display_name, User.display_name)
        .join(User, User.id == Membership.user_id)
        .where(Membership.id == invitation.invited_by_membership_id)
    ).one()
    assert tenant is not None
    return Preview(invitation, tenant, inviter[0] or inviter[1])


def accept(session: Session, *, user: User, token: str) -> Membership:
    invitation = _by_token(session, token, lock=True)
    if invitation.status == "accepted":
        # Replays by the same user return the same membership (idempotent acceptance).
        if invitation.consumed_by_user_id == user.id and invitation.accepted_membership_id:
            membership = session.get(Membership, invitation.accepted_membership_id)
            if membership is not None and membership.status == "active":
                return membership
        raise conflict("INVITATION_CLOSED", "This invitation was already used.")
    if invitation.status == "pending" and invitation.expires_at <= utcnow():
        invitation.status = "expired"
    if invitation.status == "expired":
        raise conflict("INVITATION_EXPIRED", "This invitation has expired.")
    if invitation.status != "pending":
        raise conflict("INVITATION_CLOSED", "This invitation was cancelled.")
    if invitation.email_normalized.lower() != user.primary_email.lower():
        raise forbidden_mismatch()
    tenant = session.get(Tenant, invitation.tenant_id, with_for_update=True)
    if tenant is None or tenant.status != "active":
        raise not_found()
    membership = session.execute(
        select(Membership).where(Membership.tenant_id == tenant.id, Membership.user_id == user.id).with_for_update()
    ).scalar_one_or_none()
    if membership is None:
        membership = Membership(id=ids.uuid7(), tenant_id=tenant.id, user_id=user.id, role=invitation.role)
        session.add(membership)
    elif membership.status == "removed":
        # A former member can be invited back; the row is unique per (tenant, user).
        membership.status = "active"
        membership.role = invitation.role
        membership.authz_epoch += 1
    elif membership.status != "active":
        raise conflict("MEMBERSHIP_DEACTIVATED", "Your membership is deactivated. Ask an admin to reactivate it.")
    session.flush()
    invitation.status = "accepted"
    invitation.consumed_by_user_id = user.id
    invitation.accepted_membership_id = membership.id
    audit.record(
        session,
        "invitation.accepted",
        tenant_id=tenant.id,
        actor_user_id=user.id,
        actor_membership_id=membership.id,
        target_type="invitation",
        target_id=invitation.id,
    )
    outbox.emit(
        session,
        "invitation.accepted",
        {"invitation_id": str(invitation.id), "tenant_id": str(tenant.id), "membership_id": str(membership.id)},
        tenant_id=tenant.id,
    )
    return membership


def forbidden_mismatch() -> ApiError:
    error = forbidden("This invitation was sent to a different email address.")
    error.code = "INVITATION_EMAIL_MISMATCH"
    return error


def send_invitation_email(db: Database, settings: ApiSettings, mailer: Mailer, invitation_id: uuid.UUID) -> bool:
    """Job handler for ``invitation.created``. Returns False when there is nothing to send any more."""
    with db.transaction() as session:
        invitation = session.get(Invitation, invitation_id)
        if invitation is None or invitation.status != "pending":
            return False
        tenant = session.get(Tenant, invitation.tenant_id)
        assert tenant is not None
        inviter = preview(session, token_for(settings, invitation.id)).inviter_name
        email, tenant_name, expires = invitation.email_normalized, tenant.name, invitation.expires_at
    link = f"{settings.public_base_url.rstrip('/')}/invite/{token_for(settings, invitation_id)}"
    mailer.send(
        Mail(
            to=email,
            subject=f"{inviter} invited you to {tenant_name} on WorkX",
            text=(
                f'{inviter} invited you to join the organization "{tenant_name}" on WorkX.\n\n'
                f"Accept the invitation: {link}\n\n"
                f"This link expires on {expires:%Y-%m-%d} and works only for {email}.\n"
            ),
        )
    )
    return True
