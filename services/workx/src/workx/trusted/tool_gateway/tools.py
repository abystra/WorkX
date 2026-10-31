"""Tools served to agents through the Tool Gateway: class 0 platform tools, class A (API key) connector tools,
class B (user OAuth) tools, including tools proxied to remote MCP servers.

Each tool declares its side-effect class and the fields that identify a logical operation, so a retried
Attempt cannot repeat a write (Part 4 §10.4). Tools that need a human decision set ``approval``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from workx.core.settings import ToolGatewaySettings
from workx.trusted.tool_gateway.ssrf import BlockedUrl, check_url


class ToolFailure(Exception):
    """Reported to the model as a tool error (never raised to the client)."""


class NeedsAuth(ToolFailure):
    """The provider rejected the user's token: the connection needs a new authorization."""


@dataclass(frozen=True)
class Access:
    """What a connector tool receives: the bound connection's credential and its installation settings."""

    token: str
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    effect: str  # read | write_idempotent | write_non_idempotent
    key_fields: tuple[str, ...] = ()
    approval: bool = False
    summary: Callable[[dict[str, Any]], str] = field(default=lambda args: "")
    # (settings, client, args, access): ``access`` is None for class 0 tools.
    run: Callable[[ToolGatewaySettings, httpx.Client, dict[str, Any], Access | None], dict[str, Any]] = field(
        default=lambda s, c, a, k: {}
    )


def _crm_headers(access: Access | None) -> dict[str, str]:
    if access is None:
        raise ToolFailure("No credential for this connection.")
    return {"X-Api-Key": access.token}


def _crm_list(
    settings: ToolGatewaySettings, http: httpx.Client, args: dict[str, Any], access: Access | None
) -> dict[str, Any]:
    response = http.get(
        f"{settings.crm_base_url}/accounts",
        headers=_crm_headers(access),
        params={"limit": int(args.get("limit", 20))},
    )
    if response.status_code != 200:
        raise ToolFailure(f"CRM returned {response.status_code}")
    return {"accounts": response.json()}


def _crm_note(
    settings: ToolGatewaySettings, http: httpx.Client, args: dict[str, Any], access: Access | None
) -> dict[str, Any]:
    response = http.post(
        f"{settings.crm_base_url}/notes",
        headers=_crm_headers(access),
        json={"account_id": args["account_id"], "text": args["text"]},
    )
    if response.status_code not in (200, 201):
        raise ToolFailure(f"CRM returned {response.status_code}")
    return {"note": response.json()}


def _crm_email(
    settings: ToolGatewaySettings, http: httpx.Client, args: dict[str, Any], access: Access | None
) -> dict[str, Any]:
    response = http.post(
        f"{settings.crm_base_url}/emails",
        headers=_crm_headers(access),
        json={"account_id": args["account_id"], "subject": args["subject"], "body": args["body"]},
    )
    if response.status_code not in (200, 201):
        raise ToolFailure(f"CRM returned {response.status_code}")
    return {"email": response.json()}


def _web_fetch(
    settings: ToolGatewaySettings, http: httpx.Client, args: dict[str, Any], access: Access | None
) -> dict[str, Any]:
    url = str(args.get("url", ""))
    for _hop in range(4):
        try:
            check_url(url)
        except BlockedUrl as exc:
            raise ToolFailure(str(exc)) from exc
        with http.stream("GET", url, follow_redirects=False, timeout=20) as response:
            if response.is_redirect and response.headers.get("location"):
                url = str(httpx.URL(url).join(response.headers["location"]))
                continue
            kind = response.headers.get("content-type", "")
            if not kind.startswith(("text/", "application/json", "application/xml")):
                raise ToolFailure("Only text content can be fetched.")
            body = b""
            for chunk in response.iter_bytes():
                body += chunk
                if len(body) > settings.web_fetch_max_bytes:
                    raise ToolFailure("The page is too large.")
            return {
                "url": url,
                "status": response.status_code,
                "content_type": kind,
                "text": body.decode(errors="replace"),
            }
    raise ToolFailure("Too many redirects.")


def _bearer(access: Access | None) -> dict[str, str]:
    if access is None:
        raise ToolFailure("No credential for this connection.")
    return {"Authorization": f"Bearer {access.token}"}


