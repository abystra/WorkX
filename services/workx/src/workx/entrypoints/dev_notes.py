"""Test provider for user OAuth and remote MCP (``workx dev-notes``): a notes service that is at the same time

* an OAuth 2.1 authorization server: metadata (RFC 8414), dynamic client registration (RFC 7591), authorization
  code + PKCE (S256 only), rotating refresh tokens (a reused refresh token is refused);
* a protected resource (RFC 9728) serving an MCP server (Streamable HTTP, JSON responses) at ``/mcp``.

``/_admin/expire`` and ``/_admin/revoke`` let tests force a refresh or a provider-side revocation; ``/_stats``
counts token requests. Development and tests only.
"""

from __future__ import annotations

import base64
import hashlib
import html
import secrets
import threading
import time
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from workx.core.settings import Environment

SCOPES = ["notes.read", "notes.write"]
TOOLS = [
    {
        "name": "list_notes",
        "description": "List your notes.",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
    },
    {
        "name": "create_note",
        "description": "Create a note.",
        "inputSchema": {
            "type": "object",
            "properties": {"title": {"type": "string"}, "body": {"type": "string"}},
            "required": ["title", "body"],
        },
    },
]


def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def create_dev_notes_app(
    *, environment: Environment = Environment.DEVELOPMENT, access_ttl: int = 300, refresh_delay: float = 0.0
) -> FastAPI:
    if environment in (Environment.STAGING, Environment.PRODUCTION):
        raise RuntimeError("The test notes provider must not run in staging or production.")
    app = FastAPI(title="WorkX test notes provider", docs_url=None, redoc_url=None, openapi_url=None)
    lock = threading.Lock()
    clients: dict[str, list[str]] = {}
    codes: dict[str, dict[str, Any]] = {}
    access: dict[str, dict[str, Any]] = {}
    refresh: dict[str, dict[str, Any]] = {}
    notes: dict[str, list[dict[str, str]]] = {}
    stats = {"register": 0, "authorize": 0, "token_code": 0, "token_refresh": 0, "refresh_refused": 0, "mcp_calls": 0}
    app.state.stats = stats

    def base(request: Request) -> str:
        return str(request.base_url).rstrip("/")

    def issue(account: str, client_id: str, scope: str) -> dict[str, Any]:
        token, renew = "nat_" + secrets.token_urlsafe(24), "nrt_" + secrets.token_urlsafe(24)
        access[token] = {"account": account, "scope": scope, "exp": time.time() + access_ttl}
        refresh[renew] = {"account": account, "client_id": client_id, "scope": scope}
        return {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": access_ttl,
            "refresh_token": renew,
            "scope": scope,
            "account": account,
        }

    @app.get("/.well-known/oauth-protected-resource/mcp")
    @app.get("/.well-known/oauth-protected-resource")
    def resource_metadata(request: Request) -> dict[str, Any]:
        return {
            "resource": f"{base(request)}/mcp",
            "authorization_servers": [base(request)],
            "scopes_supported": SCOPES,
            "bearer_methods_supported": ["header"],
        }

    @app.get("/.well-known/oauth-authorization-server")
    def server_metadata(request: Request) -> dict[str, Any]:
        root = base(request)
        return {
            "issuer": root,
            "authorization_endpoint": f"{root}/authorize",
            "token_endpoint": f"{root}/token",
            "registration_endpoint": f"{root}/register",
            "scopes_supported": SCOPES,
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
        }

    @app.post("/register", status_code=201)
    def register(body: dict[str, Any]) -> dict[str, Any]:
        uris = body.get("redirect_uris")
        if not isinstance(uris, list) or not uris or not all(isinstance(u, str) for u in uris):
            return JSONResponse({"error": "invalid_redirect_uri"}, status_code=400)  # type: ignore[return-value]
        client_id = "notes_client_" + secrets.token_hex(8)
        with lock:
            clients[client_id] = list(uris)
            stats["register"] += 1
        return {"client_id": client_id, "redirect_uris": uris, "token_endpoint_auth_method": "none"}

    def _valid_request(params: dict[str, str]) -> str | None:
        if params.get("response_type") != "code":
            return "unsupported_response_type"
        if params.get("redirect_uri") not in clients.get(params.get("client_id", ""), []):
            return "invalid_client"
        if params.get("code_challenge_method") != "S256" or not params.get("code_challenge"):
            return "invalid_request"
        return None

    @app.get("/authorize", response_class=HTMLResponse)
    def authorize_page(request: Request) -> Response:
        params = dict(request.query_params)
        problem = _valid_request(params)
        if problem:
            return HTMLResponse(f"<h1>Invalid request</h1><p>{problem}</p>", status_code=400)
        hidden = "".join(
            f'<input type="hidden" name="{html.escape(k)}" value="{html.escape(v)}">' for k, v in params.items()
        )
        return HTMLResponse(
            "<!doctype html><title>Notes: authorize</title><h1>Allow WorkX to use your notes?</h1>"
            f'<form method="post" action="/authorize">{hidden}'
            '<label>Account <input name="account" value="notes-user@example.com"></label>'
            '<button name="decision" value="allow">Allow</button>'
            '<button name="decision" value="deny">Deny</button></form>'
        )

    @app.post("/authorize")
    async def authorize_decision(request: Request) -> Response:
        params = {k: str(v) for k, v in (await request.form()).items()}
        problem = _valid_request(params)
        if problem:
            return HTMLResponse(f"<h1>Invalid request</h1><p>{problem}</p>", status_code=400)
        target = params["redirect_uri"]
        if params.get("decision") != "allow":
            query = urlencode({"error": "access_denied", "state": params.get("state", "")})
            return RedirectResponse(f"{target}?{query}", status_code=302)
        code = "nc_" + secrets.token_urlsafe(24)
        with lock:
            codes[code] = {
                "client_id": params["client_id"],
                "redirect_uri": target,
                "challenge": params["code_challenge"],
                "account": params.get("account") or "notes-user@example.com",
                "scope": " ".join(s for s in params.get("scope", "").split() if s in SCOPES) or "notes.read",
                "exp": time.time() + 120,
            }
            stats["authorize"] += 1
        return RedirectResponse(
            f"{target}?{urlencode({'code': code, 'state': params.get('state', '')})}", status_code=302
        )

    @app.post("/token")
    def token(
        grant_type: str = Form(...),
        client_id: str = Form(""),
        code: str = Form(""),
        code_verifier: str = Form(""),
        redirect_uri: str = Form(""),
        refresh_token: str = Form(""),
    ) -> Response:
        refused = JSONResponse({"error": "invalid_grant"}, status_code=400)
        if grant_type == "authorization_code":
            with lock:
                entry = codes.pop(code, None)
                if (
                    entry is None
                    or entry["exp"] < time.time()
                    or entry["client_id"] != client_id
                    or entry["redirect_uri"] != redirect_uri
                    or _challenge(code_verifier) != entry["challenge"]
                ):
                    return refused
                stats["token_code"] += 1
                return JSONResponse(issue(entry["account"], client_id, entry["scope"]))
        if grant_type == "refresh_token":
            if refresh_delay:
                time.sleep(refresh_delay)  # widens the window in which a second refresher would collide
            with lock:
                entry = refresh.pop(refresh_token, None)  # rotation: every refresh token works once
                if entry is None or entry["client_id"] != client_id:
                    stats["refresh_refused"] += 1
                    return refused
                stats["token_refresh"] += 1
                return JSONResponse(issue(entry["account"], client_id, entry["scope"]))
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    @app.post("/_admin/expire")
    def expire_all() -> dict[str, int]:
        with lock:
            for entry in access.values():
                entry["exp"] = 0
            return {"expired": len(access)}

    @app.post("/_admin/revoke")
    def revoke_all() -> dict[str, int]:
        with lock:
            count = len(access) + len(refresh)
            access.clear()
            refresh.clear()
            return {"revoked": count}

    @app.get("/_stats")
    def get_stats() -> dict[str, Any]:
        with lock:
            return {**stats, "notes": sum(len(v) for v in notes.values())}

    @app.post("/mcp")
    async def mcp(request: Request) -> Response:
        auth = request.headers.get("authorization", "")
        grant = access.get(auth[7:]) if auth.lower().startswith("bearer ") else None
        if grant is None or grant["exp"] < time.time():
            metadata = f"{base(request)}/.well-known/oauth-protected-resource/mcp"
            return JSONResponse(
                {"error": "invalid_token"},
                status_code=401,
                headers={"WWW-Authenticate": f'Bearer resource_metadata="{metadata}"'},
            )
        message = await request.json()
        method, params = message.get("method"), message.get("params") or {}
        if "id" not in message:
            return Response(status_code=202)
        with lock:
            stats["mcp_calls"] += 1
        headers: dict[str, str] = {}
        if method == "initialize":
            headers["Mcp-Session-Id"] = secrets.token_hex(8)
            result: dict[str, Any] = {
                "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "workx-dev-notes", "version": "1"},
            }
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            name, args = params.get("name"), params.get("arguments") or {}
            mine = notes.setdefault(grant["account"], [])
            if name == "list_notes":
                query = str(args.get("query") or "").lower()
                found = [n for n in mine if query in (n["title"] + n["body"]).lower()]
                result = {
                    "content": [{"type": "text", "text": f"{len(found)} notes"}],
                    "structuredContent": {"notes": found},
                }
            elif name == "create_note":
                if "notes.write" not in grant["scope"].split():
                    result = {"content": [{"type": "text", "text": "Missing scope notes.write"}], "isError": True}
                else:
                    note = {"id": f"note_{len(mine) + 1}", "title": str(args["title"]), "body": str(args["body"])}
                    with lock:
                        mine.append(note)
                    result = {"content": [{"type": "text", "text": "Created"}], "structuredContent": {"note": note}}
            else:
                return JSONResponse(
                    {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32602, "message": "Unknown tool"}}
                )
        else:
            return JSONResponse(
                {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": "Method not found"}}
            )
        return JSONResponse({"jsonrpc": "2.0", "id": message["id"], "result": result}, headers=headers)

    return app
