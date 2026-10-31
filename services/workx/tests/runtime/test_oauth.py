"""User OAuth connections and remote MCP (Part 6 §4, Part 4 §11; backlog B-16), against the test provider
(``workx dev-notes``): discovery (RFC 9728/8414), dynamic client registration, code + PKCE, single-use state,
single-flight refresh with rotating refresh tokens, the needs_auth preflight, a mid-run pause when the provider
revokes access, and resume after the user authorizes again."""

from __future__ import annotations

import importlib.util
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from tests.runtime.test_vertical_slice import Stack, User, start_one
from tests.support.servers import Served
from workx.core import ids
from workx.core.db import Database
from workx.core.settings import Environment, TrustedSettings
from workx.domains.connections import catalog
from workx.domains.connections.models import Connection
from workx.entrypoints.worker import build_context
from workx.platform import jobs
from workx.trusted.broker.app import vault_for
from workx.trusted.credentials import oauth


def stats(notes: Served) -> dict[str, Any]:
    return dict(httpx.get(f"{notes.url}/_stats").json())


def install_notes(user: User, notes: Served) -> None:
    response = user.client.put(
        f"{user.t}/connectors/notes/installation", json={"enabled": True, "config": {"base_url": f"{notes.url}/mcp"}}
    )
    assert response.status_code == 200, response.text


def connect(user: User, *, allow: bool = True, connection_id: str | None = None) -> tuple[str, str]:
    """Creates (or re-authorizes) the member's Notes connection through the real redirect dance."""
    if connection_id is None:
        created = user.client.post(f"{user.t}/connections", json={"connector_id": "notes", "name": "My notes"})
        assert created.status_code == 201, created.text
        assert created.json()["status"] == "pending"
        connection_id = created.json()["id"]
    started = user.client.post(f"{user.t}/connections/{connection_id}/authorize", json={"return_to": "/settings"})
    assert started.status_code == 200, started.text
    url = started.json()["authorize_url"]
    query = dict(httpx.URL(url).params)
    assert query["code_challenge_method"] == "S256" and query["resource"].endswith("/mcp")
    page = httpx.get(url)
    assert page.status_code == 200 and "Allow WorkX" in page.text
    decided = httpx.post(
        url.split("?")[0], data={**query, "decision": "allow" if allow else "deny", "account": "pat@example.com"}
    )
    assert decided.status_code == 302
    callback = urlparse(decided.headers["location"])
    finished = user.client.get(f"{callback.path}?{callback.query}", follow_redirects=False)
    assert finished.status_code == 303
    return connection_id, finished.headers["location"]


def drain(api_app: FastAPI, db: Database) -> None:
    ctx = build_context(api_app.state.workx.settings, db)
    while sum(n for status, n in jobs.run_once(ctx, "w-oauth").items() if status != "dispatched"):
        pass


def connection_row(owner_db: Database, connection_id: str) -> Connection:
    with owner_db.transaction() as session:
        row = session.get(Connection, ids.decode("connection", connection_id))
        assert row is not None
        session.expunge(row)
        return row


def test_connect_with_discovery_registration_and_pkce(
    stack: Stack, user: User, notes: Served, owner_db: Database
) -> None:
    install_notes(user, notes)
    before = stats(notes)
    connection_id, landing = connect(user)
    assert landing.endswith("/settings?connection=authorized")
    row = connection_row(owner_db, connection_id)
    assert (row.status, row.external_account, sorted(row.granted_scopes)) == (
        "active",
        "pat@example.com",
        ["notes.read", "notes.write"],
    )
    assert stats(notes)["register"] == before["register"] + 1  # dynamic client registration, once per workspace
    installed = next(c for c in user.client.get(f"{user.t}/connectors").json() if c["id"] == "notes")
    assert installed["installed"]
    # Tokens are stored as secret versions only the broker role can read.
    with owner_db.transaction() as session:
        kinds = (
            session.execute(
                text("SELECT kind FROM credentials WHERE connection_id = :c ORDER BY kind"),
                {"c": ids.decode("connection", connection_id)},
            )
            .scalars()
            .all()
        )
    assert kinds == ["oauth_access", "oauth_refresh"]
    # A second authorization reuses the registered client.
    _, again = connect(user, connection_id=connection_id)
    assert again.endswith("connection=authorized") and stats(notes)["register"] == before["register"] + 1


def test_state_is_single_use_and_bound_to_the_user(
    stack: Stack, user: User, notes: Served, new_client: Any, oidc: Any
) -> None:
    from tests.support.auth import sign_in

    install_notes(user, notes)
    created = user.client.post(f"{user.t}/connections", json={"connector_id": "notes", "name": "Notes"}).json()
    url = user.client.post(f"{user.t}/connections/{created['id']}/authorize", json={}).json()["authorize_url"]
    query = dict(httpx.URL(url).params)
    location = urlparse(httpx.post(url.split("?")[0], data={**query, "decision": "allow"}).headers["location"])
    callback = f"{location.path}?{location.query}"
    # Someone else's browser cannot complete it.
    stranger = new_client()
    sign_in(stranger, oidc)
    assert stranger.get(callback, follow_redirects=False).headers["location"].endswith("connection=invalid")
    # The state was spent by that attempt too: the real user cannot replay it either.
    assert user.client.get(callback, follow_redirects=False).headers["location"].endswith("connection=invalid")
    # Denying consent leaves the connection waiting.
    _, denied = connect(user, allow=False, connection_id=created["id"])
    assert denied.endswith("connection=denied")


