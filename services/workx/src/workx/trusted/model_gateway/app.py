"""Model Gateway (trusted): Anthropic Messages API facade for sandboxes (Part 4 §2, Part 6 §5).

* Authenticates the Attempt's model ticket (sent where the SDK sends an API key) and injects the real key.
* The ticket pins the model; other models are refused.
* Enforces per-task and per-tenant monthly token budgets before calling upstream.
* Streams responses through unchanged while metering usage idempotently per upstream message.
"""

from __future__ import annotations

import hmac
import json
import logging
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from workx.core.db import Database
from workx.core.errors import ApiError
from workx.core.settings import ModelGatewaySettings
from workx.domains.knowledge.text import estimate_tokens
from workx.domains.runtime.models import TenantBudget
from workx.domains.usage import service as usage
from workx.domains.usage.models import UsageEvent
from workx.trusted.broker import tickets
from workx.trusted.model_gateway import embeddings

log = logging.getLogger("workx.model_gateway")


def _anthropic_error(status: int, kind: str, message: str) -> JSONResponse:
    return JSONResponse({"type": "error", "error": {"type": kind, "message": message}}, status_code=status)


def _ticket(request: Request) -> str | None:
    key = request.headers.get("x-api-key")
    if key:
        return key
    auth = request.headers.get("authorization", "")
    return auth[7:] if auth.lower().startswith("bearer ") else None


def tokens_used(db: Database, lease: tickets.Lease) -> tuple[int, int]:
    """(tokens this task, tokens this tenant this month)."""
    month = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    with db.transaction(tenant_id=lease.tenant_id) as session:
        task_total = session.execute(
            select(func.coalesce(func.sum(UsageEvent.quantity), 0)).where(
                UsageEvent.kind == "model_tokens", UsageEvent.task_id == lease.task_id
            )
        ).scalar_one()
        month_total = session.execute(
            select(func.coalesce(func.sum(UsageEvent.quantity), 0)).where(
                UsageEvent.kind == "model_tokens", UsageEvent.created_at >= month
            )
        ).scalar_one()
    return int(task_total), int(month_total)


def check_budget(db: Database, lease: tickets.Lease) -> str | None:
    with db.transaction(tenant_id=lease.tenant_id) as session:
        budget = session.get(TenantBudget, lease.tenant_id)
    if budget is None:
        return None
    task_total, month_total = tokens_used(db, lease)
    if budget.per_task_token_limit is not None and task_total >= budget.per_task_token_limit:
        return "Task token budget reached."
    if budget.monthly_token_limit is not None and month_total >= budget.monthly_token_limit:
        return "Workspace monthly token budget reached."
    return None


def record_usage(
    db: Database, lease: tickets.Lease, message_id: str, input_tokens: int, output_tokens: int, model: str
) -> None:
    total = input_tokens + output_tokens
    if total <= 0:
        return
    with db.transaction(tenant_id=lease.tenant_id) as session:
        usage.record(
            session,
            tenant_id=lease.tenant_id,
            kind="model_tokens",
            quantity=total,
            unit="token",
            source_event_id=f"model:{message_id}",
            task_id=lease.task_id,
            attempt_id=lease.attempt_id,
            data={"input": input_tokens, "output": output_tokens, "model": model},
        )


class UsageMeter:
    """Parses Anthropic SSE frames as they pass through to accumulate usage."""

    def __init__(self) -> None:
        self.buffer = b""
        self.message_id = ""
        self.input_tokens = 0
        self.output_tokens = 0

    def feed(self, chunk: bytes) -> None:
        self.buffer += chunk
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            if not line.startswith(b"data:"):
                continue
            try:
                data = json.loads(line[5:])
            except ValueError:
                continue
            if data.get("type") == "message_start":
                message = data.get("message", {})
                self.message_id = message.get("id", self.message_id)
                self.input_tokens += int(message.get("usage", {}).get("input_tokens", 0) or 0)
                self.input_tokens += int(message.get("usage", {}).get("cache_creation_input_tokens", 0) or 0)
            elif data.get("type") == "message_delta":
                self.output_tokens = max(self.output_tokens, int(data.get("usage", {}).get("output_tokens", 0) or 0))


