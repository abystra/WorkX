"""Claude Agent SDK engine (production). Configuration follows Part 4 §6:

* no setting sources (no user/project settings, no .mcp.json, no CLAUDE.md discovery)
* ``permission_mode="dontAsk"``: anything not pre-approved is denied, never prompts
* network tools removed; the only MCP server is the WorkX Tool Gateway, authenticated with the tool ticket
* the model ticket is passed as ``ANTHROPIC_API_KEY`` and ``ANTHROPIC_BASE_URL`` points at the Model Gateway,
  so no real Anthropic key ever enters the sandbox
* a PreToolUse hook keeps Edit/Write inside the workspace and outputs (a correctness guard; the sandbox is the
  security boundary)

Requires ``pip install workx-runner[sdk]`` (bundles the Claude Code CLI). Option names are pinned to the SDK
version in the E2B template (runtime/e2b-template).
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any

from workx_runner.protocol import Control, Emitter

ALLOWED_TOOLS = ["Read", "Glob", "Grep", "Edit", "Write", "Bash", "Skill", "mcp__workx__*"]
DISALLOWED_TOOLS = ["WebFetch", "WebSearch"]
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def inside(path: str, roots: list[str]) -> bool:
    try:
        resolved = Path(path).resolve()
    except OSError:
        return False
    return any(resolved == Path(r).resolve() or Path(r).resolve() in resolved.parents for r in roots)


class SdkEngine:
    def __init__(self, spec: Any, emitter: Emitter, control: Control, model_ticket: str, tool_ticket: str) -> None:
        self.spec = spec
        self.emit = emitter.emit
        self.control = control
        self.model_ticket = model_ticket
        self.tool_ticket = tool_ticket
        self.started = time.monotonic()

    def options(self) -> Any:
        from claude_agent_sdk import ClaudeAgentOptions, HookContext, HookInput, HookJSONOutput, HookMatcher

        roots = [self.spec["cwd"], self.spec["outputs_dir"]]

        async def path_guard(input_data: HookInput, tool_use_id: str | None, context: HookContext) -> HookJSONOutput:
            data: dict[str, Any] = dict(input_data)
            tool = data.get("tool_name", "")
            target = (data.get("tool_input") or {}).get("file_path")
            if tool in WRITE_TOOLS and target and not inside(str(target), roots):
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": "Write only inside the workspace or outputs folder.",
                    }
                }
            return {}

        config_dir = os.path.join(os.environ.get("HOME", "/home/agent"), ".claude-ses")
        return ClaudeAgentOptions(
            cwd=self.spec["cwd"],
            setting_sources=[],
            plugins=[{"type": "local", "path": p} for p in self.spec.get("plugins", [])],
            skills=self.spec.get("skills") or None,
            system_prompt=self.spec.get("system_prompt", ""),
            model=self.spec["model"],
            max_turns=self.spec["limits"]["max_turns"],
            permission_mode="dontAsk",
            allowed_tools=ALLOWED_TOOLS,
            disallowed_tools=DISALLOWED_TOOLS,
            include_partial_messages=True,
            hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[path_guard])]},
            mcp_servers={
                "workx": {
                    "type": "http",
                    "url": self.spec["tool_gateway"]["url"],
                    "headers": {"Authorization": f"Bearer {self.tool_ticket}"},
                }
            },
            env={
                "ANTHROPIC_BASE_URL": self.spec["model_gateway"]["base_url"],
                "ANTHROPIC_API_KEY": self.model_ticket,
                # Background calls must use the pinned model too: the Model Gateway refuses any other.
                "ANTHROPIC_SMALL_FAST_MODEL": self.spec["model"],
                "CLAUDE_CONFIG_DIR": config_dir,
                "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                "DISABLE_TELEMETRY": "1",
            },
        )

    async def _run(self) -> str:
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeSDKClient,
            ResultMessage,
            TextBlock,
            ToolResultBlock,
            ToolUseBlock,
            UserMessage,
        )

        self.emit("run.started", {"engine": "claude-agent-sdk", "model": self.spec["model"]})
        reason = "completed"
        async with ClaudeSDKClient(options=self.options()) as client:
            await client.query(self.spec["input"]["text"])
            async for message in client.receive_response():
                if self.control.cancelled.is_set():
                    await client.interrupt()
                    reason = "cancelled"
                if time.monotonic() - self.started > self.spec["limits"]["wall_seconds"]:
                    await client.interrupt()
                    reason = "wall_time"
                if isinstance(message, AssistantMessage):
                    text = "".join(b.text for b in message.content if isinstance(b, TextBlock))
                    if text:
                        self.emit("assistant.message", {"text": text})
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            self.emit("tool.started", {"tool": block.name, "tool_use_id": block.id})
                elif isinstance(message, UserMessage) and isinstance(message.content, list):
                    for block in message.content:
                        if isinstance(block, ToolResultBlock):
                            self.emit(
                                "tool.finished", {"tool_use_id": block.tool_use_id, "is_error": bool(block.is_error)}
                            )
                elif isinstance(message, ResultMessage):
                    if message.subtype == "error_max_turns":
                        reason = "max_turns"
                    elif message.is_error and reason == "completed":
                        reason = "error"
                        self.emit("run.error", {"detail": str(message.subtype)})
                    self.emit("run.usage", {"usage": message.usage or {}, "num_turns": message.num_turns})
        self._stage_outputs()
        return reason

    def _stage_outputs(self) -> None:
        outputs = Path(self.spec["outputs_dir"])
        for path in sorted(outputs.glob("*")):
            if path.is_file() and not path.is_symlink():
                self.emit("artifact.staged", {"name": path.name, "size": path.stat().st_size})

    def run(self) -> str:
        return asyncio.run(self._run())
