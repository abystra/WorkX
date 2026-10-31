"""Request authentication: session cookie → LoginSession → User, plus CSRF on state-changing methods."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlparse

from fastapi import Depends, Request

from workx.core.errors import ApiError
from workx.domains.identity import service, tokens
from workx.domains.identity.service import Principal
from workx.platform.web import AppState, app_state

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_HEADER = "x-workx-csrf"


def _origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def check_origin(request: Request, state: AppState) -> None:
    origin = request.headers.get("origin")
    if origin is None:
        return
    allowed = {
        _origin(state.settings.public_base_url),
        _origin(state.settings.api_base_url),
        *state.settings.cors_origins,
    }
    if origin not in allowed:
        raise ApiError(403, "CSRF_FAILED", "Request origin is not allowed.")


def current_principal(request: Request, state: Annotated[AppState, Depends(app_state)]) -> Principal:
    raw = request.cookies.get(state.settings.session_cookie_name)
    with state.db.transaction() as session:
        principal = service.authenticate(session, raw, state.settings)
    if request.method not in SAFE_METHODS:
        check_origin(request, state)
        expected = service.csrf_token(state.settings, principal.session_token)
        if not tokens.constant_equals(request.headers.get(CSRF_HEADER, ""), expected):
            raise ApiError(403, "CSRF_FAILED", "Reload the page and try again.")
    return principal


Authenticated = Annotated[Principal, Depends(current_principal)]
State = Annotated[AppState, Depends(app_state)]
