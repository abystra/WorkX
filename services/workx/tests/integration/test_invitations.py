"""J2: invite by email, deliver the link, accept as the matching verified user."""

from __future__ import annotations

import email
import re
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from tests.integration.test_tenancy import create_org
from tests.support.auth import idem, sign_in, unique_email
from workx.core import ids
from workx.core.db import Database
from workx.core.orm import utcnow
from workx.domains.tenancy import invitations
from workx.domains.tenancy.models import Invitation
from workx.platform.mail import FileMailer
from workx.platform.models import OutboxEvent


def deliver(api_app: FastAPI, db: Database, tmp: Path, invitation_id: str) -> str:
    """Runs the email job the outbox schedules and returns the token from the delivered link."""
    settings = api_app.state.workx.settings
    with db.transaction() as session:
        topics = (
            session.execute(
                select(OutboxEvent.topic).where(
                    OutboxEvent.payload["invitation_id"].astext == str(ids.decode("invitation", invitation_id))
                )
            )
            .scalars()
            .all()
        )
    assert topics == ["invitation.created"]
    mailer = FileMailer(tmp, settings.mail_from)
    assert invitations.send_invitation_email(db, settings, mailer, ids.decode("invitation", invitation_id))
    message = email.message_from_bytes(sorted(tmp.glob("*.eml"), key=lambda p: p.stat().st_mtime)[-1].read_bytes())
    body = message.get_payload(decode=True).decode()
    match = re.search(r"http://web\.test/invite/([A-Za-z0-9_\-]+)", body)
    assert match, body
    return match.group(1)


def invite(owner: TestClient, org_id: str, emails: str, role: str = "member") -> list[dict[str, str]]:
    response = owner.post(
        f"/api/v1/tenants/{org_id}/invitations", json={"emails": emails, "role": role}, headers=idem()
    )
    assert response.status_code == 201, response.text
    return list(response.json())


def test_invite_deliver_preview_accept(
    new_client: Callable[[], TestClient], oidc: TestClient, db: Database, api_app: FastAPI, tmp_path: Path
) -> None:
    owner, invitee = new_client(), new_client()
    sign_in(owner, oidc)
    org = create_org(owner, "Northwind")
    address = unique_email("new.person")
    [created] = invite(owner, org["id"], f" {address.upper()} ", "admin")
    assert created["email"] == address and created["status"] == "pending"
    token = deliver(api_app, db, tmp_path, created["id"])

    preview = invitee.post("/api/v1/invitations/preview", json={"token": token}).json()
    assert preview["tenant_name"] == "Northwind" and preview["role"] == "admin" and preview["status"] == "pending"
    # Not signed in yet: the web app sends the visitor to sign in and back.
    assert invitee.post("/api/v1/invitations/accept", json={"token": token}).status_code == 401
    sign_in(invitee, oidc, address)
    accepted = invitee.post("/api/v1/invitations/accept", json={"token": token})
    assert accepted.status_code == 200 and accepted.json()["tenant_id"] == org["id"]
    replay = invitee.post("/api/v1/invitations/accept", json={"token": token})
    assert replay.json() == accepted.json()
    roles = {m["email"]: m["role"] for m in owner.get(f"/api/v1/tenants/{org['id']}/members").json()}
    assert roles[address] == "admin"
    assert [i["status"] for i in owner.get(f"/api/v1/tenants/{org['id']}/invitations").json()] == ["accepted"]
    # The plaintext token is not stored anywhere.
    with db.transaction() as session:
        row = session.get(Invitation, ids.decode("invitation", created["id"]))
        assert row is not None and token.encode() not in row.token_digest


def test_wrong_email_expired_cancelled(
    new_client: Callable[[], TestClient], oidc: TestClient, db: Database, api_app: FastAPI, tmp_path: Path
) -> None:
    owner, other = new_client(), new_client()
    sign_in(owner, oidc)
    sign_in(other, oidc)
    org = create_org(owner)
    first, second = invite(owner, org["id"], f"{unique_email()}, {unique_email()}")
    token = deliver(api_app, db, tmp_path, first["id"])
    assert other.post("/api/v1/invitations/accept", json={"token": token}).json()["code"] == "INVITATION_EMAIL_MISMATCH"
    with db.transaction() as session:
        session.execute(
            update(Invitation)
            .where(Invitation.id == ids.decode("invitation", first["id"]))
            .values(expires_at=utcnow() - timedelta(minutes=1))
        )
    invitee = new_client()
    sign_in(invitee, oidc, first["email"])
    assert invitee.post("/api/v1/invitations/accept", json={"token": token}).json()["code"] == "INVITATION_EXPIRED"
    second_token = deliver(api_app, db, tmp_path, second["id"])
    assert owner.post(f"/api/v1/tenants/{org['id']}/invitations/{second['id']}/cancel").status_code == 204
    assert not invitations.send_invitation_email(
        db, api_app.state.workx.settings, FileMailer(tmp_path, "x"), ids.decode("invitation", second["id"])
    )
    late = new_client()
    sign_in(late, oidc, second["email"])
    assert late.post("/api/v1/invitations/accept", json={"token": second_token}).json()["code"] == "INVITATION_CLOSED"
    assert late.post("/api/v1/invitations/accept", json={"token": "x" * 43}).json()["code"] == "INVITATION_NOT_FOUND"


def test_batches_are_all_or_nothing(new_client: Callable[[], TestClient], oidc: TestClient) -> None:
    owner = new_client()
    owner_me = sign_in(owner, oidc)
    org = create_org(owner)
    url = f"/api/v1/tenants/{org['id']}/invitations"
    bad = owner.post(url, json={"emails": f"{unique_email()}, not-an-email"}, headers=idem())
    assert bad.status_code == 400 and bad.json()["data"]["code"] == "INVALID_EMAIL"
    assert owner.get(url).json() == []
    existing = unique_email()
    invite(owner, org["id"], existing)
    dup = owner.post(url, json={"emails": [unique_email(), existing]}, headers=idem())
    assert dup.json()["code"] == "INVITATION_PENDING" and dup.json()["data"]["emails"] == [existing]
    member = owner.post(url, json={"emails": owner_me["email"]}, headers=idem())
    assert member.json()["code"] == "ALREADY_MEMBER"
    assert owner.post(url, json={"emails": unique_email(), "role": "owner"}, headers=idem()).status_code == 400
    assert len(owner.get(url).json()) == 1


def test_who_may_invite(new_client: Callable[[], TestClient], oidc: TestClient, db: Database) -> None:
    from tests.integration.test_tenancy import add_member

    owner, member = new_client(), new_client()
    sign_in(owner, oidc)
    member_me = sign_in(member, oidc)
    org = create_org(owner)
    add_member(db, org["id"], member_me["id"])
    assert (
        member.post(
            f"/api/v1/tenants/{org['id']}/invitations", json={"emails": unique_email()}, headers=idem()
        ).status_code
        == 403
    )
    assert member.get(f"/api/v1/tenants/{org['id']}/invitations").status_code == 403
    personal = next(t for t in owner.get("/api/v1/me/tenants").json() if t["type"] == "personal")
    response = owner.post(
        f"/api/v1/tenants/{personal['id']}/invitations", json={"emails": unique_email()}, headers=idem()
    )
    assert response.json()["code"] == "PERSONAL_WORKSPACE"
