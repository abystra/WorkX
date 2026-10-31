"""A workmate with attached knowledge searches it through the Tool Gateway (as the task's initiator) and its
answer keeps only citations to passages actually returned to the task (Part 7 §4, §9; J7)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.integration.test_knowledge import POLICY_MD, drain, make_source, upload
from tests.integration.test_tenancy import add_member
from tests.runtime.test_vertical_slice import Stack, User, start_one
from tests.support.auth import idem, sign_in
from workx.core import ids
from workx.core.db import Database


def test_workmate_searches_and_cites_attached_knowledge(
    stack: Stack, user: User, api_app: FastAPI, db: Database
) -> None:
    file = upload(user.client, user.t, "travel-policy.md", POLICY_MD.encode(), "text/markdown")
    source = make_source(user.client, user.t, file["id"])
    drain(api_app, db)
    attached = user.client.put(f"{user.t}/agents/{user.agent}/knowledge", json={"source_ids": [source["id"]]})
    assert attached.status_code == 200, attached.text
    task = user.task("SCENARIO:knowledge hotel reimbursed per night")
    assert stack.orchestrator.run(start_one(stack, task["id"])) == "succeeded"
    events = user.client.get(f"{user.t}/tasks/{task['id']}/events").json()
    finished = [e["payload"] for e in events if e["type"] == "tool.finished"]
    assert finished[0]["tool"] == "knowledge_search" and not finished[0]["is_error"]
    answer = [m for m in user.get(task["id"])["messages"] if m["role"] == "assistant"][-1]
    # The valid citation is numbered; the made-up one is removed.
    assert "your documents say [1]" in answer["content"] and "knc_" not in answer["content"]
    [citation] = answer["citations"]
    assert citation["source"] == "travel-policy.md" and citation["section"] == "Travel Policy > Reimbursement"
    assert any(e["payload"].get("invalid_citations") == 1 for e in events if e["type"] == "assistant.message")


def test_knowledge_follows_the_initiators_access(
    stack: Stack,
    user: User,
    api_app: FastAPI,
    db: Database,
    owner_db: Database,
    new_client: Callable[[], TestClient],
    oidc: TestClient,
) -> None:
    """The workmate is shared, the file is not: another member's task gets no passages from it."""
    file = upload(
        user.client, user.t, "private.md", b"# Notes\n\nHotels are reimbursed per night at 999 EUR.\n", "text/markdown"
    )
    source = make_source(user.client, user.t, file["id"])
    drain(api_app, db)
    user.client.put(f"{user.t}/agents/{user.agent}/knowledge", json={"source_ids": [source["id"]]})
    assert (
        user.client.put(
            f"{user.t}/resources/agents/{user.agent}/sharing", json={"visibility": "organization"}
        ).status_code
        == 200
    )
    other = new_client()
    me = sign_in(other, oidc)
    add_member(owner_db, user.tenant, me["id"])
    created = other.post(
        f"{user.t}/tasks",
        json={"agent_id": user.agent, "prompt": "SCENARIO:knowledge hotels reimbursed per night"},
        headers=idem(),
    )
    assert created.status_code == 202, created.text
    assert stack.orchestrator.run(start_one(stack, created.json()["id"])) == "succeeded"
    with owner_db.transaction() as session:
        returned = session.execute(
            text("SELECT coalesce(sum(cardinality(chunk_ids)), 0) FROM retrieval_logs WHERE task_id = :t"),
            {"t": ids.decode("task", created.json()["id"])},
        ).scalar_one()
    assert returned == 0
    answer = [
        m for m in other.get(f"{user.t}/tasks/{created.json()['id']}").json()["messages"] if m["role"] == "assistant"
    ][-1]
    assert answer["citations"] == []