def _remote_mcp(remote_name: str) -> Callable[..., dict[str, Any]]:
    """Calls a tool on the connection's remote MCP server (Streamable HTTP, JSON responses) as the user."""

    def run(
        settings: ToolGatewaySettings, http: httpx.Client, args: dict[str, Any], access: Access | None
    ) -> dict[str, Any]:
        url = str((access.config if access else {}).get("base_url") or "")
        if not url:
            raise ToolFailure("The connector has no server URL.")
        headers = {**_bearer(access), "Accept": "application/json, text/event-stream"}

        def rpc(message: dict[str, Any], session_id: str | None) -> httpx.Response:
            extra = {"Mcp-Session-Id": session_id} if session_id else {}
            response = http.post(url, json={"jsonrpc": "2.0", **message}, headers={**headers, **extra})
            if response.status_code == 401:
                raise NeedsAuth("The server rejected the authorization.")
            return response

        init = rpc(
            {
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "workx-tool-gateway", "version": "1"},
                },
            },
            None,
        )
        session_id = init.headers.get("mcp-session-id")
        rpc({"method": "notifications/initialized"}, session_id)
        response = rpc(
            {"id": 2, "method": "tools/call", "params": {"name": remote_name, "arguments": args}}, session_id
        )
        if response.status_code != 200:
            raise ToolFailure(f"The server returned {response.status_code}")
        message = response.json()
        if "error" in message:
            raise ToolFailure(str(message["error"].get("message", "error")))
        result = message.get("result") or {}
        if result.get("isError"):
            raise ToolFailure(" ".join(c.get("text", "") for c in result.get("content", [])) or "Tool error")
        return dict(result.get("structuredContent") or {"content": result.get("content", [])})

    return run


FEISHU_TOKEN_INVALID = {99991663, 99991668, 99991677, 20005}  # invalid/expired user_access_token


def _feishu(method: str, path: str, body: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    def run(
        settings: ToolGatewaySettings, http: httpx.Client, args: dict[str, Any], access: Access | None
    ) -> dict[str, Any]:
        response = http.request(method, f"{settings.feishu_base_url}{path}", headers=_bearer(access), json=body(args))
        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        code = data.get("code")
        if code in FEISHU_TOKEN_INVALID or response.status_code == 401:
            raise NeedsAuth("Feishu rejected the authorization.")
        if response.status_code >= 400 or code not in (0, None):
            raise ToolFailure(f"Feishu returned {code or response.status_code}: {data.get('msg', '')}"[:300])
        return dict(data.get("data") or {})

    return run


REGISTRY: dict[str, Tool] = {
    tool.name: tool
    for tool in (
        Tool(
            "crm_list_accounts",
            "List accounts in the CRM with their annual revenue.",
            {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}}},
            "read",
            run=_crm_list,
        ),
        Tool(
            "crm_create_note",
            "Add a note to a CRM account.",
            {
                "type": "object",
                "properties": {"account_id": {"type": "string"}, "text": {"type": "string"}},
                "required": ["account_id", "text"],
            },
            "write_non_idempotent",
            key_fields=("account_id", "text"),
            run=_crm_note,
        ),
        Tool(
            "crm_send_email",
            "Send an email to a CRM account's contact. Requires the user's approval.",
            {
                "type": "object",
                "properties": {
                    "account_id": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["account_id", "subject", "body"],
            },
            "write_non_idempotent",
            key_fields=("account_id", "subject", "body"),
            approval=True,
            summary=lambda a: f'Send email "{a.get("subject", "")}" to account {a.get("account_id", "")}',
            run=_crm_email,
        ),
        Tool(
            "notes_list",
            "List the user's notes in their Notes service.",
            {"type": "object", "properties": {"query": {"type": "string"}}},
            "read",
            run=_remote_mcp("list_notes"),
        ),
        Tool(
            "notes_create",
            "Create a note in the user's Notes service.",
            {
                "type": "object",
                "properties": {"title": {"type": "string"}, "body": {"type": "string"}},
                "required": ["title", "body"],
            },
            "write_non_idempotent",
            key_fields=("title", "body"),
            run=_remote_mcp("create_note"),
        ),
        Tool(
            "feishu_docs_search",
            "Search the user's Feishu documents by keyword.",
            {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            "read",
            run=_feishu(
                "POST",
                "/open-apis/suite/docs-api/search/object",
                lambda a: {"search_key": a["query"], "count": 20, "offset": 0, "docs_types": ["docx", "doc", "sheet"]},
            ),
        ),
        Tool(
            "feishu_docs_create",
            "Create a Feishu document owned by the user.",
            {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]},
            "write_non_idempotent",
            key_fields=("title",),
            run=_feishu("POST", "/open-apis/docx/v1/documents", lambda a: {"title": a["title"]}),
        ),
        Tool(
            "knowledge_search",
            "Search the documents attached to you (company knowledge). Returns quoted passages with citation_id, "
            "source, section and location. Cite passages you rely on as [[cite:<citation_id>]].",
            {
                "type": "object",
                "properties": {"query": {"type": "string"}, "k": {"type": "integer", "minimum": 1, "maximum": 12}},
                "required": ["query"],
            },
            "read",
            # Served by the gateway itself (needs the Attempt's lease); see app.knowledge_search.
        ),
        Tool(
            "web_fetch",
            "Fetch a public web page as text.",
            {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
            "read",
            run=_web_fetch,
        ),
    )
}