def create_model_gateway_app(
    settings: ModelGatewaySettings | None = None, db: Database | None = None, *, upstream: httpx.Client | None = None
) -> FastAPI:
    settings = settings or ModelGatewaySettings()
    db = db or Database.connect(settings.database_url)
    client = upstream or httpx.Client(timeout=httpx.Timeout(settings.upstream_timeout_seconds, connect=10))
    app = FastAPI(title="WorkX Model Gateway", docs_url=None, redoc_url=None, openapi_url=None)

    def authorize(request: Request, body: dict[str, Any]) -> tickets.Lease | JSONResponse:
        try:
            with db.transaction() as session:
                lease = tickets.verify(session, _ticket(request), "model")
        except ApiError as exc:
            return _anthropic_error(401, "authentication_error", exc.detail)
        allowed = lease.scopes.get("model")
        if allowed and body.get("model") != allowed:
            return _anthropic_error(403, "permission_error", "This attempt may only use its assigned model.")
        return lease

    def upstream_headers(request: Request) -> dict[str, str]:
        headers = {
            "x-api-key": settings.anthropic_api_key.get_secret_value(),
            "anthropic-version": request.headers.get("anthropic-version", "2023-06-01"),
            "content-type": "application/json",
        }
        beta = request.headers.get("anthropic-beta")
        if beta:
            headers["anthropic-beta"] = beta
        return headers

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    embedder = embeddings.from_settings(settings)

    @app.exception_handler(ApiError)
    async def errors(_: object, exc: ApiError) -> JSONResponse:
        return JSONResponse({"code": exc.code, "detail": exc.detail}, status_code=exc.status)

    @app.post("/internal/embeddings")
    def embed(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """Embedding Gateway (Part 7 §1): internal callers only; the provider key never leaves this process."""
        token = request.headers.get("x-workx-internal-token", "")
        if not hmac.compare_digest(token, settings.embedding_token.get_secret_value()):
            raise ApiError(401, "UNAUTHENTICATED", "Internal token required.")
        texts = body.get("texts")
        if not isinstance(texts, list) or not texts or len(texts) > 256 or not all(isinstance(t, str) for t in texts):
            raise ApiError(400, "VALIDATION_FAILED", "texts must be 1-256 strings.")
        vectors = embedder.embed([t[:8000] for t in texts])
        tenant = body.get("tenant_id")
        if tenant:
            with db.transaction(tenant_id=uuid.UUID(str(tenant))) as session:
                usage.record(
                    session,
                    tenant_id=uuid.UUID(str(tenant)),
                    kind="embedding_tokens",
                    quantity=sum(estimate_tokens(t) for t in texts),
                    unit="token",
                    source_event_id=f"emb:{uuid.uuid4().hex}",
                    data={"profile": embedder.profile, "count": len(texts)},
                )
        return {"profile": embedder.profile, "vectors": vectors}

    @app.post("/v1/messages", response_model=None)
    async def messages(request: Request) -> Response:
        try:
            body = await request.json()
        except ValueError:
            return _anthropic_error(400, "invalid_request_error", "Body must be JSON.")
        lease = await run_in_threadpool(authorize, request, body)
        if isinstance(lease, JSONResponse):
            return lease
        over = await run_in_threadpool(check_budget, db, lease)
        if over:
            return _anthropic_error(429, "rate_limit_error", over)
        url = settings.anthropic_base_url.rstrip("/") + "/v1/messages"
        headers = upstream_headers(request)
        model = str(body.get("model", ""))
        if not body.get("stream"):
            response = await run_in_threadpool(lambda: client.post(url, json=body, headers=headers))
            if response.status_code == 200:
                data = response.json()
                used = data.get("usage", {})
                await run_in_threadpool(
                    record_usage,
                    db,
                    lease,
                    data.get("id") or str(uuid.uuid4()),
                    int(used.get("input_tokens", 0)),
                    int(used.get("output_tokens", 0)),
                    model,
                )
            return Response(response.content, status_code=response.status_code, media_type="application/json")

        request_ctx = client.build_request("POST", url, json=body, headers=headers)
        upstream_response = await run_in_threadpool(lambda: client.send(request_ctx, stream=True))
        if upstream_response.status_code != 200:
            content = await run_in_threadpool(upstream_response.read)
            upstream_response.close()
            return Response(content, status_code=upstream_response.status_code, media_type="application/json")
        meter = UsageMeter()
        chunks: Iterator[bytes] = upstream_response.iter_bytes()

        async def relay() -> AsyncIterator[bytes]:
            try:
                while True:
                    chunk = await run_in_threadpool(next, chunks, None)
                    if chunk is None:
                        break
                    meter.feed(chunk)
                    yield chunk
            finally:
                upstream_response.close()
                await run_in_threadpool(
                    record_usage,
                    db,
                    lease,
                    meter.message_id or str(uuid.uuid4()),
                    meter.input_tokens,
                    meter.output_tokens,
                    model,
                )

        return StreamingResponse(relay(), media_type="text/event-stream")

    @app.post("/v1/messages/count_tokens", response_model=None)
    async def count_tokens(request: Request) -> Response:
        body = await request.json()
        lease = await run_in_threadpool(authorize, request, body)
        if isinstance(lease, JSONResponse):
            return lease
        url = settings.anthropic_base_url.rstrip("/") + "/v1/messages/count_tokens"
        response = await run_in_threadpool(lambda: client.post(url, json=body, headers=upstream_headers(request)))
        return Response(response.content, status_code=response.status_code, media_type="application/json")

    return app
