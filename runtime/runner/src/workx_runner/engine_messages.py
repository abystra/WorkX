"""Minimal agent loop over the Anthropic Messages API (development and tests).

Production uses the Claude Agent SDK engine (engine_sdk.py). This loop exists so the whole path (Runner →
Model Gateway → upstream, Runner → Tool Gateway → connector) can run without the SDK's CLI, against any
Messages-compatible upstream. It supports streaming text, tool use through the gateway's MCP tools, one
local tool for writing output files, approvals and authorization interrupts.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from workx_runner.mcp import McpClient
from workx_runner.protocol import Control, Emitter

LOCAL_TOOLS = [
    {
        "name": "write_output_file",
        "description": "Save a result file for the user. Use a short file name with an extension (.md, .csv, .txt).",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "content": {"type": "string"}},
            "required": ["name", "content"],
        },
    }
]
APPROVAL_TIMEOUT_SECONDS = 600


class RunStopped(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def safe_output_path(outputs_dir: str, name: str) -> Path:
    """Correctness guard (not the security boundary): files stay directly inside outputs/."""
    base = Path(outputs_dir).resolve()
    candidate = (base / Path(name).name).resolve()
    if candidate.parent != base or not candidate.name or candidate.name.startswith("."):
        raise ValueError("invalid output file name")
    return candidate


class MessagesEngine:
    def __init__(self, spec: Any, emitter: Emitter, control: Control, model_ticket: str, tool_ticket: str) -> None:
        self.spec = spec
        self.emit = emitter.emit
        self.control = control
        self.model_ticket = model_ticket
        self.http = httpx.Client(timeout=httpx.Timeout(300, connect=10))
        self.tools = McpClient(spec["tool_gateway"]["url"], tool_ticket)
        self.usage = {"input_tokens": 0, "output_tokens": 0}
        self.started = time.monotonic()

    # --------------------------------------------------------------- model
    def _check(self) -> None:
        if self.control.cancelled.is_set():
            raise RunStopped("cancelled")
        if time.monotonic() - self.started > self.spec["limits"]["wall_seconds"]:
            raise RunStopped("wall_time")

    def _stream(self, body: dict[str, Any]) -> dict[str, Any]:
        """Streams one Messages call; returns {content, stop_reason}. Emits text deltas as they arrive."""
        headers = {
            "x-api-key": self.model_ticket,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        blocks: dict[int, dict[str, Any]] = {}
        stop_reason = None
        url = self.spec["model_gateway"]["base_url"].rstrip("/") + "/v1/messages"
        with self.http.stream("POST", url, json={**body, "stream": True}, headers=headers) as response:
            if response.status_code != 200:
                detail = response.read().decode(errors="replace")[:500]
                raise RunStopped(f"model_error:{response.status_code}:{detail}")
            event = ""
            for line in response.iter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                data = json.loads(line[5:])
                kind = data.get("type", event)
                if kind == "message_start":
                    usage = data.get("message", {}).get("usage", {})
                    self.usage["input_tokens"] += int(usage.get("input_tokens", 0))
                elif kind == "content_block_start":
                    block = dict(data["content_block"])
                    if block.get("type") == "tool_use":
                        block["_json"] = ""
                    blocks[data["index"]] = block
                elif kind == "content_block_delta":
                    delta = data["delta"]
                    block = blocks[data["index"]]
                    if delta.get("type") == "text_delta":
                        block["text"] = block.get("text", "") + delta["text"]
                        self.emit("assistant.delta", {"text": delta["text"]})
                    elif delta.get("type") == "input_json_delta":
                        block["_json"] += delta.get("partial_json", "")
                elif kind == "message_delta":
                    stop_reason = data.get("delta", {}).get("stop_reason")
                    self.usage["output_tokens"] += int(data.get("usage", {}).get("output_tokens", 0))
                elif kind == "error":
                    raise RunStopped(f"model_error:{data.get('error', {}).get('type', 'error')}")
                self._check()
        content = []
        for index in sorted(blocks):
            block = blocks[index]
            if block.get("type") == "tool_use":
                block["input"] = json.loads(block.pop("_json") or "{}")
            content.append(block)
        return {"content": content, "stop_reason": stop_reason}

    # --------------------------------------------------------------- tools
    def _local_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        path = safe_output_path(self.spec["outputs_dir"], str(arguments.get("name", "")))
        data = str(arguments.get("content", "")).encode()
        limit = int(self.spec["limits"].get("max_output_bytes") or 100 * 1024 * 1024)
        if len(data) > limit:
            return {"isError": True, "content": [{"type": "text", "text": "File too large."}]}
        path.write_bytes(data)
        self.emit("artifact.staged", {"name": path.name, "size": len(data)})
        return {"content": [{"type": "text", "text": f"Saved {path.name}"}]}

    def _gateway_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self.tools.call_tool(name, arguments)
        structured = result.get("structuredContent") or {}
        if result.get("isError") and structured.get("code") == "APPROVAL_REQUIRED":
            approval_id = structured["approval_id"]
            self.emit(
                "approval.requested",
                {"approval_id": approval_id, "tool": name, "summary": structured.get("summary", "")},
            )
            decision = self.control.wait_approval(approval_id, APPROVAL_TIMEOUT_SECONDS)
            if decision is None:
                raise RunStopped("cancelled" if self.control.cancelled.is_set() else "approval_timeout")
            if decision != "approved":
                return {"isError": True, "content": [{"type": "text", "text": "The user rejected this action."}]}
            result = self.tools.call_tool(name, {**arguments, "_approval_id": approval_id})
            structured = result.get("structuredContent") or {}
        if result.get("isError") and structured.get("code") == "NEEDS_AUTH":
            self.emit(
                "auth.required", {"tool": name, "authorization_request_id": structured.get("authorization_request_id")}
            )
            raise RunStopped("needs_auth")
        return result

    # --------------------------------------------------------------- loop
    def run(self) -> str:
        self.emit("run.started", {"engine": "messages", "model": self.spec["model"]})
        try:
            self.tools.initialize()
            gateway_tools = self.tools.list_tools()
            tools = LOCAL_TOOLS + [
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": t.get("inputSchema", {"type": "object"}),
                }
                for t in gateway_tools
            ]
            messages: list[dict[str, Any]] = [
                {"role": m["role"], "content": m["content"]} for m in self.spec["input"].get("history", [])
            ]
            messages.append({"role": "user", "content": self.spec["input"]["text"]})
            for _turn in range(self.spec["limits"]["max_turns"]):
                self._check()
                reply = self._stream(
                    {
                        "model": self.spec["model"],
                        "max_tokens": 4096,
                        "system": self.spec.get("system_prompt", ""),
                        "messages": messages,
                        "tools": tools,
                    }
                )
                messages.append({"role": "assistant", "content": reply["content"]})
                text = "".join(b.get("text", "") for b in reply["content"] if b.get("type") == "text")
                if text:
                    self.emit("assistant.message", {"text": text})
                if reply["stop_reason"] != "tool_use":
                    return "completed"
                results = []
                for block in reply["content"]:
                    if block.get("type") != "tool_use":
                        continue
                    self._check()
                    self.emit("tool.started", {"tool": block["name"], "tool_use_id": block["id"]})
                    try:
                        if block["name"] in {t["name"] for t in LOCAL_TOOLS}:
                            outcome = self._local_tool(block["name"], block["input"])
                        else:
                            outcome = self._gateway_tool(block["name"], block["input"])
                    except RunStopped:
                        raise
                    except Exception as exc:
                        outcome = {
                            "isError": True,
                            "content": [{"type": "text", "text": f"Tool failed: {type(exc).__name__}"}],
                        }
                    text_out = "".join(c.get("text", "") for c in outcome.get("content", []) if c.get("type") == "text")
                    self.emit(
                        "tool.finished",
                        {
                            "tool": block["name"],
                            "tool_use_id": block["id"],
                            "is_error": bool(outcome.get("isError")),
                            "deduplicated": bool((outcome.get("structuredContent") or {}).get("deduplicated")),
                        },
                    )
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block["id"],
                            "content": text_out[:50_000],
                            "is_error": bool(outcome.get("isError")),
                        }
                    )
                messages.append({"role": "user", "content": results})
            return "max_turns"
        except RunStopped as stop:
            if stop.reason in {"cancelled", "wall_time", "needs_auth", "approval_timeout"}:
                return stop.reason
            self.emit("run.error", {"detail": stop.reason[:500]})
            return "error"
