"""Organization SSO policy (R2, Part 3 §3): sessions record the brokered identity provider; an organization
that requires its provider answers 403 TENANT_REAUTH_REQUIRED (with the login URL) to other sessions, without
affecting the personal workspace or other organizations; the owner cannot lock themselves out."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.integration.test_tenancy import add_member, create_org
from tests.support.auth import sign_in, unique_email
from workx.core import ids
from workx.core.db import Database

POLICY = {"required": True, "idp_alias": "acme-okta"}


def test_org_requires_its_identity_provider(
    new_client: Callable[[], TestClient], oidc: TestClient, owner_db: Database
) -> None:
    owner_email, member_email = unique_email("owner"), unique_email("member")
    owner = new_client()
    sign_in(owner, oidc, owner_email)
    org = create_org(owner)
    base = f"/api/v1/tenants/{org['id']}"
    # Requiring a provider the owner did not sign in with would lock them out: refused with the way forward.
    refused = owner.put(f"{base}/sso", json=POLICY)
    assert refused.status_code == 409 and refused.json()["data"]["login_url"].startswith(
        "/api/v1/auth/login?idp_hint=acme-okta"
    )
    # Signing in through the organization's provider (brokered) satisfies it; then the policy can be set.
    owner = new_client()
    owner_me = sign_in(owner, oidc, owner_email, idp_hint="acme-okta")
    assert owner.put(f"{base}/sso", json=POLICY).status_code == 200
    assert owner.get(f"{base}/members").status_code == 200
    with owner_db.transaction() as session:
        idp = session.execute(
            text("SELECT idp_alias FROM login_sessions WHERE user_id = :u ORDER BY created_at DESC LIMIT 1"),
            {"u": ids.decode("user", owner_me["id"])},
        ).scalar_one()
    assert idp == "acme-okta"
    # A member with a password session is asked to sign in again, for this organization only.
    member = new_client()
    me = sign_in(member, oidc, member_email)
    add_member(owner_db, org["id"], me["id"])
    blocked = member.get(f"{base}/agents")
    assert blocked.status_code == 403 and blocked.json()["code"] == "TENANT_REAUTH_REQUIRED"
    assert blocked.json()["data"] == {
        "idp_hint": "acme-okta",
        "login_url": f"/api/v1/auth/login?idp_hint=acme-okta&return_to=%2Ft%2F{org['id']}%2Fhome",
    }
    personal = next(t for t in member.get("/api/v1/me/tenants").json() if t["type"] == "personal")
    assert member.get(f"/api/v1/tenants/{personal['id']}/agents").status_code == 200
    # Another provider does not count either.
    other = new_client()
    sign_in(other, oidc, member_email, idp_hint="partner-azure")
    assert other.get(f"{base}/agents").status_code == 403
    # After signing in through the organization's provider the member gets in.
    member = new_client()
    sign_in(member, oidc, member_email, idp_hint="acme-okta")
    assert member.get(f"{base}/agents").status_code == 200
    # Only the owner may change the policy.
    assert member.put(f"{base}/sso", json={"required": False}).status_code == 403
    assert ids.decode("tenant", org["id"]) is not None
