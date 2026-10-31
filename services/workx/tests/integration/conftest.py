"""Fixtures shared by integration tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.integration.test_tenancy import add_member, create_org
from tests.support.auth import sign_in
from workx.core.db import Database


@pytest.fixture
def team(new_client: Callable[[], TestClient], oidc: TestClient, owner_db: Database) -> dict[str, Any]:
    alice, bob = new_client(), new_client()
    sign_in(alice, oidc)
    bob_me = sign_in(bob, oidc)
    org = create_org(alice)
    add_member(owner_db, org["id"], bob_me["id"])
    return {"alice": alice, "bob": bob, "base": f"/api/v1/tenants/{org['id']}", "org": org}
