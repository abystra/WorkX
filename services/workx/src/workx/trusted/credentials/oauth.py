"""OAuth for user connections (Part 6 §4): endpoint discovery, client registration, code exchange, refresh.

* Static endpoints come from the connector definition (Feishu); remote MCP servers publish theirs: protected
  resource metadata (RFC 9728) names the authorization server, whose metadata (RFC 8414) lists the endpoints.
* Without a configured ``client_id`` the client registers itself (RFC 7591) once per workspace installation.
* Always authorization code + PKCE (S256) with a single-use ``state``.
* Refresh is single-flight: the refresh credential row is locked while one process refreshes; the others wait
  and then use the new access token instead of spending the (rotating) refresh token again.

Only trusted processes (broker, Tool Gateway) import this module.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from workx.core import ids
from workx.core.errors import ApiError
from workx.core.orm import utcnow
from workx.domains.connections.catalog import Connector
from workx.domains.connections.models import Connection, ConnectorInstallation, Credential
from workx.trusted.credentials.models import SecretVersion
from workx.trusted.credentials.vault import Vault

REFRESH_MARGIN = timedelta(seconds=60)


class OAuthFailure(Exception):
    """The provider refused (``invalid_grant`` and friends): the user has to authorize again."""


@dataclass(frozen=True)
class Endpoints:
    authorize_url: str
    token_url: str
    registration_url: str | None
    scopes: tuple[str, ...]
    exchange_format: str = "form"
    resource: str | None = None  # RFC 8707 resource indicator (remote MCP servers)


@dataclass(frozen=True)
class Tokens:
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    scopes: list[str]
    account: str | None


def well_known(url: str, name: str) -> list[str]:
    """RFC 8414 §3.1 / RFC 9728 §3.1: the well-known segment goes between the host and the path."""
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.rstrip("/")
    candidates = [f"{origin}/.well-known/{name}{path}"] if path else []
    return [*candidates, f"{origin}/.well-known/{name}"]


def _first_json(http: httpx.Client, urls: list[str]) -> dict[str, Any]:
    for url in urls:
        response = http.get(url)
        if response.status_code == 200:
            data: dict[str, Any] = response.json()
            return data
    raise ApiError(502, "UPSTREAM_UNAVAILABLE", "The service did not publish OAuth metadata.")


def endpoints_for(connector: Connector, config: dict[str, Any], http: httpx.Client) -> Endpoints:
    assert connector.oauth is not None
    if not connector.remote_mcp:
        return Endpoints(
            connector.oauth.authorize_url,
            connector.oauth.token_url,
            None,
            connector.oauth.scopes,
            connector.oauth.exchange_format,
        )
    resource_url = str(config.get("base_url") or "")
    if not resource_url.startswith(("https://", "http://")):
        raise ApiError(409, "CONNECTOR_NOT_CONFIGURED", "Set the server URL for this connector first.")
    resource = _first_json(http, well_known(resource_url, "oauth-protected-resource"))
    issuer = (resource.get("authorization_servers") or [None])[0]
    if not issuer:
        raise ApiError(502, "UPSTREAM_UNAVAILABLE", "The server names no authorization server.")
    server = _first_json(http, well_known(issuer, "oauth-authorization-server"))
    if "S256" not in (server.get("code_challenge_methods_supported") or []):
        raise ApiError(502, "UPSTREAM_UNAVAILABLE", "The authorization server does not support PKCE (S256).")
    scopes = tuple(
        s for s in connector.oauth.scopes if s in (resource.get("scopes_supported") or connector.oauth.scopes)
    )
    return Endpoints(
        server["authorization_endpoint"],
        server["token_endpoint"],
        server.get("registration_endpoint"),
        scopes,
        resource=str(resource.get("resource") or resource_url),
    )


def installation_secret(session: Session, vault: Vault, tenant_id: uuid.UUID, connector_id: str) -> str | None:
    credential = session.execute(
        select(Credential).where(
            Credential.tenant_id == tenant_id,
            Credential.installation_connector_id == connector_id,
            Credential.kind == "app_secret",
        )
    ).scalar_one_or_none()
    if credential is None or credential.active_version_id is None:
        return None
    return vault.read(session, credential)[0]


def put_installation_secret(
    session: Session, vault: Vault, tenant_id: uuid.UUID, connector_id: str, value: str
) -> SecretVersion:
    credential = session.execute(
        select(Credential).where(
            Credential.tenant_id == tenant_id,
            Credential.installation_connector_id == connector_id,
            Credential.kind == "app_secret",
        )
    ).scalar_one_or_none()
    if credential is None:
        credential = Credential(
            id=ids.uuid7(),
            tenant_id=tenant_id,
            connection_id=None,
            installation_connector_id=connector_id,
            usage_class="tool",
            kind="app_secret",
        )
        session.add(credential)
        session.flush()
    return vault.put(session, credential, value)


def ensure_client(
    session: Session,
    vault: Vault,
    installation: ConnectorInstallation,
    endpoints: Endpoints,
    redirect_uri: str,
    http: httpx.Client,
) -> str:
    """The workspace's client_id for this connector: configured, or registered once (RFC 7591)."""
    client_id = str((installation.config or {}).get("client_id") or "")
    if client_id:
        return client_id
    if not endpoints.registration_url:
        raise ApiError(409, "CONNECTOR_NOT_CONFIGURED", "Set the OAuth client ID for this connector first.")
    response = http.post(
        endpoints.registration_url,
        json={
            "client_name": "WorkX",
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": " ".join(endpoints.scopes),
        },
    )
    if response.status_code not in (200, 201):
        raise ApiError(502, "UPSTREAM_UNAVAILABLE", "Client registration failed.")
    registered = response.json()
    installation.config = {**(installation.config or {}), "client_id": registered["client_id"]}
    if registered.get("client_secret"):
        put_installation_secret(
            session, vault, installation.tenant_id, installation.connector_id, registered["client_secret"]
        )
    return str(registered["client_id"])


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def authorize_url(endpoints: Endpoints, client_id: str, redirect_uri: str, state: str, challenge: str) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if endpoints.scopes:
        params["scope"] = " ".join(endpoints.scopes)
    if endpoints.resource:
        params["resource"] = endpoints.resource
    separator = "&" if "?" in endpoints.authorize_url else "?"
    return f"{endpoints.authorize_url}{separator}{urlencode(params)}"


