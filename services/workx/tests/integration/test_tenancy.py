"""Organizations, memberships and the Part 3 §6.1 management rules."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from tests.support.auth import idem, sign_in
from workx.core import ids
from workx.core.db import Database
from workx.core.orm import utcnow
from workx.domains.audit.models import AuditEvent
from workx.domains.identity.models import LoginSession
from workx.domains.tenancy.models import Membership
from workx.platform.models import OutboxEvent


def create_org(client: TestClient, name: str = "Acme") -> dict[str, Any]:
    response = client.post("/api/v1/tenants", json={"name": name}, headers=idem())
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def add_member(db: Database, tenant_id: str, user_id: str, role: str = "member") -> str:
    """Direct insert for rule tests (pass the owner connection); invitation acceptance is in test_invitations."""
    membership_id = ids.uuid7()
    with db.transaction() as session:
        session.add(
            Membership(
                id=membership_id,
                tenant_id=ids.decode("tenant", tenant_id),
                user_id=ids.decode("user", user_id),
                role=role,
            )
        )
    return ids.encode("membership", membership_id)


def test_create_organization_is_idempotent(client: TestClient, oidc: TestClient, owner_db: Database) -> None:
    sign_in(client, oidc)
    key = {"Idempotency-Key": "org-create-1"}
    first = client.post("/api/v1/tenants", json={"name": "  Acme   Labs "}, headers=key)
    again = client.post("/api/v1/tenants", json={"name": "  Acme   Labs "}, headers=key)
    assert first.status_code == again.status_code == 201
    assert first.json() == again.json() and first.json()["name"] == "Acme Labs" and first.json()["role"] == "owner"
    reused = client.post("/api/v1/tenants", json={"name": "Other"}, headers=key)
    assert reused.status_code == 409 and reused.json()["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert client.post("/api/v1/tenants", json={"name": "No key"}).json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    assert len([t for t in client.get("/api/v1/me/tenants").json() if t["type"] == "organization"]) == 1
    with owner_db.transaction() as session:
        tenant_uuid = ids.decode("tenant", first.json()["id"])
        assert session.execute(select(AuditEvent).where(AuditEvent.tenant_id == tenant_uuid)).first()
        assert session.execute(select(OutboxEvent).where(OutboxEvent.tenant_id == tenant_uuid)).first()


def test_other_users_cannot_see_a_tenant(new_client: Callable[[], TestClient], oidc: TestClient) -> None:
    owner, stranger = new_client(), new_client()
    sign_in(owner, oidc)
    sign_in(stranger, oidc)
    org = create_org(owner)
    for path in ("", "/members", "/departments", "/invitations"):
        assert stranger.get(f"/api/v1/tenants/{org['id']}{path}").status_code == 404
    assert stranger.get("/api/v1/tenants/not-an-id").status_code == 404


def test_rename_and_settings_rules(new_client: Callable[[], TestClient], oidc: TestClient, owner_db: Database) -> None:
    owner, member = new_client(), new_client()
    sign_in(owner, oidc)
    member_me = sign_in(member, oidc)
    org = create_org(owner)
    add_member(owner_db, org["id"], member_me["id"])
    assert owner.patch(f"/api/v1/tenants/{org['id']}", json={"name": "Renamed"}).json()["name"] == "Renamed"
    assert member.patch(f"/api/v1/tenants/{org['id']}", json={"name": "Nope"}).status_code == 403
    # Members can change only their own preferences.
    mine = member.patch(f"/api/v1/tenants/{org['id']}", json={"preferences": {"hideQuick": True}})
    assert mine.status_code == 200 and mine.json()["preferences"] == {"hideQuick": True}
    assert owner.get(f"/api/v1/tenants/{org['id']}").json()["preferences"] == {}
    assert owner.patch(f"/api/v1/tenants/{org['id']}", json={"settings": {"evil": 1}}).status_code == 400


def test_role_and_status_rules(new_client: Callable[[], TestClient], oidc: TestClient, owner_db: Database) -> None:
    owner, admin, member = new_client(), new_client(), new_client()
    owner_me = sign_in(owner, oidc)
    admin_me, member_me = sign_in(admin, oidc), sign_in(member, oidc)
    org = create_org(owner)
    admin_id = add_member(owner_db, org["id"], admin_me["id"], "admin")
    member_id = add_member(owner_db, org["id"], member_me["id"])
    base = f"/api/v1/tenants/{org['id']}/members"
    owner_id = next(m["id"] for m in owner.get(base).json() if m["user_id"] == owner_me["id"])

    assert member.patch(f"{base}/{admin_id}", json={"role": "member"}).status_code == 403
    assert admin.patch(f"{base}/{owner_id}", json={"role": "member"}).status_code == 403
    assert admin.patch(f"{base}/{member_id}", json={"role": "owner"}).json()["code"] == "USE_OWNERSHIP_TRANSFER"
    assert admin.patch(f"{base}/{admin_id}", json={"status": "deactivated"}).json()["code"] == "CANNOT_DEACTIVATE_SELF"
    promoted = admin.patch(f"{base}/{member_id}", json={"role": "admin", "name": "Mia"})
    assert promoted.status_code == 200 and promoted.json()["role"] == "admin" and promoted.json()["name"] == "Mia"
    assert admin.patch(f"{base}/{member_id}", json={"status": "deactivated"}).json()["status"] == "deactivated"
    # A deactivated member loses access to the tenant immediately.
    assert member.get(f"/api/v1/tenants/{org['id']}").status_code == 404
    assert owner.patch(f"{base}/{owner_id}", json={"status": "deactivated"}).json()["code"] == "CANNOT_DEACTIVATE_SELF"


def test_last_owner_cannot_leave_and_members_can(
    new_client: Callable[[], TestClient], oidc: TestClient, owner_db: Database
) -> None:
    owner, member = new_client(), new_client()
    owner_me = sign_in(owner, oidc)
    member_me = sign_in(member, oidc)
    org = create_org(owner)
    member_id = add_member(owner_db, org["id"], member_me["id"])
    base = f"/api/v1/tenants/{org['id']}/members"
    owner_id = next(m["id"] for m in owner.get(base).json() if m["user_id"] == owner_me["id"])
    assert owner.delete(f"{base}/{owner_id}").json()["code"] == "LAST_OWNER"
    assert member.delete(f"{base}/{member_id}").status_code == 204
    assert member.get(f"/api/v1/tenants/{org['id']}").status_code == 404
    personal = next(t for t in owner.get("/api/v1/me/tenants").json() if t["type"] == "personal")
    personal_member = owner.get(f"/api/v1/tenants/{personal['id']}/members").json()[0]["id"]
    assert (
        owner.delete(f"/api/v1/tenants/{personal['id']}/members/{personal_member}").json()["code"]
        == "PERSONAL_WORKSPACE"
    )


def test_database_keeps_an_owner_even_if_code_forgets(owner_db: Database, client: TestClient, oidc: TestClient) -> None:
    import pytest
    from sqlalchemy.exc import IntegrityError

    sign_in(client, oidc)
    org = create_org(client)
    with pytest.raises(IntegrityError), owner_db.transaction() as session:
        session.execute(
            update(Membership).where(Membership.tenant_id == ids.decode("tenant", org["id"])).values(role="admin")
        )


def test_ownership_transfer_requires_recent_sign_in(
    new_client: Callable[[], TestClient], oidc: TestClient, owner_db: Database
) -> None:
    owner, admin = new_client(), new_client()
    owner_me = sign_in(owner, oidc)
    admin_me = sign_in(admin, oidc)
    org = create_org(owner)
    admin_id = add_member(owner_db, org["id"], admin_me["id"], "admin")
    with owner_db.transaction() as session:
        session.execute(
            update(LoginSession)
            .where(LoginSession.user_id == ids.decode("user", owner_me["id"]))
            .values(created_at=utcnow() - timedelta(hours=2))
        )
    url = f"/api/v1/tenants/{org['id']}/ownership-transfer"
    assert owner.post(url, json={"membership_id": admin_id}).json()["code"] == "REAUTH_REQUIRED"
    sign_in(owner, oidc, owner_me["email"])
    assert admin.post(url, json={"membership_id": admin_id}).status_code == 403
    assert owner.post(url, json={"membership_id": admin_id}).status_code == 204
    roles = {m["user_id"]: m["role"] for m in owner.get(f"/api/v1/tenants/{org['id']}/members").json()}
    assert roles == {owner_me["id"]: "admin", admin_me["id"]: "owner"}


def test_departments(new_client: Callable[[], TestClient], oidc: TestClient, owner_db: Database) -> None:
    owner, member = new_client(), new_client()
    sign_in(owner, oidc)
    member_me = sign_in(member, oidc)
    org = create_org(owner)
    member_id = add_member(owner_db, org["id"], member_me["id"])
    base = f"/api/v1/tenants/{org['id']}"
    product = owner.post(f"{base}/departments", json={"name": "Product"}).json()
    design = owner.post(f"{base}/departments", json={"name": "Design", "parent_id": product["id"]}).json()
    assert design["parent_id"] == product["id"]
    assert member.post(f"{base}/departments", json={"name": "Nope"}).status_code == 403
    assert (
        owner.patch(f"{base}/members/{member_id}", json={"department_id": design["id"]}).json()["department_id"]
        == design["id"]
    )
    personal = next(t for t in owner.get("/api/v1/me/tenants").json() if t["type"] == "personal")
    assert owner.post(f"/api/v1/tenants/{personal['id']}/departments", json={"name": "X"}).status_code == 403
