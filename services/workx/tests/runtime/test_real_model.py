"""Opt-in: the vertical slice against a real model service instead of the protocol-level fake.

Runs only when these are set (never in CI by default; the key stays in the environment):

    WORKX_REAL_MODEL_BASE_URL   Anthropic Messages API base URL (https://api.anthropic.com, or a compatible service)
    WORKX_REAL_MODEL_API_KEY    the upstream key; only the Model Gateway in this test receives it
    WORKX_REAL_MODEL            the model ID every tier maps to for this run

Both engines run: ``messages`` and ``claude-agent-sdk`` (bundled Claude Code CLI). The model decides on its own
to call the CRM tool; the assertions check the platform path, not the wording.
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.runtime.test_vertical_slice import CRM_KEY, CapturingProvider, Stack, User, start_one
from tests.support.servers import Served
from workx.core import ids
from workx.core.db import Database
from workx.core.settings import Environment, ModelGatewaySettings, OrchestratorSettings
from workx.domains.runtime.orchestrator import Orchestrator
from workx.trusted.model_gateway.app import create_model_gateway_app

BASE_URL = os.environ.get("WORKX_REAL_MODEL_BASE_URL", "")
API_KEY = os.environ.get("WORKX_REAL_MODEL_API_KEY", "")
MODEL = os.environ.get("WORKX_REAL_MODEL", "")

pytestmark = pytest.mark.skipif(
    not (BASE_URL and API_KEY and MODEL), reason="set WORKX_REAL_MODEL_BASE_URL, _API_KEY and WORKX_REAL_MODEL"
)

PROMPT = (
    "Use the CRM tool to list our accounts, then tell me which account has the highest annual revenue. "
    "Answer in one short paragraph and include the account name."
)


@pytest.fixture(scope="module")
def real(stack: Stack, db: Database, objects_dir: Path) -> Iterator[tuple[Orchestrator, Served]]:
    base = {
        "environment": Environment.TEST,
        "database_url": stack.orchestrator.settings.database_url,
        "object_store_url": f"file:{objects_dir}",
    }
    gateway = Served(
        create_model_gateway_app(
            ModelGatewaySettings(**base, anthropic_base_url=BASE_URL, anthropic_api_key=API_KEY), db
        )
    )  # type: ignore[arg-type]
    settings = OrchestratorSettings(
        **base,
        model_tiers={tier: MODEL for tier in ("auto", "opus", "sonnet", "haiku")},
        runner_engine="messages",
        model_gateway_url=gateway.url,
        tool_gateway_url=stack.orchestrator.settings.tool_gateway_url,  # type: ignore[arg-type]
        heartbeat_seconds=1,
        lease_seconds=60,
        wall_seconds=240,
        max_concurrent_attempts_per_tenant=5,
    )
    captured: list[dict[str, str]] = []
    yield Orchestrator(db, settings, CapturingProvider(captured), "orch-real"), gateway
    gateway.stop()


ENGINES = ["messages"]
_sdk = importlib.util.find_spec("claude_agent_sdk")
if _sdk and _sdk.origin and (Path(_sdk.origin).parent / "_bundled" / "claude").exists():
    ENGINES.append("claude-agent-sdk")


@pytest.mark.timeout(300)
@pytest.mark.parametrize("engine", ENGINES)
def test_real_model_runs_the_slice(
    engine: str, real: tuple[Orchestrator, Served], stack: Stack, user: User, owner_db: Database
) -> None:
    orchestrator, _ = real
    orchestrator.settings.runner_engine = engine
    lists_before = stack.crm_stats()["calls"]["list"]
    task = user.task(PROMPT)
    started = start_one(stack, task["id"], orchestrator)
    status = orchestrator.run(started)
    events = user.client.get(f"{user.t}/tasks/{task['id']}/events").json()
    summary = [(e["type"], e["payload"]) for e in events][-8:]
    assert status == "succeeded", summary
    assert next(e for e in events if e["type"] == "run.started")["payload"]["engine"] == engine
    tools = [e["payload"] for e in events if e["type"] == "tool.finished"]
    assert any(t["tool"] == "crm_list_accounts" and not t["is_error"] for t in tools), summary
    assert stack.crm_stats()["calls"]["list"] > lists_before
    answer = " ".join(m["content"] for m in user.get(task["id"])["messages"] if m["role"] == "assistant")
    assert "Northwind" in answer, answer[:500]
    # The Runner only ever held tickets; the upstream key and the CRM key stayed in the trusted services.
    env = orchestrator.provider.captured[-1]  # type: ignore[attr-defined]
    assert set(env) == {"WORKX_MODEL_TICKET", "WORKX_TOOL_TICKET"}
    assert API_KEY not in str(env) and CRM_KEY not in str(env)
    with owner_db.transaction() as session:
        tokens = session.execute(
            text("SELECT coalesce(sum(quantity), 0) FROM usage_events WHERE kind = 'model_tokens' AND task_id = :t"),
            {"t": ids.decode("task", task["id"])},
        ).scalar_one()
    assert tokens > 0
    print(f"\n[{engine}] {MODEL}: {len(tools)} tool call(s), {tokens} tokens metered. Answer: {answer[:300]}")
