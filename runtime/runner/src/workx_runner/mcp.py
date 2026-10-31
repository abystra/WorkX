"""Minimal MCP client over Streamable HTTP (JSON responses) for the WorkX Tool Gateway."""

from __future__ import annotations

import itertools
from typing import Any

import httpx

MCP_PROTOCOL_VERSION = "2025-06-18"


class McpError(Exception):
    pass


class McpClient:
    def __init__(self, url: str, ticket: str, *, client: httpx.Client | None = None) -> None:
        self.url = url
        self._http = client or httpx.Client(timeout=120)
        self._headers = {
            "Authorization": f"Bearer {ticket}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        self._ids = itertools.count(1)
        self._session: str | None = None

    def _rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        headers = dict(self._headers)
        if self._session:
            headers["Mcp-Session-Id"] = self._session
        body = {"jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": params or {}}
        response = self._http.post(self.url, json=body, headers=headers)
        if response.status_code >= 400:
            raise McpError(f"gateway returned {response.status_code}")
        self._session = response.headers.get("Mcp-Session-Id", self._session)
        message = response.json()
        if "error" in message:
            raise McpError(str(message["error"].get("message", "MCP error")))
        return message.get("result")

    def initialize(self) -> None:
        self._rpc(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "workx-runner", "version": "1"},
            },
        )

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._rpc("tools/list")
        return list(result.get("tools", []))

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = self._rpc("tools/call", {"name": name, "arguments": arguments})
        return result