def _token_request(
    http: httpx.Client, endpoints: Endpoints, client_id: str, client_secret: str | None, body: dict[str, str]
) -> Tokens:
    payload = {**body, "client_id": client_id}
    if client_secret:
        payload["client_secret"] = client_secret
    if endpoints.resource:
        payload["resource"] = endpoints.resource
    response = (
        http.post(endpoints.token_url, json=payload)
        if endpoints.exchange_format == "json"
        else http.post(endpoints.token_url, data=payload)
    )
    data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    # Feishu wraps errors in a 200 with a non-zero "code".
    if response.status_code >= 400 or data.get("error") or (isinstance(data.get("code"), int) and data["code"] != 0):
        if response.status_code >= 500:
            raise ApiError(502, "UPSTREAM_UNAVAILABLE", "The authorization server is not available.")
        raise OAuthFailure(str(data.get("error") or data.get("code") or response.status_code))
    expires_in = data.get("expires_in")
    return Tokens(
        access_token=str(data["access_token"]),
        refresh_token=data.get("refresh_token"),
        expires_at=utcnow() + timedelta(seconds=int(expires_in)) if expires_in else None,
        scopes=str(data.get("scope") or "").split(),
        account=data.get("account") or data.get("open_id") or data.get("sub"),
    )


def exchange_code(
    http: httpx.Client,
    endpoints: Endpoints,
    client_id: str,
    client_secret: str | None,
    code: str,
    verifier: str,
    redirect_uri: str,
) -> Tokens:
    return _token_request(
        http,
        endpoints,
        client_id,
        client_secret,
        {"grant_type": "authorization_code", "code": code, "code_verifier": verifier, "redirect_uri": redirect_uri},
    )


def _credential(session: Session, connection: Connection, kind: str, *, lock: bool = False) -> Credential | None:
    query = select(Credential).where(Credential.connection_id == connection.id, Credential.kind == kind)
    if lock:
        query = query.with_for_update()
    return session.execute(query).scalar_one_or_none()


def store_tokens(session: Session, vault: Vault, connection: Connection, tokens: Tokens) -> None:
    for kind, value, not_after in (
        ("oauth_access", tokens.access_token, tokens.expires_at),
        ("oauth_refresh", tokens.refresh_token, None),
    ):
        if not value:
            continue
        credential = _credential(session, connection, kind)
        if credential is None:
            credential = Credential(
                id=ids.uuid7(),
                tenant_id=connection.tenant_id,
                connection_id=connection.id,
                usage_class="tool",
                kind=kind,
            )
            session.add(credential)
            session.flush()
        vault.put(session, credential, value, not_after=not_after)


def _usable(session: Session, vault: Vault, connection: Connection) -> str | None:
    access = _credential(session, connection, "oauth_access")
    if access is None or access.active_version_id is None:
        return None
    version = session.get(SecretVersion, access.active_version_id)
    if version is None or version.state != "active":
        return None
    if version.not_after is not None and version.not_after - REFRESH_MARGIN <= utcnow():
        return None
    return vault.read(session, access)[0]


def access_token(
    session: Session, vault: Vault, connection: Connection, connector: Connector, http: httpx.Client
) -> str:
    """A valid access token for the connection, refreshing it first when it is about to expire.

    Raises OAuthFailure when the user has to authorize again (no refresh token, or the provider refused it); the
    caller marks the connection ``needs_auth``.
    """
    token = _usable(session, vault, connection)
    if token is not None:
        return token
    refresh = _credential(session, connection, "oauth_refresh", lock=True)  # single flight: waits for a refresher
    session.expire_all()
    token = _usable(session, vault, connection)
    if token is not None:
        return token  # another process refreshed while this one waited
    if refresh is None or refresh.active_version_id is None:
        raise OAuthFailure("no_refresh_token")
    installation = session.get(ConnectorInstallation, (connection.tenant_id, connector.id))
    config = dict(installation.config) if installation else {}
    endpoints = endpoints_for(connector, config, http)
    tokens = _token_request(
        http,
        endpoints,
        str(config.get("client_id") or ""),
        installation_secret(session, vault, connection.tenant_id, connector.id),
        {"grant_type": "refresh_token", "refresh_token": vault.read(session, refresh)[0]},
    )
    store_tokens(session, vault, connection, tokens)
    connection.last_refresh_at = utcnow()
    return tokens.access_token
