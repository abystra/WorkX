"""Tools served to agents through the Tool Gateway (class 0 platform tools and class A connector tools).

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


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    effect: str  # read | write_idempotent | write_non_idempotent
    key_fields: tuple[str, ...] = ()
    approval: bool = False
    summary: Callable[[dict[str, Any]], str] = field(default=lambda args: "")
    run: Callable[[ToolGatewaySettings, httpx.Client, dict[str, Any]], dict[str, Any]] = field(
        default=lambda s, c, a: {}
    )


def _crm_headers(settings: ToolGatewaySettings) -> dict[str, str]:
    return {"X-Api-Key": settings.crm_api_key.get_secret_value()}


def _crm_list(settings: ToolGatewaySettings, http: httpx.Client, args: dict[str, Any]) -> dict[str, Any]:
    response = http.get(
        f"{settings.crm_base_url}/accounts",
        headers=_crm_headers(settings),
        params={"limit": int(args.get("limit", 20))},
    )
    if response.status_code != 200:
        raise ToolFailure(f"CRM returned {response.status_code}")
    return {"accounts": response.json()}


def _crm_note(settings: ToolGatewaySettings, http: httpx.Client, args: dict[str, Any]) -> dict[str, Any]:
    response = http.post(
        f"{settings.crm_base_url}/notes",
        headers=_crm_headers(settings),
        json={"account_id": args["account_id"], "text": args["text"]},
    )
    if response.status_code not in (200, 201):
        raise ToolFailure(f"CRM returned {response.status_code}")
    return {"note": response.json()}


def _crm_email(settings: ToolGatewaySettings, http: httpx.Client, args: dict[str, Any]) -> dict[str, Any]:
    response = http.post(
        f"{settings.crm_base_url}/emails",
        headers=_crm_headers(settings),
        json={"account_id": args["account_id"], "subject": args["subject"], "body": args["body"]},
    )
    if response.status_code not in (200, 201):
        raise ToolFailure(f"CRM returned {response.status_code}")
    return {"email": response.json()}


def _web_fetch(settings: ToolGatewaySettings, http: httpx.Client, args: dict[str, Any]) -> dict[str, Any]:
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
            "web_fetch",
            "Fetch a public web page as text.",
            {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
            "read",
            run=_web_fetch,
        ),
    )
}
