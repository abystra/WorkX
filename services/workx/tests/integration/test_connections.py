"""Credentials and connections (Part 6; backlog B-15, B-17, B-18)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError

from tests.integration.test_tenancy import add_member, create_org
from tests.support.auth import idem, sign_in
from workx.core import ids
from workx.core.db import Database
from workx.core.orm import utcnow
from workx.domains.connections import resolve
from workx.domains.connections.broker_client import BrokerClient
from workx.domains.connections.models import Credential
from workx.domains.tenancy.models import Membership
from workx.entrypoints.worker import build_context
from workx.platform import jobs
from workx.trusted.credentials.models import SecretVersion

SECRET = "crm-key-WORKX_CANARY_ab12cd34ef"


def _org(new_client: Callable[[], TestClient], oidc: TestClient, owner_db: Database) -> dict[str, Any]:
    owner, member = new_client(), new_client()
    sign_in(owner, oidc)
    member_me = sign_in(member, oidc)
    org = create_org(owner)
    member_id = add_member(owner_db, org["id"], member_me["id"])
    base = f"/api/v1/tenants/{org['id']}"
    assert owner.put(f"{base}/connectors/crm/installation", json={"enabled": True}).status_code == 200
    return {"owner": owner, "member": member, "org": org, "base": base, "member_id": member_id}


def test_secrets_are_encrypted_and_unreadable_by_the_api_role(
    new_client: Callable[[], TestClient], oidc: TestClient, owner_db: Database, db: Database, broker_db: Database
) -> None:
    w = _org(new_client, oidc, owner_db)
    created = w["owner"].post(
        f"{w['base']}/connections", json={"connector_id": "crm", "name": "CRM", "scope": "tenant", "secret": SECRET}
    )
    assert created.status_code == 201 and created.json()["status"] == "active"
    assert SECRET not in created.text and SECRET not in w["owner"].get(f"{w['base']}/connections").text
    connection_id = ids.decode("connection", created.json()["id"])
    with owner_db.transaction() as session:
        row = session.execute(
            select(SecretVersion)
            .join(Credential, Credential.id == SecretVersion.credential_id)
            .where(Credential.connection_id == connection_id)
        ).scalar_one()
        assert SECRET.encode() not in row.ciphertext and row.state == "active" and len(row.wrapped_dek) > 32
        audit = (
            session.execute(text("SELECT data::text FROM audit_events WHERE target_id = :c"), {"c": connection_id})
            .scalars()
            .all()
        )
        assert audit and all(SECRET not in a for a in audit)
    # The API/worker role has no privilege on secret material at all, even inside the tenant.
    tenant = ids.decode("tenant", w["org"]["id"])
    with pytest.raises(ProgrammingError, match="permission denied"), db.transaction(tenant_id=tenant) as session:
        session.execute(text("SELECT ciphertext FROM secret_versions"))
    # A ciphertext moved to another row does not decrypt (associated data binds tenant/credential/version).
    from workx.core.settings import Environment, TrustedSettings
    from workx.trusted.broker.app import vault_for

    vault = vault_for(TrustedSettings(environment=Environment.TEST))
    with broker_db.transaction(tenant_id=tenant) as session:
        credential = session.execute(select(Credential).where(Credential.connection_id == connection_id)).scalar_one()
        assert vault.read(session, credential)[0] == SECRET
        version = session.get(SecretVersion, credential.active_version_id)
        assert version is not None
        version.version_no = 99
        from cryptography.exceptions import InvalidTag

        with pytest.raises(InvalidTag):
            vault.read(session, credential)
        session.rollback()


def test_scope_and_visibility_rules(new_client: Callable[[], TestClient], oidc: TestClient, owner_db: Database) -> None:
    w = _org(new_client, oidc, owner_db)
    shared = w["member"].post(
        f"{w['base']}/connections", json={"connector_id": "crm", "name": "x", "scope": "tenant", "secret": "k"}
    )
    assert shared.status_code == 403
    mine = w["member"].post(
        f"{w['base']}/connections", json={"connector_id": "crm", "name": "Mine", "scope": "member", "secret": "k"}
    )
    assert mine.status_code == 201
    assert (
        w["member"]
        .post(f"{w['base']}/connections", json={"connector_id": "crm", "name": "x", "secret": None})
        .status_code
        == 400
    )
    assert w["member"].post(f"{w['base']}/connections", json={"connector_id": "web", "name": "x"}).status_code == 400
    oauth_shared = w["owner"].post(
        f"{w['base']}/connections", json={"connector_id": "notes", "name": "x", "scope": "tenant"}
    )
    assert oauth_shared.status_code in (400, 409)
    # Admins see metadata of a member's private connection (to revoke it), never its value; other members don't see it.
    assert [c["name"] for c in w["owner"].get(f"{w['base']}/connections").json()] == ["Mine"]
    other = new_client()
    other_me = sign_in(other, oidc)
    add_member(owner_db, w["org"]["id"], other_me["id"])
    assert other.get(f"{w['base']}/connections").json() == []
    assert other.delete(f"{w['base']}/connections/{mine.json()['id']}").status_code == 404
    assert w["owner"].delete(f"{w['base']}/connections/{mine.json()['id']}").status_code == 204


def test_usage_policy_decides_who_gets_tools(
    new_client: Callable[[], TestClient], oidc: TestClient, owner_db: Database, db: Database
) -> None:
    w = _org(new_client, oidc, owner_db)
    created = (
        w["owner"]
        .post(f"{w['base']}/connections", json={"connector_id": "crm", "name": "CRM", "scope": "tenant", "secret": "k"})
        .json()
    )
    tenant = ids.decode("tenant", w["org"]["id"])
    member_uuid = ids.decode("membership", w["member_id"])

    def tools() -> list[str]:
        with db.transaction(tenant_id=tenant) as session:
            member = session.get(Membership, member_uuid)
            assert member is not None
            return resolve.resolve(
                session, tenant_id=tenant, initiator=member, agent_id=ids.uuid7(), project_id=None
            ).tools

    # Default: a new shared connection empowers nobody (Part 6 §2 rule 3).
    assert tools() == ["web_fetch"]
    url = f"{w['base']}/connections/{created['id']}/usage-policy"
    assert (
        w["owner"]
        .put(url, json=[{"principal_type": "role", "principal_ref": "member", "allowed_tools": ["crm_list_accounts"]}])
        .status_code
        == 200
    )
    assert tools() == ["web_fetch", "crm_list_accounts"]
    assert w["member"].put(url, json=[]).status_code in (403, 404)
    assert (
        w["owner"]
        .put(url, json=[{"principal_type": "role", "principal_ref": "member", "allowed_tools": ["rm_rf"]}])
        .status_code
        == 400
    )
    # Workmate rules come back with public ids and show as the connection's bound workmates.
    agent = w["owner"].get(f"{w['base']}/agents").json()[0]["id"]
    rule = {"principal_type": "agent", "principal_ref": agent, "allowed_tools": ["crm_list_accounts"]}
    assert w["owner"].put(url, json=[rule]).status_code == 200
    assert w["owner"].get(url).json() == [rule]
    [listed] = w["owner"].get(f"{w['base']}/connections").json()
    assert listed["agent_ids"] == [agent]


def test_rotation_and_shredding(
    new_client: Callable[[], TestClient], oidc: TestClient, owner_db: Database, broker_db: Database
) -> None:
    w = _org(new_client, oidc, owner_db)
    created = (
        w["owner"]
        .post(
            f"{w['base']}/connections",
            json={"connector_id": "crm", "name": "CRM", "scope": "tenant", "secret": "old-key"},
        )
        .json()
    )
    assert (
        w["owner"].post(f"{w['base']}/connections/{created['id']}/secret", json={"secret": "new-key"}).status_code
        == 200
    )
    from workx.core.settings import Environment, TrustedSettings
    from workx.trusted.broker.app import vault_for

    vault = vault_for(TrustedSettings(environment=Environment.TEST))
    tenant = ids.decode("tenant", w["org"]["id"])
    with broker_db.transaction(tenant_id=tenant) as session:
        credential = session.execute(
            select(Credential).where(Credential.connection_id == ids.decode("connection", created["id"]))
        ).scalar_one()
        assert vault.read(session, credential)[0] == "new-key"
        states = session.execute(
            select(SecretVersion.version_no, SecretVersion.state)
            .where(SecretVersion.credential_id == credential.id)
            .order_by(SecretVersion.version_no)
        ).all()
        assert [tuple(s) for s in states] == [(1, "retiring"), (2, "active")]
        assert vault.destroy_retired(session, credential.id, now=utcnow() + timedelta(minutes=11)) == 1
        retired = session.execute(
            select(SecretVersion).where(SecretVersion.credential_id == credential.id, SecretVersion.version_no == 1)
        ).scalar_one()
        assert retired.state == "destroyed" and retired.ciphertext == b""


def _drain(ctx: jobs.JobContext) -> None:
    """Runs dispatch and jobs until nothing is left to claim."""
    while sum(n for status, n in jobs.run_once(ctx, "w-test").items() if status != "dispatched"):
        pass


def test_revocation_and_member_offboarding(
    new_client: Callable[[], TestClient],
    oidc: TestClient,
    owner_db: Database,
    db: Database,
    broker_http: TestClient,
    api_app: FastAPI,
    tmp_path: Path,
) -> None:
    w = _org(new_client, oidc, owner_db)
    with owner_db.transaction() as session:  # other tests leave events and jobs behind
        session.execute(text("UPDATE outbox_events SET dispatched_at = now() WHERE dispatched_at IS NULL"))
        session.execute(text("DELETE FROM jobs"))
    shared = (
        w["owner"]
        .post(f"{w['base']}/connections", json={"connector_id": "crm", "name": "CRM", "scope": "tenant", "secret": "k"})
        .json()
    )
    private = (
        w["member"]
        .post(
            f"{w['base']}/connections", json={"connector_id": "crm", "name": "Mine", "scope": "member", "secret": "k2"}
        )
        .json()
    )
    agent = w["member"].get(f"{w['base']}/agents").json()[0]["id"]
    task = w["member"].post(f"{w['base']}/tasks", json={"agent_id": agent, "prompt": "go"}, headers=idem()).json()
    ctx = build_context(api_app.state.workx.settings, db)
    ctx.services["broker"] = BrokerClient("http://testserver", "workx-dev-broker-token", broker_http)
    # Revoking the shared connection shreds its secrets through the broker (job).
    assert w["owner"].delete(f"{w['base']}/connections/{shared['id']}").status_code == 204
    _drain(ctx)
    with owner_db.transaction() as session:
        states = (
            session.execute(
                text(
                    "SELECT sv.state FROM secret_versions sv JOIN credentials c ON c.id = sv.credential_id"
                    " WHERE c.connection_id = :c"
                ),
                {"c": ids.decode("connection", shared["id"])},
            )
            .scalars()
            .all()
        )
        assert states == ["destroyed"]
    # Deactivating the member cancels their queued task and suspends their private connection.
    assert w["owner"].patch(f"{w['base']}/members/{w['member_id']}", json={"status": "deactivated"}).status_code == 200
    _drain(ctx)
    with owner_db.transaction() as session:
        status = session.execute(
            text("SELECT status, status_reason FROM tasks WHERE id = :t"), {"t": ids.decode("task", task["id"])}
        ).one()
        connection = session.execute(
            text("SELECT status FROM connections WHERE id = :c"), {"c": ids.decode("connection", private["id"])}
        ).scalar_one()
    assert tuple(status) == ("cancelled", "member_deactivated") and connection == "suspended"
