"""Drives the real sign-in redirect flow: API /auth/login → issuer /authorize → API /auth/callback."""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


def start_login(
    client: TestClient,
    oidc: TestClient,
    email: str,
    *,
    return_to: str = "/",
    intent: str = "login",
    idp_hint: str | None = None,
) -> str:
    """Returns the callback URL the issuer redirects the browser to."""
    params = {"return_to": return_to, "intent": intent, **({"idp_hint": idp_hint} if idp_hint else {})}
    login = client.get("/api/v1/auth/login", params=params, follow_redirects=False)
    assert login.status_code == 302, login.text
    approved = oidc.get(login.headers["location"] + f"&login_hint={email}", follow_redirects=False)
    assert approved.status_code == 302, approved.text
    return approved.headers["location"]


def sign_in(
    client: TestClient, oidc: TestClient, email: str | None = None, *, return_to: str = "/", idp_hint: str | None = None
) -> dict[str, Any]:
    callback = start_login(client, oidc, email or unique_email(), return_to=return_to, idp_hint=idp_hint)
    done = client.get(callback, follow_redirects=False)
    assert done.status_code == 302, done.text
    assert "error=" not in done.headers["location"], done.headers["location"]
    me = client.get("/api/v1/me")
    assert me.status_code == 200, me.text
    body: dict[str, Any] = me.json()
    client.headers["X-WorkX-CSRF"] = body["csrf_token"]
    return body


def error_of(location: str) -> str | None:
    return parse_qs(urlparse(location).query).get("error", [None])[0]


def idem() -> dict[str, str]:
    return {"Idempotency-Key": uuid.uuid4().hex}
