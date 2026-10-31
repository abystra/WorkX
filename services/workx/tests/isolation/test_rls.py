"""T-ISO: tenant isolation enforced by PostgreSQL row-level security for the runtime role (Part 13 §2).

These tests use raw SQL as ``workx_app``, so they hold even if application code forgets a filter.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from tests.integration.test_tenancy import create_org
from tests.support.auth import idem, sign_in, unique_email
from workx.core import ids
from workx.core.db import Database

TENANT_TABLES = ("memberships", "invitations", "departments", "audit_events", "resource_grants", "usage_events")


@dataclass(frozen=True)
class World:
    a_tenant: uuid.UUID
    b_tenant: uuid.UUID
    a_user: uuid.UUID
    b_user: uuid.UUID


@pytest.fixture
def world(new_client: Callable[[], TestClient], oidc: TestClient, owner_db: Database) -> World:
    a, b = new_client(), new_client()
    a_me, b_me = sign_in(a, oidc), sign_in(b, oidc)
    org_a, org_b = create_org(a, "Tenant A"), create_org(b, "Tenant B")
    for client, org in ((a, org_a), (b, org_b)):
        client.post(f"/api/v1/tenants/{org['id']}/departments", json={"name": "Ops"})
        client.post(f"/api/v1/tenants/{org['id']}/invitations", json={"emails": unique_email()}, headers=idem())
    a_tid, b_tid = ids.decode("tenant", org_a["id"]), ids.decode("tenant", org_b["id"])
    with owner_db.transaction() as session:
        for tid in (a_tid, b_tid):
            session.execute(
                text(
                    "INSERT INTO resource_grants (id, tenant_id, resource_type, resource_id, principal_type,"
                    " principal_id, actions)"
                    " VALUES (gen_random_uuid(), :t, 'agent', gen_random_uuid(), 'tenant', :t, '{read}')"
                ),
                {"t": tid},
            )
            session.execute(
                text(
                    "INSERT INTO usage_events (id, tenant_id, kind, quantity, unit, source_event_id)"
                    " VALUES (gen_random_uuid(), :t, 'tool_call', 1, 'call', gen_random_uuid()::text)"
                ),
                {"t": tid},
            )
    assert a_tid and b_tid
    return World(a_tid, b_tid, ids.decode("user", a_me["id"]), ids.decode("user", b_me["id"]))  # type: ignore[arg-type]


def count(
    db: Database, table: str, tenant: uuid.UUID, *, as_tenant: uuid.UUID | None, as_user: uuid.UUID | None
) -> int:
    with db.transaction(tenant_id=as_tenant, principal_id=as_user) as session:
        return int(
            session.execute(text(f"SELECT count(*) FROM {table} WHERE tenant_id = :t"), {"t": tenant}).scalar_one()  # noqa: S608
        )


def test_iso_01_other_tenant_rows_are_invisible(db: Database, owner_db: Database, world: World) -> None:
    for table in TENANT_TABLES:
        assert count(owner_db, table, world.b_tenant, as_tenant=None, as_user=None) > 0, table
        assert count(db, table, world.b_tenant, as_tenant=world.a_tenant, as_user=world.a_user) == 0, table
        assert count(db, table, world.a_tenant, as_tenant=world.a_tenant, as_user=world.a_user) > 0, table


def test_iso_02_no_context_sees_no_tenant_rows(db: Database, world: World) -> None:
    for table in ("invitations", "departments", "resource_grants", "usage_events", "audit_events"):
        assert count(db, table, world.a_tenant, as_tenant=None, as_user=None) == 0, table


def test_iso_03_cannot_write_into_another_tenant(db: Database, world: World) -> None:
    statements = [
        "INSERT INTO departments (id, tenant_id, name) VALUES (gen_random_uuid(), :b, 'x')",
        "INSERT INTO resource_grants (id, tenant_id, resource_type, resource_id, principal_type, principal_id, actions)"
        " VALUES (gen_random_uuid(), :b, 'agent', gen_random_uuid(), 'tenant', :b, '{read}')",
        "INSERT INTO audit_events (id, tenant_id, action) VALUES (gen_random_uuid(), :b, 'forged')",
    ]
    for statement in statements:
        with (
            pytest.raises(ProgrammingError, match="row-level security"),
            db.transaction(tenant_id=world.a_tenant, principal_id=world.a_user) as session,
        ):
            session.execute(text(statement), {"b": world.b_tenant})
    # Updates and deletes silently match nothing.
    with db.transaction(tenant_id=world.a_tenant, principal_id=world.a_user) as session:
        changed = session.execute(
            text("UPDATE departments SET name = 'pwned' WHERE tenant_id = :b"), {"b": world.b_tenant}
        )
        assert changed.rowcount == 0  # type: ignore[attr-defined]
        removed = session.execute(text("DELETE FROM memberships WHERE tenant_id = :b"), {"b": world.b_tenant})
        assert removed.rowcount == 0  # type: ignore[attr-defined]


def test_iso_04_cannot_join_a_foreign_tenant(db: Database, world: World) -> None:
    with (
        pytest.raises(ProgrammingError, match="row-level security"),
        db.transaction(principal_id=world.a_user) as session,
    ):
        session.execute(
            text("INSERT INTO memberships (id, tenant_id, user_id, role) VALUES (gen_random_uuid(), :b, :u, 'owner')"),
            {"b": world.b_tenant, "u": world.a_user},
        )


def test_iso_05_users_tenants_and_sessions(db: Database, world: World) -> None:
    with db.transaction(tenant_id=world.a_tenant, principal_id=world.a_user) as session:
        assert session.execute(text("SELECT count(*) FROM users WHERE id = :u"), {"u": world.b_user}).scalar_one() == 0
        assert (
            session.execute(text("SELECT count(*) FROM tenants WHERE id = :b"), {"b": world.b_tenant}).scalar_one() == 0
        )
        assert (
            session.execute(
                text("SELECT count(*) FROM login_sessions WHERE user_id = :u"), {"u": world.b_user}
            ).scalar_one()
            == 0
        )
        revoked = session.execute(
            text("UPDATE login_sessions SET revoked_at = now() WHERE user_id = :u"), {"u": world.b_user}
        )
        assert revoked.rowcount == 0  # type: ignore[attr-defined]


def test_iso_06_append_only_tables_and_no_ddl(db: Database, world: World) -> None:
    for statement in (
        "UPDATE audit_events SET action = 'x' WHERE tenant_id = :a",
        "DELETE FROM usage_events WHERE tenant_id = :a",
        "ALTER TABLE memberships DISABLE ROW LEVEL SECURITY",
        "SET LOCAL row_security = off; SELECT count(*) FROM memberships",
    ):
        with pytest.raises(DBAPIError), db.transaction(tenant_id=world.a_tenant, principal_id=world.a_user) as session:
            session.execute(text(statement), {"a": world.a_tenant})


def test_iso_07_definer_lookups_are_narrow(db: Database, world: World) -> None:
    with db.transaction() as session:
        assert (
            session.execute(
                text("SELECT workx_is_active_member(:t, :u)"), {"t": world.b_tenant, "u": world.a_user}
            ).scalar()
            is False
        )
        assert session.execute(text("SELECT * FROM workx_session_by_hash('\\x00'::bytea)")).first() is None
        assert session.execute(text("SELECT workx_invitation_tenant('\\x00'::bytea)")).scalar() is None


def test_iso_08_api_returns_404_across_tenants(new_client: Callable[[], TestClient], oidc: TestClient) -> None:
    a, b = new_client(), new_client()
    sign_in(a, oidc)
    sign_in(b, oidc)
    org = create_org(a)
    for path in ("", "/members", "/departments", "/invitations", "/audit-events"):
        assert b.get(f"/api/v1/tenants/{org['id']}{path}").status_code == 404, path
    assert b.patch(f"/api/v1/tenants/{org['id']}", json={"name": "x"}).status_code == 404
