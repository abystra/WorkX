"""Tool Gateway (trusted): the only MCP server an agent can reach (Part 4 §2, §10.4; Part 6).

``POST /mcp/{attempt_id}`` speaks MCP over Streamable HTTP (JSON responses). Every call needs the
Attempt's tool ticket; the ticket's scopes list the tools this Attempt may use.

Writes go through the operation ledger: ``operation_key = H(task, tool, key fields)`` is unique per Task,
so a later Attempt gets the recorded result back (``deduplicated``) instead of repeating the side effect,
and an operation whose outcome is unknown blocks until reconciled. Approval-gated tools create an approval
bound to a digest of the exact arguments; only that decision lets the same call through.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import timedelta
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from starlette.concurrency import run_in_threadpool

from workx.core import ids
from workx.core.db import Database
from workx.core.errors import ApiError
from workx.core.orm import utcnow
from workx.core.redaction import redact
from workx.core.settings import ToolGatewaySettings
from workx.domains.runtime.models import Approval, ToolOperation
from workx.domains.usage import service as usage
from workx.trusted.broker import tickets
from workx.trusted.tool_gateway.tools import REGISTRY, Tool, ToolFailure

PROTOCOL_VERSION = "2025-06-18"


def canonical(args: dict[str, Any]) -> str:
    return json.dumps({k: v for k, v in args.items() if not k.startswith("_")}, sort_keys=True, ensure_ascii=False)


def args_digest(args: dict[str, Any]) -> str:
    return hashlib.sha256(canonical(args).encode()).hexdigest()


def operation_key(task_id: Any, tool: Tool, args: dict[str, Any]) -> str:
    fields = (
        {k: args.get(k) for k in tool.key_fields}
        if tool.key_fields
        else {k: v for k, v in args.items() if not k.startswith("_")}
    )
    return hashlib.sha256(
        f"{task_id}|{tool.name}|{json.dumps(fields, sort_keys=True, ensure_ascii=False)}".encode()
    ).hexdigest()


def _text_result(data: Any, *, error: bool = False, structured: dict[str, Any] | None = None) -> dict[str, Any]:
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    result: dict[str, Any] = {"content": [{"type": "text", "text": text}], "isError": error}
    if structured is not None:
        result["structuredContent"] = structured
    return result


def create_tool_gateway_app(
    settings: ToolGatewaySettings | None = None, db: Database | None = None, *, http: httpx.Client | None = None
) -> FastAPI:
    settings = settings or ToolGatewaySettings()
    db = db or Database.connect(settings.database_url)
    client = http or httpx.Client(timeout=30)
    app = FastAPI(title="WorkX Tool Gateway", docs_url=None, redoc_url=None, openapi_url=None)

    def lease_for(request: Request, attempt_external: str) -> tickets.Lease:
        auth = request.headers.get("authorization", "")
        token = auth[7:] if auth.lower().startswith("bearer ") else None
        with db.transaction() as session:
            lease = tickets.verify(session, token, "tool")
        if ids.decode("attempt", attempt_external) != lease.attempt_id:
            raise ApiError(401, "TICKET_INVALID", "The ticket does not belong to this attempt.")
        return lease

    def allowed(lease: tickets.Lease) -> list[Tool]:
        names = lease.scopes.get("tools") or []
        return [REGISTRY[n] for n in names if n in REGISTRY]

    def approval_gate(lease: tickets.Lease, tool: Tool, args: dict[str, Any]) -> dict[str, Any] | None:
        """None when the call may proceed; otherwise the MCP result to return."""
        digest = args_digest(args)
        approval_ref = args.get("_approval_id")
        with db.transaction(tenant_id=lease.tenant_id) as session:
            if approval_ref:
                approval = session.get(Approval, ids.decode("approval", str(approval_ref)))
                ok = (
                    approval is not None
                    and approval.task_id == lease.task_id
                    and approval.tool == tool.name
                    and approval.args_digest == digest
                    and approval.status == "approved"
                )
                if ok:
                    return None
                return _text_result("This action was not approved.", error=True, structured={"code": "APPROVAL_DENIED"})
            approval = Approval(
                id=ids.uuid7(),
                tenant_id=lease.tenant_id,
                task_id=lease.task_id,
                attempt_id=lease.attempt_id,
                tool=tool.name,
                args_digest=digest,
                summary=tool.summary(args)[:500],
                expires_at=utcnow() + timedelta(minutes=settings.approval_ttl_minutes),
                created_at=utcnow(),
            )
            session.add(approval)
        return _text_result(
            "Waiting for the user's approval.",
            error=True,
            structured={
                "code": "APPROVAL_REQUIRED",
                "approval_id": ids.encode("approval", approval.id),
                "summary": approval.summary,
            },
        )

    def execute(lease: tickets.Lease, tool: Tool, args: dict[str, Any]) -> dict[str, Any]:
        clean = {k: v for k, v in args.items() if not k.startswith("_")}
        key = operation_key(lease.task_id, tool, clean)
        if tool.effect != "read":
            with db.transaction(tenant_id=lease.tenant_id) as session:
                inserted = session.execute(
                    insert(ToolOperation)
                    .values(
                        id=ids.uuid7(),
                        tenant_id=lease.tenant_id,
                        task_id=lease.task_id,
                        attempt_id=lease.attempt_id,
                        tool=tool.name,
                        effect=tool.effect,
                        operation_key=key,
                        status="started",
                    )
                    .on_conflict_do_nothing(index_elements=["task_id", "operation_key"])
                    .returning(ToolOperation.id)
                ).scalar()
                if inserted is None:
                    existing = session.execute(
                        select(ToolOperation).where(
                            ToolOperation.task_id == lease.task_id, ToolOperation.operation_key == key
                        )
                    ).scalar_one()
                    if existing.status == "succeeded":
                        return _text_result(
                            existing.result or {}, structured={"deduplicated": True, **(existing.result or {})}
                        )
                    if existing.status == "failed":
                        existing.status = "started"
                        existing.attempt_id = lease.attempt_id
                        existing.error = None
                    else:
                        return _text_result(
                            "A previous attempt may already have done this; it needs to be checked first.",
                            error=True,
                            structured={"code": "OPERATION_IN_DOUBT"},
                        )
        try:
            outcome = redact(tool.run(settings, client, clean))
            text = json.dumps(outcome, ensure_ascii=False)
            if len(text) > settings.max_result_chars:
                outcome = {"truncated": True, "text": text[: settings.max_result_chars]}
            status, error = "succeeded", None
        except ToolFailure as exc:
            outcome, status, error = {"error": str(exc)}, "failed", str(exc)
        except httpx.TimeoutException:
            outcome, status, error = {"error": "The service did not answer in time."}, "unknown", "timeout"
        except httpx.HTTPError:
            outcome, status, error = {"error": "The service could not be reached."}, "failed", "unreachable"
        with db.transaction(tenant_id=lease.tenant_id) as session:
            if tool.effect != "read":
                op = session.execute(
                    select(ToolOperation).where(
                        ToolOperation.task_id == lease.task_id, ToolOperation.operation_key == key
                    )
                ).scalar_one()
                op.status, op.result, op.error = status, outcome if status == "succeeded" else None, error
            usage.record(
                session,
                tenant_id=lease.tenant_id,
                kind="tool_call",
                quantity=1,
                unit="call",
                source_event_id=f"tool:{secrets.token_hex(12)}",
                task_id=lease.task_id,
                attempt_id=lease.attempt_id,
                data={"tool": tool.name, "status": status},
            )
        return _text_result(outcome, error=status != "succeeded")

    def handle(lease: tickets.Lease, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        params = message.get("params") or {}
        if method == "initialize":
            return {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "workx-tool-gateway", "version": "1"},
            }
        if method in ("notifications/initialized", "notifications/cancelled"):
            return None
        if method == "ping":
            return {}
        if method == "tools/list":
            return {
                "tools": [
                    {"name": t.name, "description": t.description, "inputSchema": t.input_schema}
                    for t in allowed(lease)
                ]
            }
        if method == "tools/call":
            name = str(params.get("name", ""))
            tool = next((t for t in allowed(lease) if t.name == name), None)
            if tool is None:
                return _text_result(
                    "This tool is not available to this task.", error=True, structured={"code": "TOOL_NOT_ALLOWED"}
                )
            args = dict(params.get("arguments") or {})
            if tool.approval:
                gated = approval_gate(lease, tool, args)
                if gated is not None:
                    return gated
            return execute(lease, tool, args)
        raise KeyError(method)

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/mcp/{attempt_id}", response_model=None)
    async def mcp(attempt_id: str, request: Request) -> Response:
        try:
            lease = await run_in_threadpool(lease_for, request, attempt_id)
        except ApiError as exc:
            return JSONResponse({"error": exc.code}, status_code=401)
        try:
            message = await request.json()
        except ValueError:
            return JSONResponse(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}, status_code=400
            )
        try:
            result = await run_in_threadpool(handle, lease, message)
        except KeyError:
            return JSONResponse(
                {"jsonrpc": "2.0", "id": message.get("id"), "error": {"code": -32601, "message": "Method not found"}}
            )
        if result is None:
            return Response(status_code=202)
        headers = {"Mcp-Session-Id": request.headers.get("Mcp-Session-Id") or secrets.token_hex(16)}
        return JSONResponse({"jsonrpc": "2.0", "id": message.get("id"), "result": result}, headers=headers)

    return app
