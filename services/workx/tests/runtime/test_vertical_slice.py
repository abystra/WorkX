"""Vertical slice (Part 14 §2) with protocol-level fakes for Anthropic: task → orchestrator → sandbox (local
process) → Runner (messages engine) → Model Gateway → upstream, Runner → Tool Gateway → test CRM, artifact
ingestion, events, usage, cancel, crash recovery without duplicate writes, approvals, budgets, ticket scope."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text, update

import workx.domains.runtime.jobs  # noqa: F401  (registers task.queued → run_task)
from tests.conftest import ProvisionedDatabase
from tests.integration.test_tenancy import create_org
from tests.support.auth import idem, sign_in
from tests.support.fake_anthropic import UPSTREAM_KEY, create_fake_anthropic
from tests.support.servers import Served
from workx.core import ids
from workx.core.db import Database
from workx.core.orm import utcnow
from workx.core.settings import Environment, ModelGatewaySettings, OrchestratorSettings, ToolGatewaySettings
from workx.domains.runtime.models import TaskAttempt
from workx.domains.runtime.orchestrator import Orchestrator, Started, reconcile_expired_attempts
from workx.domains.runtime.sandbox import LocalProcessProvider, Sandbox
from workx.entrypoints.dev_crm import create_dev_crm_app
from workx.platform import jobs
from workx.trusted.model_gateway.app import create_model_gateway_app
from workx.trusted.tool_gateway.app import create_tool_gateway_app

CRM_KEY = "crm-test-key"
TIERS = {"auto": "test-model-auto", "sonnet": "test-model-sonnet"}


@dataclass
class Stack:
    upstream: Served
    crm: Served
    model_gw: Served
    tool_gw: Served
    orchestrator: Orchestrator
    captured_env: list[dict[str, str]]

    def crm_stats(self) -> dict[str, Any]:
        return dict(httpx.get(f"{self.crm.url}/_stats").json())


class CapturingProvider(LocalProcessProvider):
    """Records the environment each Runner is started with (canary check: no platform secrets)."""

    def __init__(self, captured: list[dict[str, str]]) -> None:
        import os

        super().__init__(keep_files=bool(os.environ.get("WORKX_KEEP_SANDBOX")))
        self.captured = captured

    def create(self, attempt_ref: str, *, timeout_seconds: int, allow_hosts: list[str]) -> Sandbox:
        sandbox = super().create(attempt_ref, timeout_seconds=timeout_seconds, allow_hosts=allow_hosts)
        original = sandbox.start_runner

        def start(spec_path: str, env: dict[str, str]) -> Any:
            self.captured.append(dict(env))
            return original(spec_path, env)

        sandbox.start_runner = start  # type: ignore[method-assign]
        return sandbox


@pytest.fixture(scope="package")
def stack(test_database: ProvisionedDatabase, db: Database, broker_db: Database, objects_dir: Path) -> Iterator[Stack]:
    base = {
        "environment": Environment.TEST,
        "database_url": test_database.app_url,
        "object_store_url": f"file:{objects_dir}",
    }
    upstream = Served(create_fake_anthropic())
    crm = Served(create_dev_crm_app(CRM_KEY, environment=Environment.TEST))
    model_gw = Served(
        create_model_gateway_app(
            ModelGatewaySettings(**base, anthropic_base_url=upstream.url, anthropic_api_key=UPSTREAM_KEY), db
        )
    )  # type: ignore[arg-type]
    tool_gw = Served(
        create_tool_gateway_app(ToolGatewaySettings(**base, crm_base_url=crm.url), broker_db)  # type: ignore[arg-type]
    )
    captured: list[dict[str, str]] = []
    settings = OrchestratorSettings(
        **base,
        model_tiers=TIERS,
        runner_engine="messages",
        model_gateway_url=model_gw.url,
        tool_gateway_url=tool_gw.url,  # type: ignore[arg-type]
        heartbeat_seconds=0.3,
        lease_seconds=30,
        wall_seconds=120,
        max_concurrent_attempts_per_tenant=5,
    )
    orchestrator = Orchestrator(db, settings, CapturingProvider(captured), "orch-test")
    yield Stack(upstream, crm, model_gw, tool_gw, orchestrator, captured)
    for server in (tool_gw, model_gw, crm, upstream):
        server.stop()


@dataclass
class User:
    client: TestClient
    me: dict[str, Any]
    tenant: str
    agent: str

    @property
    def t(self) -> str:
        return f"/api/v1/tenants/{self.tenant}"

    def task(self, prompt: str) -> dict[str, Any]:
        response = self.client.post(f"{self.t}/tasks", json={"agent_id": self.agent, "prompt": prompt}, headers=idem())
        assert response.status_code == 202, response.text
        return dict(response.json())

    def get(self, task_id: str) -> dict[str, Any]:
        return dict(self.client.get(f"{self.t}/tasks/{task_id}").json())


def connect_crm(client: TestClient, tenant: str) -> str:
    """Install the CRM connector, store its key as an org-shared connection (via the broker) and let members use it."""
    base = f"/api/v1/tenants/{tenant}"
    assert client.put(f"{base}/connectors/crm/installation", json={"enabled": True}).status_code == 200
    created = client.post(
        f"{base}/connections", json={"connector_id": "crm", "name": "Team CRM", "scope": "tenant", "secret": CRM_KEY}
    )
    assert created.status_code == 201, created.text
    connection = created.json()["id"]
    tools = ["crm_list_accounts", "crm_create_note", "crm_send_email"]
    policy = client.put(
        f"{base}/connections/{connection}/usage-policy", json=[{"principal_type": "tenant", "allowed_tools": tools}]
    )
    assert policy.status_code == 200, policy.text
    return str(connection)


@pytest.fixture
def user(new_client: Callable[[], TestClient], oidc: TestClient) -> User:
    client = new_client()
    me = sign_in(client, oidc)
    org = create_org(client, "Runtime Org")
    agent = client.get(f"/api/v1/tenants/{org['id']}/agents").json()[0]["id"]
    connect_crm(client, org["id"])
    return User(client, me, org["id"], agent)


def start_one(stack: Stack, task_id: str) -> Started:
    """Starts exactly this task: run_task jobs left by other test modules are cleared first."""
    jobs.dispatch_outbox(stack.orchestrator.db)
    with stack.orchestrator.db.transaction() as session:
        session.execute(
            text("DELETE FROM jobs WHERE kind = 'run_task' AND status = 'queued' AND payload->>'task_id' <> :t"),
            {"t": str(ids.decode("task", task_id))},
        )
    started = stack.orchestrator.claim_and_start()
    match = [s for s in started if ids.encode("task", s.task_id) == task_id]
    assert match, f"no attempt started for {task_id}: {started}"
    return match[0]


def run_background(stack: Stack, started: Started) -> tuple[threading.Thread, dict[str, str]]:
    result: dict[str, str] = {}
    thread = threading.Thread(target=lambda: result.setdefault("status", stack.orchestrator.run(started)), daemon=True)
    thread.start()
    return thread, result


def wait_for(predicate: Callable[[], bool], timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.1)


def test_slice_runs_end_to_end(
    stack: Stack, user: User, new_client: Callable[[], TestClient], oidc: TestClient, owner_db: Database
) -> None:
    task = user.task("Build a list of our top accounts from the CRM")
    notes_before = stack.crm_stats()["notes"]
    status = stack.orchestrator.run(start_one(stack, task["id"]))
    assert status == "succeeded"
    detail = user.get(task["id"])
    assert detail["status"] == "succeeded" and detail["unread"] is True
    answer = [m for m in detail["messages"] if m["role"] == "assistant"]
    assert answer[-1]["content"].startswith("Here are your top accounts") and answer[-1]["file_id"]
    file = user.client.get(f"{user.t}/files/{answer[-1]['file_id']}").json()
    assert file["name"] == "top-accounts.md" and "Northwind" in file["content"] and file["source_task_id"] == task["id"]
    events = [e["type"] for e in user.client.get(f"{user.t}/tasks/{task['id']}/events").json()]
    for expected in (
        "attempt.started",
        "run.started",
        "tool.started",
        "tool.finished",
        "artifact.staged",
        "artifact.available",
        "task.succeeded",
    ):
        assert expected in events, (expected, events)
    assert stack.crm_stats()["notes"] == notes_before + 1
    # The upstream saw the real key and the pinned model; the Runner never had the real key.
    assert all(
        s["key"] == UPSTREAM_KEY and s["model"] == TIERS["auto"] for s in stack.upstream.server.config.app.state.seen
    )
    env = stack.captured_env[-1]
    assert (
        set(env) == {"WORKX_MODEL_TICKET", "WORKX_TOOL_TICKET"}
        and UPSTREAM_KEY not in str(env)
        and CRM_KEY not in str(env)
    )
    with owner_db.transaction() as session:
        tenant = ids.decode("tenant", user.tenant)
        metered = dict(
            session.execute(
                text("SELECT kind, sum(quantity) FROM usage_events WHERE tenant_id = :t GROUP BY kind"), {"t": tenant}
            ).all()
        )
        assert metered["model_tokens"] > 0 and metered["tool_call"] == 2
        revoked = session.execute(
            text("SELECT bool_and(revoked_at IS NOT NULL) FROM credential_leases WHERE task_id = :k"),
            {"k": ids.decode("task", task["id"])},
        ).scalar()
        assert revoked is True
    # Another workspace cannot see the task, its events or its file.
    stranger = new_client()
    sign_in(stranger, oidc)
    for path in (f"tasks/{task['id']}", f"tasks/{task['id']}/events", f"files/{answer[-1]['file_id']}"):
        assert stranger.get(f"{user.t}/{path}").status_code == 404


def test_cancel_mid_run_revokes_tickets(stack: Stack, user: User) -> None:
    task = user.task("SCENARIO:slow please work slowly")
    started = start_one(stack, task["id"])
    thread, result = run_background(stack, started)
    wait_for(
        lambda: any(
            e["type"] == "assistant.delta" for e in user.client.get(f"{user.t}/tasks/{task['id']}/events").json()
        )
    )
    assert user.client.post(f"{user.t}/tasks/{task['id']}/cancel").status_code == 202
    thread.join(timeout=40)
    assert result.get("status") == "cancelled" and user.get(task["id"])["status"] == "cancelled"
    blocked = httpx.post(
        f"{stack.model_gw.url}/v1/messages",
        headers={"x-api-key": started.model_ticket},
        json={"model": TIERS["auto"], "messages": []},
    )
    assert blocked.status_code == 401


def test_crashed_orchestrator_then_retry_does_not_repeat_the_write(
    stack: Stack, user: User, owner_db: Database
) -> None:
    task = user.task("SCENARIO:slow then crash")
    notes_before = stack.crm_stats()["notes"]
    started = start_one(stack, task["id"])
    thread, result = run_background(stack, started)
    wait_for(lambda: stack.crm_stats()["notes"] == notes_before + 1)
    # Simulate the orchestrator dying: its lease expires and is no longer its own.
    with owner_db.transaction() as session:
        session.execute(
            update(TaskAttempt)
            .where(TaskAttempt.id == started.attempt_id)
            .values(lease_owner="dead-process", lease_expires_at=utcnow())
        )
    thread.join(timeout=15)
    assert result.get("status") == "fenced"
    assert reconcile_expired_attempts(stack.orchestrator.db) >= 1
    assert user.get(task["id"])["status"] == "interrupted"
    # Manual retry: a new Attempt with the next fence; the ledger returns the earlier note instead of writing again.
    assert user.client.post(f"{user.t}/tasks/{task['id']}/retry").status_code == 202
    second = start_one(stack, task["id"])
    assert second.fence == started.fence + 1
    thread, result = run_background(stack, second)
    wait_for(
        lambda: any(
            e["type"] == "tool.finished" and e["payload"].get("deduplicated")
            for e in user.client.get(f"{user.t}/tasks/{task['id']}/events").json()
        )
    )
    user.client.post(f"{user.t}/tasks/{task['id']}/cancel")
    thread.join(timeout=40)
    assert stack.crm_stats()["notes"] == notes_before + 1


def test_approval_gate(stack: Stack, user: User) -> None:
    emails_before = stack.crm_stats()["emails"]
    task = user.task("SCENARIO:approval email the renewal")
    thread, result = run_background(stack, start_one(stack, task["id"]))
    wait_for(lambda: user.get(task["id"])["status"] == "awaiting_approval")
    [approval] = user.client.get(f"{user.t}/tasks/{task['id']}/approvals").json()
    assert approval["status"] == "pending" and "Renewal" in approval["summary"]
    assert stack.crm_stats()["emails"] == emails_before
    decided = user.client.post(
        f"{user.t}/tasks/{task['id']}/approvals/{approval['id']}/decision", json={"decision": "approve"}
    )
    assert decided.status_code == 200
    thread.join(timeout=40)
    assert result.get("status") == "succeeded" and stack.crm_stats()["emails"] == emails_before + 1
    again = user.client.post(
        f"{user.t}/tasks/{task['id']}/approvals/{approval['id']}/decision", json={"decision": "reject"}
    )
    assert again.json()["code"] == "INVALID_STATE"


def test_rejected_approval_is_not_executed(stack: Stack, user: User) -> None:
    emails_before = stack.crm_stats()["emails"]
    task = user.task("SCENARIO:approval but I will say no")
    thread, result = run_background(stack, start_one(stack, task["id"]))
    wait_for(lambda: user.get(task["id"])["status"] == "awaiting_approval")
    [approval] = user.client.get(f"{user.t}/tasks/{task['id']}/approvals").json()
    user.client.post(f"{user.t}/tasks/{task['id']}/approvals/{approval['id']}/decision", json={"decision": "reject"})
    thread.join(timeout=40)
    assert result.get("status") == "succeeded" and stack.crm_stats()["emails"] == emails_before


def test_budget_stops_model_calls(stack: Stack, user: User) -> None:
    assert user.client.put(f"{user.t}/budgets", json={"per_task_token_limit": 1}).status_code == 200
    try:
        task = user.task("Build a list of our top accounts from the CRM")
        assert stack.orchestrator.run(start_one(stack, task["id"])) == "failed"
        detail = user.get(task["id"])
        assert detail["status"] == "failed" and "budget" in (detail["status_reason"] or "").lower()
    finally:
        user.client.put(f"{user.t}/budgets", json={})


def test_ticket_scope_ssrf_and_model_pinning(stack: Stack, user: User) -> None:
    ssrf = user.task("SCENARIO:ssrf fetch the admin page")
    assert stack.orchestrator.run(start_one(stack, ssrf["id"])) == "succeeded"
    finished = [
        e for e in user.client.get(f"{user.t}/tasks/{ssrf['id']}/events").json() if e["type"] == "tool.finished"
    ]
    assert finished and finished[0]["payload"]["is_error"] is True
    blocked = user.task("SCENARIO:forbidden_tool")
    started = start_one(stack, blocked["id"])
    # The model ticket cannot be used for another model.
    other = httpx.post(
        f"{stack.model_gw.url}/v1/messages",
        headers={"x-api-key": started.model_ticket},
        json={"model": "some-other-model", "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]},
    )
    assert other.status_code == 403
    # A tool ticket only works for its own attempt.
    wrong = httpx.post(
        f"{stack.tool_gw.url}/mcp/{ids.encode('attempt', ids.uuid7())}",
        headers={"Authorization": f"Bearer {started.tool_ticket}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert wrong.status_code == 401
    assert stack.orchestrator.run(started) == "succeeded"
    tool_events = [
        e for e in user.client.get(f"{user.t}/tasks/{blocked['id']}/events").json() if e["type"] == "tool.finished"
    ]
    assert tool_events[0]["payload"]["is_error"] is True


def test_revoked_connection_stops_tool_use_in_active_task(stack: Stack, user: User) -> None:
    emails_before = stack.crm_stats()["emails"]
    task = user.task("SCENARIO:approval email the renewal")
    started = start_one(stack, task["id"])
    thread, result = run_background(stack, started)
    wait_for(lambda: user.get(task["id"])["status"] == "awaiting_approval")
    [connection] = user.client.get(f"{user.t}/connections").json()
    assert user.client.delete(f"{user.t}/connections/{connection['id']}").status_code == 204
    # The attempt's tool ticket named the connection, so it stops working at once.
    blocked = httpx.post(
        f"{stack.tool_gw.url}/mcp/{started.spec['attempt_id']}",
        headers={"Authorization": f"Bearer {started.tool_ticket}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert blocked.status_code == 401
    [approval] = user.client.get(f"{user.t}/tasks/{task['id']}/approvals").json()
    user.client.post(f"{user.t}/tasks/{task['id']}/approvals/{approval['id']}/decision", json={"decision": "approve"})
    thread.join(timeout=40)
    # The approved call fails instead of sending; the model sees a tool error and finishes its answer.
    finished = [
        e["payload"]
        for e in user.client.get(f"{user.t}/tasks/{task['id']}/events").json()
        if e["type"] == "tool.finished"
    ]
    assert finished == [
        {"tool": "crm_send_email", "is_error": True, "tool_use_id": finished[0]["tool_use_id"], "deduplicated": False}
    ]
    assert result.get("status") == "succeeded" and stack.crm_stats()["emails"] == emails_before
