"""HTTP API process: ``workx api`` (Part 10). Assembles domain routers; contains no business rules."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from workx.core import context, ids
from workx.core.db import Database
from workx.core.errors import ApiError
from workx.core.settings import ApiSettings
from workx.platform.web import AppState

log = logging.getLogger("workx.api")
API_PREFIX = "/api/v1"


def _problem(error: ApiError) -> JSONResponse:
    return JSONResponse(
        error.problem(context.request_id.get()),
        status_code=error.status,
        media_type="application/problem+json",
        headers=error.headers,
    )


def create_app(settings: ApiSettings | None = None, db: Database | None = None) -> FastAPI:
    settings = settings or ApiSettings()
    db = db or Database.connect(settings.database_url)
    app = FastAPI(
        title="WorkX API",
        version="1.0.0",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=None if settings.is_production else f"{API_PREFIX}/docs",
        redoc_url=None,
    )
    app.state.workx = AppState(settings=settings, db=db)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        incoming = request.headers.get("x-request-id", "")
        rid = incoming if incoming.startswith("req_") and len(incoming) <= 64 else ids.new("request")[1]
        token = context.request_id.set(rid)
        try:
            response = await call_next(request)
        finally:
            context.request_id.reset(token)
        response.headers["X-Request-Id"] = rid
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        return _problem(exc)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [{"loc": [str(p) for p in e.get("loc", ())], "msg": e.get("msg", "")} for e in exc.errors()]
        return _problem(ApiError(400, "VALIDATION_FAILED", "The request is not valid.", data={"errors": fields}))

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
        return _problem(ApiError(exc.status_code, code, str(exc.detail)))

    @app.exception_handler(Exception)
    async def unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error")
        return _problem(ApiError(500, "INTERNAL", "Something went wrong. Try again."))

    health = APIRouter(tags=["health"])

    @health.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @health.get("/readyz", include_in_schema=False)
    def readyz() -> dict[str, str]:
        try:
            with db.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as exc:
            raise ApiError(503, "UPSTREAM_UNAVAILABLE", "Database is not reachable.") from exc
        return {"status": "ready"}

    app.include_router(health)
    for router in domain_routers():
        app.include_router(router, prefix=API_PREFIX)
    return app


def domain_routers() -> list[APIRouter]:
    """Routers contributed by domains. Grows phase by phase (docs/delivery/PLAN.md)."""
    return []
