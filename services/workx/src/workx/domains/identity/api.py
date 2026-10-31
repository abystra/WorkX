"""/auth/* and /me routes (Part 9 §3, Part 11 §3)."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from workx.core import ids
from workx.core.errors import not_found, validation
from workx.domains.identity import service
from workx.domains.identity.auth import Authenticated, State
from workx.domains.identity.models import LoginSession, User
from workx.domains.identity.oidc import OidcError, OidcProvider
from workx.domains.tenancy.models import Membership
from workx.platform.web import AppState

router = APIRouter(tags=["identity"])
BINDING_COOKIE = "workx_oidc"


def provider(state: AppState) -> OidcProvider:
    oidc: OidcProvider = state.services["oidc"]
    return oidc


def _set_cookie(response: Response, state: AppState, name: str, value: str, *, max_age: int, path: str = "/") -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        path=path,
        httponly=True,
        secure=state.settings.session_cookie_secure,
        samesite="lax",
    )


@router.get("/auth/login", summary="Start sign-in or sign-up at the identity provider")
def login(
    state: State,
    intent: Annotated[str, Query(pattern="^(login|signup)$")] = "login",
    return_to: str = "/",
) -> RedirectResponse:
    with state.db.transaction() as session:
        start = service.begin_login(session, provider(state), state.settings, intent=intent, return_to=return_to)
    response = RedirectResponse(start.authorization_url, status_code=302)
    _set_cookie(response, state, BINDING_COOKIE, start.browser_binding, max_age=600, path="/api/v1/auth")
    return response


@router.get("/auth/callback", summary="OIDC redirect target")
def callback(
    request: Request,
    state: State,
    code: str | None = None,
    login_state: Annotated[str | None, Query(alias="state")] = None,
    error: str | None = None,
) -> RedirectResponse:
    web = state.settings.public_base_url.rstrip("/")

    def failure(reason: str) -> RedirectResponse:
        return RedirectResponse(f"{web}/login?{urlencode({'error': reason})}", status_code=302)

    if error or not code or not login_state:
        return failure(error if error in ("access_denied", "login_required") else "login_failed")
    try:
        with state.db.transaction() as session:
            result = service.complete_login(
                session,
                provider(state),
                state.settings,
                state=login_state,
                code=code,
                browser_binding=request.cookies.get(BINDING_COOKIE),
                user_agent=request.headers.get("user-agent"),
                client_ip=request.client.host if request.client else None,
            )
    except OidcError as exc:
        # The failed attempt rolled back; consume the state separately so the callback cannot be replayed.
        with state.db.transaction() as session:
            service.mark_consumed(session, login_state)
        return failure(exc.code)
    response = RedirectResponse(f"{web}{result.return_to}", status_code=302)
    settings = state.settings
    _set_cookie(
        response,
        state,
        settings.session_cookie_name,
        result.session_token,
        max_age=settings.session_absolute_days * 86400,
    )
    response.delete_cookie(BINDING_COOKIE, path="/api/v1/auth")
    return response


class LogoutOut(BaseModel):
    end_session_url: str | None


@router.post("/auth/logout", summary="End this session")
def logout(principal: Authenticated, state: State, response: Response) -> LogoutOut:
    with state.db.transaction(principal_id=principal.user_id) as session:
        login = session.get(LoginSession, principal.login_session.id)
        assert login is not None
        service.revoke_session(session, login, actor_user_id=principal.user_id, reason="logout")
    response.delete_cookie(state.settings.session_cookie_name, path="/")
    url = provider(state).end_session_url(
        id_token_hint=principal.login_session.id_token_hint,
        post_logout_redirect_uri=f"{state.settings.public_base_url.rstrip('/')}/login",
    )
    return LogoutOut(end_session_url=url)


class MeOut(BaseModel):
    id: str
    email: str
    name: str
    locale: str
    notifications: bool
    last_tenant_id: str | None
    csrf_token: str


def _me(user: User, csrf: str) -> MeOut:
    return MeOut(
        id=ids.encode("user", user.id),
        email=user.primary_email,
        name=user.display_name,
        locale=user.locale,
        notifications=user.notifications_enabled,
        last_tenant_id=ids.encode("tenant", user.last_tenant_id) if user.last_tenant_id else None,
        csrf_token=csrf,
    )


@router.get("/me", summary="Current user and CSRF token")
def me(principal: Authenticated, state: State) -> MeOut:
    return _me(principal.user, service.csrf_token(state.settings, principal.session_token))


class MePatch(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    locale: str | None = Field(default=None, pattern="^(en|zh-CN)$")
    notifications: bool | None = None


@router.patch("/me", summary="Update profile")
def update_me(body: MePatch, principal: Authenticated, state: State) -> MeOut:
    with state.db.transaction(principal_id=principal.user_id) as session:
        user = session.get(User, principal.user_id)
        assert user is not None
        if body.name is not None:
            name = " ".join(body.name.split())
            if not name:
                raise validation("Name is required.", data={"field": "name"})
            user.display_name = name
        if body.locale is not None:
            user.locale = body.locale
        if body.notifications is not None:
            user.notifications_enabled = body.notifications
    return _me(user, service.csrf_token(state.settings, principal.session_token))


class PreferencesIn(BaseModel):
    last_tenant_id: str


@router.put("/me/preferences", status_code=204, summary="Remember the last workspace (navigation only)")
def preferences(body: PreferencesIn, principal: Authenticated, state: State) -> Response:
    tenant_id = ids.decode("tenant", body.last_tenant_id)
    with state.db.transaction(principal_id=principal.user_id) as session:
        member = (
            tenant_id
            and session.execute(
                select(Membership.id).where(
                    Membership.tenant_id == tenant_id,
                    Membership.user_id == principal.user_id,
                    Membership.status == "active",
                )
            ).first()
        )
        if not member:
            raise not_found()
        user = session.get(User, principal.user_id)
        assert user is not None
        user.last_tenant_id = tenant_id
    return Response(status_code=204)


class SessionOut(BaseModel):
    id: str
    current: bool
    created_at: str
    last_seen_at: str
    user_agent: str | None


@router.get("/me/sessions", summary="Active sign-in sessions")
def sessions(principal: Authenticated, state: State) -> list[SessionOut]:
    with state.db.transaction(principal_id=principal.user_id) as session:
        rows = service.active_sessions(session, principal.user_id)
    return [
        SessionOut(
            id=ids.encode("login_session", row.id),
            current=row.id == principal.login_session.id,
            created_at=row.created_at.isoformat(),
            last_seen_at=row.last_seen_at.isoformat(),
            user_agent=row.user_agent,
        )
        for row in rows
    ]


@router.delete("/me/sessions/{session_id}", status_code=204, summary="Sign out another session")
def revoke(session_id: str, principal: Authenticated, state: State) -> Response:
    target = ids.decode("login_session", session_id)
    with state.db.transaction(principal_id=principal.user_id) as session:
        login = session.get(LoginSession, target) if target else None
        if login is None or login.user_id != principal.user_id:
            raise not_found()
        service.revoke_session(session, login, actor_user_id=principal.user_id, reason="user")
    return Response(status_code=204)
