"""The production engine: Claude Agent SDK + its bundled Claude Code CLI, run as a real Runner subprocess
against the real Model Gateway and Tool Gateway. Only the model is a protocol-level fake."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from tests.runtime.test_vertical_slice import Stack, User, start_one

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("claude_agent_sdk") is None, reason="workx-runner[sdk] not installed"
)


def _bundled_cli() -> bool:
    spec = importlib.util.find_spec("claude_agent_sdk")
    return bool(spec and spec.origin and (Path(spec.origin).parent / "_bundled" / "claude").exists())


@pytest.mark.skipif(not _bundled_cli(), reason="Claude Code CLI not bundled with the SDK")
def test_sdk_engine_runs_through_the_gateways(stack: Stack, user: User) -> None:
    stack.orchestrator.settings.runner_engine = "claude-agent-sdk"
    try:
        lists_before = stack.crm_stats()["calls"]["list"]
        task = user.task("SCENARIO:sdk which accounts matter most?")
        status = stack.orchestrator.run(start_one(stack, task["id"]))
        events = user.client.get(f"{user.t}/tasks/{task['id']}/events").json()
        types = [e["type"] for e in events]
        assert status == "succeeded", (status, [(e["type"], e["payload"]) for e in events][-6:])
        started = next(e for e in events if e["type"] == "run.started")
        assert started["payload"]["engine"] == "claude-agent-sdk"
        assert "tool.started" in types and "tool.finished" in types
        assert stack.crm_stats()["calls"]["list"] == lists_before + 1
        answer = [m["content"] for m in user.get(task["id"])["messages"] if m["role"] == "assistant"]
        assert any("Northwind" in a for a in answer)
        # Every model call reached the upstream with the real key and the pinned model only.
        seen = stack.upstream.server.config.app.state.seen
        assert seen and all(s["model"] == "test-model-auto" for s in seen)
    finally:
        stack.orchestrator.settings.runner_engine = "messages"


@pytest.mark.skipif(not _bundled_cli(), reason="Claude Code CLI not bundled with the SDK")
def test_sdk_engine_produces_a_downloadable_xlsx(stack: Stack, user: User) -> None:
    """Part 14 §2 acceptance: the user downloads a valid XLSX produced in outputs/ by the agent."""
    import io

    from openpyxl import load_workbook

    stack.orchestrator.settings.runner_engine = "claude-agent-sdk"
    try:
        task = user.task("SCENARIO:xlsx build the spreadsheet")
        status = stack.orchestrator.run(start_one(stack, task["id"]))
        events = user.client.get(f"{user.t}/tasks/{task['id']}/events").json()
        assert status == "succeeded", [(e["type"], e["payload"]) for e in events][-6:]
        available = [e["payload"] for e in events if e["type"] == "artifact.available"]
        assert available and available[0]["name"] == "top-accounts.xlsx" and available[0]["kind"] == "sheet"
        download = user.client.get(f"{user.t}/files/{available[0]['file_id']}/content")
        assert download.status_code == 200
        sheet = load_workbook(io.BytesIO(download.content)).active
        assert sheet["A2"].value == "Northwind Traders" and sheet["B2"].value == 4200000
    finally:
        stack.orchestrator.settings.runner_engine = "messages"
