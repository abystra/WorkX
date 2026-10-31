"""Connector knowledge sync (R2, Part 7 §6): a member's connected Notes account becomes knowledge that only they
can search; it re-syncs periodically and disappears from search as soon as the connection is revoked."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.integration.test_knowledge import search
from tests.integration.test_tenancy import add_member
from tests.runtime.test_oauth import connect, install_notes
from tests.runtime.test_vertical_slice import Stack, User, start_one
from tests.support.auth import sign_in
from tests.support.servers import Served
from workx.core import ids
from workx.core.db import Database
from workx.domains.knowledge import service as knowledge
from workx.domains.resources import scheduler
from workx.entrypoints.worker import build_context
from workx.platform import jobs


def work(api_app: FastAPI, db: Database) -> None:
    ctx = build_context(api_app.state.workx.settings, db)
    services = api_app.state.workx.services
    ctx.services["broker"] = services["broker"]
    ctx.services["knowledge"] = knowledge.Services(
        db, services["objects"], services["embeddings"], broker=services["broker"]
    )
    for _ in range(10):
        if not sum(n for status, n in jobs.run_once(ctx, "w-sync").items() if status != "dispatched"):
            break


def test_connected_account_becomes_private_knowledge(
    stack: Stack,
    user: User,
    notes: Served,
    api_app: FastAPI,
    db: Database,
    owner_db: Database,
    new_client: Callable[[], TestClient],
    oidc: TestClient,
) -> None:
    install_notes(user, notes)
    connection_id, _ = connect(user)
    task = user.task("SCENARIO:notes remember the renewal")  # writes "Renewals: Call Contoso" to the service
    assert stack.orchestrator.run(start_one(stack, task["id"])) == "succeeded"
    created = user.client.post(f"{user.t}/knowledge-sources", json={"connection_id": connection_id})
    assert created.status_code == 201, created.text
    source = created.json()
    assert source["kind"] == "connector" and source["file_id"] is None
    work(api_app, db)
    detail = user.client.get(f"{user.t}/knowledge-sources/{source['id']}").json()
    assert detail["status"] == "ready" and detail["latest"]["parser"] == "connector"
    [hit] = [p for p in search(user.client, user.t, "call Contoso renewals") if p["source_id"] == source["id"]]
    assert hit["section"] == "Renewals" and hit["locator"]["document"].startswith("note_")
    # Another member of the organization cannot see or search it.
    other = new_client()
    add_member(owner_db, user.tenant, sign_in(other, oidc)["id"])
    assert other.get(f"{user.t}/knowledge-sources/{source['id']}").status_code == 404
    assert search(other, user.t, "call Contoso renewals", source_ids=[source["id"]]) == []
    # Periodic re-sync picks up new documents.
    second = user.task("SCENARIO:notes remember again")
    assert stack.orchestrator.run(start_one(stack, second["id"])) == "succeeded"
    with owner_db.transaction() as session:
        session.execute(
            text("UPDATE knowledge_sources SET last_synced_at = now() - interval '1 hour' WHERE id = :s"),
            {"s": ids.decode("knowledge_source", source["id"])},
        )
    ctx = build_context(api_app.state.workx.settings, db)
    scheduler.schedule_tick(ctx, datetime(2099, 1, 1, tzinfo=UTC))
    work(api_app, db)
    assert user.client.get(f"{user.t}/knowledge-sources/{source['id']}").json()["latest"]["revision"] == 2
    # Revoking the connection removes the knowledge from search at once.
    assert user.client.delete(f"{user.t}/connections/{connection_id}").status_code == 204
    assert search(user.client, user.t, "call Contoso renewals", source_ids=[source["id"]]) == []