def test_remote_mcp_tool_runs_as_the_user(stack: Stack, user: User, notes: Served) -> None:
    install_notes(user, notes)
    connect(user)
    before = stats(notes)["notes"]
    task = user.task("SCENARIO:notes remember to call Contoso")
    assert stack.orchestrator.run(start_one(stack, task["id"])) == "succeeded"
    finished = [
        e["payload"]
        for e in user.client.get(f"{user.t}/tasks/{task['id']}/events").json()
        if e["type"] == "tool.finished"
    ]
    assert finished and finished[0]["tool"] == "notes_create" and not finished[0]["is_error"]
    assert stats(notes)["notes"] == before + 1


def test_refresh_is_single_flight(
    stack: Stack, user: User, notes: Served, owner_db: Database, broker_db: Database
) -> None:
    install_notes(user, notes)
    connection_id, _ = connect(user)
    uid = ids.decode("connection", connection_id)
    with owner_db.transaction() as session:  # the stored access token is about to expire
        session.execute(
            text(
                "UPDATE secret_versions SET not_after = now() - interval '1 minute' WHERE state = 'active' AND "
                "credential_id = (SELECT id FROM credentials WHERE connection_id = :c AND kind = 'oauth_access')"
            ),
            {"c": uid},
        )
    before = stats(notes)
    vault = vault_for(TrustedSettings(environment=Environment.TEST))
    tenant = ids.decode("tenant", user.tenant)
    results: list[str] = []

    def use() -> None:
        with broker_db.transaction(tenant_id=tenant) as session, httpx.Client(timeout=10) as http:
            connection = session.get(Connection, uid)
            assert connection is not None
            results.append(oauth.access_token(session, vault, connection, catalog.CONNECTORS["notes"], http))

    threads = [threading.Thread(target=use) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    after = stats(notes)
    # One refresh; the other three waited and used the new token (a second refresh would have been refused).
    assert after["token_refresh"] == before["token_refresh"] + 1
    assert after["refresh_refused"] == before["refresh_refused"]
    assert len(results) == 4 and len(set(results)) == 1


def test_preflight_needs_auth_then_resumes_after_authorization(
    stack: Stack, user: User, notes: Served, api_app: FastAPI, db: Database
) -> None:
    install_notes(user, notes)
    assert user.client.patch(f"{user.t}/agents/{user.agent}", json={"connectors": ["notes"]}).status_code == 200
    task = user.task("SCENARIO:notes remember to call Contoso")
    jobs.dispatch_outbox(stack.orchestrator.db)
    with stack.orchestrator.db.transaction() as session:
        session.execute(
            text("DELETE FROM jobs WHERE kind = 'run_task' AND status = 'queued' AND payload->>'task_id' <> :t"),
            {"t": str(ids.decode("task", task["id"]))},
        )
    assert not [s for s in stack.orchestrator.claim_and_start() if ids.encode("task", s.task_id) == task["id"]]
    detail = user.get(task["id"])
    assert detail["status"] == "needs_auth" and detail["status_reason"] == "needs_auth:notes"
    events = [e["type"] for e in user.client.get(f"{user.t}/tasks/{task['id']}/events").json()]
    assert "auth.required" in events and "run.started" not in events  # no sandbox was created
    connect(user)
    drain(api_app, db)
    assert user.get(task["id"])["status"] == "queued"
    assert stack.orchestrator.run(start_one(stack, task["id"])) == "succeeded"


ENGINES = ["messages"]
_sdk = importlib.util.find_spec("claude_agent_sdk")
if _sdk and _sdk.origin and (Path(_sdk.origin).parent / "_bundled" / "claude").exists():
    ENGINES.append("claude-agent-sdk")


@pytest.mark.parametrize("engine", ENGINES)
def test_provider_revocation_pauses_the_run_and_resumes(
    engine: str, stack: Stack, user: User, notes: Served, owner_db: Database, api_app: FastAPI, db: Database
) -> None:
    install_notes(user, notes)
    connection_id, _ = connect(user)
    httpx.post(f"{notes.url}/_admin/revoke")  # the user revoked WorkX at the provider; WorkX does not know yet
    stack.orchestrator.settings.runner_engine = engine
    try:
        scenario = "notes" if engine == "messages" else "sdknotes"
        task = user.task(f"SCENARIO:{scenario} remember to call Contoso")
        status = stack.orchestrator.run(start_one(stack, task["id"]))
        events = user.client.get(f"{user.t}/tasks/{task['id']}/events").json()
        assert status == "needs_auth", [(e["type"], e["payload"]) for e in events][-6:]
        assert connection_row(owner_db, connection_id).status == "needs_auth"
        with owner_db.transaction() as session:
            pending = session.execute(
                text("SELECT count(*) FROM authorization_requests WHERE task_id = :t AND status = 'pending'"),
                {"t": ids.decode("task", task["id"])},
            ).scalar_one()
        assert pending == 1
        # The user authorizes again: the task is queued and the next attempt completes the write once.
        before = stats(notes)["notes"]
        connect(user, connection_id=connection_id)
        drain(api_app, db)
        assert user.get(task["id"])["status"] == "queued"
        assert stack.orchestrator.run(start_one(stack, task["id"])) == "succeeded"
        assert stats(notes)["notes"] == before + 1
    finally:
        stack.orchestrator.settings.runner_engine = "messages"
