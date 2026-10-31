from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.integration.test_tenancy import add_member, create_org
from tests.support.auth import sign_in
from workx.core.db import Database


def test_audit_log_pages_and_is_for_managers(
    new_client: Callable[[], TestClient], oidc: TestClient, owner_db: Database
) -> None:
    owner, member = new_client(), new_client()
    sign_in(owner, oidc)
    member_me = sign_in(member, oidc)
    org = create_org(owner)
    add_member(owner_db, org["id"], member_me["id"])
    for name in ("A", "B", "C"):
        owner.post(f"/api/v1/tenants/{org['id']}/departments", json={"name": name})
    owner.patch(f"/api/v1/tenants/{org['id']}", json={"name": "Renamed"})
    url = f"/api/v1/tenants/{org['id']}/audit-events"
    first = owner.get(url, params={"limit": 1}).json()
    assert len(first["items"]) == 1 and first["next_cursor"]
    seen = [first["items"][0]["id"]]
    cursor = first["next_cursor"]
    while cursor:
        page = owner.get(url, params={"limit": 1, "cursor": cursor}).json()
        seen += [i["id"] for i in page["items"]]
        cursor = page["next_cursor"]
    assert len(seen) == len(set(seen)) >= 5  # created, 3 departments, renamed
    assert "tenant.created" in {i["action"] for i in owner.get(url).json()["items"]}
    assert member.get(url).status_code == 403
    assert owner.get(url, params={"cursor": "not-base64!"}).status_code == 400
