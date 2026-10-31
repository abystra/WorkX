"""Workspace API (P-04): agents with immutable versions, projects, files, automations, scenarios, tasks, sharing."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.integration.test_tenancy import add_member, create_org
from tests.support.auth import idem, sign_in
from workx.core import ids
from workx.core.db import Database


class Team:
    def __init__(self, new_client: Callable[[], TestClient], oidc: TestClient, owner_db: Database) -> None:
        self.owner, self.admin, self.alice, self.bob = (new_client() for _ in range(4))
        self.me = {name: sign_in(getattr(self, name), oidc) for name in ("owner", "admin", "alice", "bob")}
        self.org = create_org(self.owner)
        self.t = f"/api/v1/tenants/{self.org['id']}"
        self.members = {
            "admin": add_member(owner_db, self.org["id"], self.me["admin"]["id"], "admin"),
            "alice": add_member(owner_db, self.org["id"], self.me["alice"]["id"]),
            "bob": add_member(owner_db, self.org["id"], self.me["bob"]["id"]),
        }

    def agent(self, client: TestClient, **body: Any) -> dict[str, Any]:
        response = client.post(f"{self.t}/agents", json={"name": "Writer", "description": "Drafts", **body})
        assert response.status_code == 201, response.text
        return dict(response.json())


@pytest.fixture
def team(new_client: Callable[[], TestClient], oidc: TestClient, owner_db: Database) -> Team:
    return Team(new_client, oidc, owner_db)


def test_models_and_skills_catalog(team: Team) -> None:
    assert [m["id"] for m in team.alice.get("/api/v1/models").json()] == ["auto", "opus", "sonnet", "haiku"]
    assert "deep-research" in {s["id"] for s in team.alice.get("/api/v1/skills").json()}


def test_agent_versions_are_published_and_immutable(team: Team, owner_db: Database) -> None:
    agent = team.agent(team.alice, instructions="Be brief.")
    assert agent["version"] == 1 and agent["actions"] == sorted(
        ["read", "use", "comment", "edit", "share", "delete", "export", "approve"]
    )
    url = f"{team.t}/agents/{agent['id']}"
    assert team.alice.patch(url, json={"name": "Writer 2"}).json()["version"] == 1  # cosmetic: no new version
    updated = team.alice.patch(url, json={"instructions": "Be thorough.", "add_skill": "Deep Research"}).json()
    assert updated["version"] == 2 and updated["skills"] == ["deep-research"]
    assert team.alice.patch(url, json={"add_skill": "teleportation"}).status_code == 400
    versions = team.alice.get(f"{url}/versions").json()
    assert [v["version"] for v in versions] == [2, 1]
    with pytest.raises(DBAPIError, match="immutable"), owner_db.transaction() as session:
        session.execute(
            text("UPDATE agent_versions SET instructions = 'tampered' WHERE agent_id = :a"),
            {"a": ids.decode("agent", agent["id"])},
        )


def test_agent_sharing_and_admin_without_grant(team: Team) -> None:
    agent = team.agent(team.alice)
    url = f"{team.t}/agents/{agent['id']}"
    assert team.admin.get(url).status_code == 404  # management role ≠ content access
    assert agent["id"] not in {a["id"] for a in team.bob.get(f"{team.t}/agents").json()}
    shared = team.alice.put(f"{team.t}/resources/agents/{agent['id']}/sharing", json={"visibility": "organization"})
    assert shared.status_code == 200 and shared.json()["visibility"] == "organization"
    assert team.bob.get(url).json()["actions"] == ["read", "use"]
    assert team.bob.patch(url, json={"name": "Mine now"}).status_code == 403
    assert agent["id"] in team.alice.get(f"{team.t}/shared-agents").json()
    team.alice.put(
        f"{team.t}/resources/agents/{agent['id']}/sharing",
        json={"visibility": "selected", "member_ids": [team.members["bob"]], "actions": ["edit"]},
    )
    assert team.bob.patch(url, json={"name": "Edited by Bob"}).status_code == 200
    assert team.admin.get(url).status_code == 404
    assert (
        team.bob.put(f"{team.t}/resources/agents/{agent['id']}/sharing", json={"visibility": "private"}).status_code
        == 403
    )
    assert team.bob.delete(url).status_code == 403
    assert team.alice.delete(url).status_code == 204 and team.alice.get(url).status_code == 404


def test_projects_roster_and_member_access(team: Team) -> None:
    project = team.alice.post(f"{team.t}/projects", json={"name": "Launch", "description": "Q4"}).json()
    url = f"{team.t}/projects/{project['id']}"
    assert team.bob.get(url).status_code == 404
    agent = team.agent(team.alice)
    roster = team.alice.put(f"{url}/roster", json={"member_ids": [team.members["bob"]], "agent_ids": [agent["id"]]})
    assert roster.status_code == 200 and set(roster.json()["member_ids"]) == {
        team.members["bob"],
        roster.json()["resource_owner_id"],
    }
    bob_view = team.bob.get(url).json()
    assert bob_view["actions"] == ["comment", "read", "use"]
    assert team.bob.patch(url, json={"shared_context": "Ship by Friday"}).json()["shared_context"] == "Ship by Friday"
    assert team.bob.patch(url, json={"name": "Renamed"}).status_code == 403
    assert team.alice.put(f"{url}/roster", json={"member_ids": ["mem_" + "0" * 26]}).status_code == 400
    # Files in the project are visible to project members.
    file = team.alice.post(
        f"{team.t}/files", json={"name": "Brief.md", "content": "# Brief", "project_id": project["id"]}
    ).json()
    assert team.bob.get(f"{team.t}/files/{file['id']}").json()["content"] == "# Brief"
    assert team.admin.get(f"{team.t}/files/{file['id']}").status_code == 404
    # Removing Bob from the roster removes that access.
    team.alice.put(f"{url}/roster", json={"member_ids": []})
    assert team.bob.get(url).status_code == 404


def test_tasks_lifecycle_without_execution(team: Team) -> None:
    agent = team.agent(team.alice)
    key = idem()
    body = {"agent_id": agent["id"], "prompt": "  Summarize this week's   project updates  ", "model_tier": "sonnet"}
    first = team.alice.post(f"{team.t}/tasks", json=body, headers=key)
    again = team.alice.post(f"{team.t}/tasks", json=body, headers=key)
    assert first.status_code == again.status_code == 202 and first.json()["id"] == again.json()["id"]
    task = first.json()
    assert task["status"] == "queued" and task["name"] == "Summarize this week's project updates"
    assert task["agent_version_id"] and first.headers["location"].endswith(task["id"])
    url = f"{team.t}/tasks/{task['id']}"
    detail = team.alice.get(url).json()
    assert [m["role"] for m in detail["messages"]] == ["user"]
    # Personal state is per member; the task stays private to its initiator.
    assert team.alice.patch(url, json={"pinned": True}).json()["pinned"] is True
    assert team.bob.get(url).status_code == 404
    # Assigning Bob gives Bob access; his own pin is independent.
    team.alice.patch(url, json={"assignee_id": team.members["bob"]})
    assert team.bob.get(url).json()["pinned"] is False
    # Cancelling a queued task finishes it; a follow-up queues it again.
    assert team.alice.post(f"{url}/cancel").json()["status"] == "cancelled"
    assert team.alice.post(f"{url}/cancel").json()["code"] == "INVALID_STATE"
    follow = team.alice.post(f"{url}/messages", json={"prompt": "Add risks too"})
    assert follow.status_code == 202 and follow.json()["status"] == "queued"
    assert [m["content"] for m in team.alice.get(url).json()["messages"]][-1] == "Add risks too"
    assert team.alice.post(f"{team.t}/tasks", json={**body, "model_tier": "gpt"}, headers=idem()).status_code == 400
    # Using someone else's private agent is not allowed.
    assert team.bob.post(f"{team.t}/tasks", json={**body}, headers=idem()).status_code == 404


def test_automations_and_scenarios(team: Team) -> None:
    created = team.alice.post(
        f"{team.t}/automations", json={"name": "Weekly report", "schedule": "0 9 * * 1", "timezone": "Asia/Shanghai"}
    )
    assert created.status_code == 201 and created.json()["next_run_at"].endswith("+08:00")
    bad = team.alice.post(f"{team.t}/automations", json={"name": "x", "schedule": "every day"})
    assert bad.status_code == 400 and "cron" in bad.json()["detail"]
    url = f"{team.t}/automations/{created.json()['id']}"
    assert team.alice.patch(url, json={"enabled": False}).json()["next_run_at"] is None
    assert team.bob.get(f"{team.t}/automations").json() == []
    scenario = team.alice.post(
        f"{team.t}/scenarios", json={"name": "Weekly ops", "problem": "Collect updates", "ecosystems": ["feishu"]}
    ).json()
    assert team.alice.get(f"{team.t}/scenarios").json()[0]["id"] == scenario["id"]
    assert (
        team.alice.post(f"{team.t}/scenarios", json={"name": "x", "problem": "", "ecosystems": []}).status_code == 400
    )


def test_event_stream_delivers_resumes_and_closes_on_revocation(
    team: Team, api_app: Any, new_client: Callable[[], TestClient], oidc: TestClient
) -> None:
    agent = team.agent(team.alice)
    team.alice.post(f"{team.t}/tasks", json={"agent_id": agent["id"], "prompt": "One"}, headers=idem())
    with team.alice.stream("GET", f"{team.t}/events", params={"after": 0, "max_seconds": 1.5}) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())
    assert "event: task.queued" in body and "event: agent.created" in body
    last_id = max(int(line[4:]) for line in body.splitlines() if line.startswith("id: "))
    team.alice.post(f"{team.t}/tasks", json={"agent_id": agent["id"], "prompt": "Two"}, headers=idem())
    with team.alice.stream(
        "GET", f"{team.t}/events", params={"max_seconds": 1.5}, headers={"Last-Event-ID": str(last_id)}
    ) as response:
        resumed = "".join(response.iter_text())
    assert resumed.count("event: task.queued") == 1
    # Bob is not in the audience of Alice's private task events.
    with team.bob.stream("GET", f"{team.t}/events", params={"after": 0, "max_seconds": 1.2}) as response:
        assert "task.queued" not in "".join(response.iter_text())
    # Revoking the session from another device ends an already-open stream at the next check.
    phone = new_client()
    sign_in(phone, oidc, team.me["alice"]["email"])
    laptop_session = next(x for x in phone.get("/api/v1/me/sessions").json() if not x["current"])
    settings = api_app.state.workx.settings
    original, settings.sse_revalidate_seconds = settings.sse_revalidate_seconds, 0.5
    try:
        timer = threading.Timer(0.4, lambda: phone.delete(f"/api/v1/me/sessions/{laptop_session['id']}"))
        timer.start()
        started = time.monotonic()
        with team.alice.stream("GET", f"{team.t}/events", params={"max_seconds": 10}) as response:
            closing = "".join(response.iter_text())
        timer.join()
        assert "event: stream.closed" in closing and time.monotonic() - started < 5
        assert team.alice.get(f"{team.t}/events").status_code == 401
    finally:
        settings.sse_revalidate_seconds = original


def test_task_list_carries_conversation_summary(team: Team, owner_db: Database) -> None:
    agent = team.agent(team.alice)
    task = team.alice.post(f"{team.t}/tasks", json={"agent_id": agent["id"], "prompt": "First"}, headers=idem()).json()
    team.alice.post(f"{team.t}/tasks/{task['id']}/messages", json={"prompt": "Second"})
    with owner_db.transaction() as session:
        session.execute(
            text(
                "INSERT INTO task_messages (id, tenant_id, task_id, role, content)"
                " SELECT gen_random_uuid(), tenant_id, id, 'assistant', 'Here is the summary' FROM tasks WHERE id = :t"
            ),
            {"t": ids.decode("task", task["id"])},
        )
    [listed] = [t for t in team.alice.get(f"{team.t}/tasks").json() if t["id"] == task["id"]]
    assert (
        listed["answer"] == "Here is the summary" and listed["follow_ups"] == ["Second"] and listed["messages"] is None
    )


def test_new_workspaces_start_with_one_workmate(team: Team) -> None:
    """Approved baseline: every workspace has a workmate to talk to. Org starters are shared; personal ones private."""
    [starter] = [a for a in team.bob.get(f"{team.t}/agents").json() if a["name"] == "My Workmate"]
    assert starter["visibility"] == "organization" and starter["actions"] == ["read", "use"]
    personal = next(t for t in team.bob.get("/api/v1/me/tenants").json() if t["type"] == "personal")
    [mine] = team.bob.get(f"/api/v1/tenants/{personal['id']}/agents").json()
    assert mine["visibility"] == "private" and mine["version"] == 1
