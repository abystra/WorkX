"""Local OpenID Connect issuer for development and tests: ``workx dev-oidc``.

Speaks the same protocol the API uses with Keycloak (discovery, JWKS, authorization code + PKCE S256, RS256
ID tokens, end-session), so the real sign-in code path runs locally without an identity server. It accepts
any email typed into its form; it must never run in staging or production (``create_dev_oidc_app`` refuses).
"""

from __future__ import annotations

import hashlib
import html
import secrets
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from joserfc import jwt
from joserfc.jwk import RSAKey

from workx.core.settings import Environment
from workx.domains.identity.tokens import pkce_challenge


@dataclass
class _Grant:
    client_id: str
    redirect_uri: str
    nonce: str
    challenge: str
    email: str
    name: str
    verified: bool
    expires: float


@dataclass
class DevIssuer:
    issuer: str
    client_id: str = "workx-web"
    client_secret: str = ""
    key: RSAKey = field(default_factory=lambda: RSAKey.generate_key(2048))
    grants: dict[str, _Grant] = field(default_factory=dict)

    def subject(self, email: str) -> str:
        return "dev-" + hashlib.sha256(email.lower().encode()).hexdigest()[:20]

    def id_token(self, grant: _Grant) -> str:
        now = int(time.time())
        claims = {
            "iss": self.issuer,
            "sub": self.subject(grant.email),
            "aud": grant.client_id,
            "iat": now,
            "exp": now + 300,
            "nonce": grant.nonce,
            "email": grant.email,
            "email_verified": grant.verified,
            "name": grant.name,
            "sid": secrets.token_hex(8),
            "acr": "password",
        }
        header = {"alg": "RS256", "kid": self.key.thumbprint()}
        return jwt.encode(header, claims, self.key)


_FORM = """<!doctype html><meta charset="utf-8"><title>WorkX dev sign-in</title>
<style>body{{font:14px system-ui;max-width:420px;margin:80px auto;color:#1f2329}}input,button{{font:inherit;padding:8px;
width:100%;box-sizing:border-box;margin:6px 0}}button{{background:#24262b;color:#fff;border:0;border-radius:6px}}
p{{color:#6b7079}}</style>
<h1>Development sign-in</h1><p>Local OIDC issuer for development only. Any email is accepted.</p>
<form method="post">{hidden}<label>Email<input name="email" type="email" required autofocus></label>
<label>Name<input name="name"></label><button>Continue</button></form>"""


def create_dev_oidc_app(
    issuer: str, *, environment: Environment = Environment.DEVELOPMENT, client_secret: str = ""
) -> FastAPI:
    if environment in (Environment.STAGING, Environment.PRODUCTION):
        raise RuntimeError("The development OIDC issuer must not run in staging or production.")
    state = DevIssuer(issuer=issuer.rstrip("/"), client_secret=client_secret)
    app = FastAPI(title="WorkX development OIDC issuer", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.issuer = state

    @app.get("/.well-known/openid-configuration")
    def discovery() -> dict[str, Any]:
        base = state.issuer
        return {
            "issuer": base,
            "authorization_endpoint": f"{base}/authorize",
            "token_endpoint": f"{base}/token",
            "jwks_uri": f"{base}/jwks",
            "end_session_endpoint": f"{base}/logout",
            "response_types_supported": ["code"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "code_challenge_methods_supported": ["S256"],
            "scopes_supported": ["openid", "email", "profile"],
        }

    @app.get("/jwks")
    def jwks() -> dict[str, Any]:
        public = dict(state.key.as_dict(private=False))
        public.update({"kid": state.key.thumbprint(), "use": "sig", "alg": "RS256"})
        return {"keys": [public]}

    def _approve(params: dict[str, str], email: str, name: str) -> RedirectResponse:
        if params.get("client_id") != state.client_id or params.get("code_challenge_method") != "S256":
            raise HTTPException(400, "invalid client or PKCE method")
        code = secrets.token_urlsafe(24)
        state.grants[code] = _Grant(
            client_id=params["client_id"],
            redirect_uri=params["redirect_uri"],
            nonce=params.get("nonce", ""),
            challenge=params["code_challenge"],
            email=email,
            name=name or email.split("@")[0],
            verified=not email.startswith("unverified"),
            expires=time.time() + 60,
        )
        query = urlencode({"code": code, "state": params.get("state", "")})
        return RedirectResponse(f"{params['redirect_uri']}?{query}", status_code=302)

    @app.get("/authorize", response_model=None)
    def authorize(request: Request) -> HTMLResponse | RedirectResponse:
        params = dict(request.query_params)
        if params.get("login_hint"):
            # Scripted sign-in for tests and local automation.
            return _approve(params, params["login_hint"], params.get("name", ""))
        hidden = "".join(
            f'<input type="hidden" name="{html.escape(k)}" value="{html.escape(v)}">' for k, v in params.items()
        )
        return HTMLResponse(_FORM.format(hidden=hidden))

    @app.post("/authorize")
    async def authorize_form(request: Request) -> RedirectResponse:
        form = {k: str(v) for k, v in (await request.form()).items()}
        return _approve(form, form.pop("email", ""), form.pop("name", ""))

    @app.post("/token")
    def token(
        request: Request,
        grant_type: str = Form(),
        code: str = Form(),
        redirect_uri: str = Form(),
        code_verifier: str = Form(),
        client_id: str = Form(default=""),
    ) -> JSONResponse:
        grant = state.grants.pop(code, None)
        error = None
        if (
            grant_type != "authorization_code"
            or grant is None
            or grant.expires < time.time()
            or grant.redirect_uri != redirect_uri
            or pkce_challenge(code_verifier) != grant.challenge
        ):
            error = "invalid_grant"
        elif state.client_secret and request.headers.get("authorization", "") == "":
            error = "invalid_client"
        if error or grant is None:
            return JSONResponse({"error": error}, status_code=400)
        return JSONResponse(
            {
                "access_token": secrets.token_urlsafe(24),
                "token_type": "Bearer",
                "expires_in": 300,
                "id_token": state.id_token(grant),
            }
        )

    @app.get("/logout")
    def logout(post_logout_redirect_uri: str = "/") -> RedirectResponse:
        return RedirectResponse(post_logout_redirect_uri, status_code=302)

    return app
