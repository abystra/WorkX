"""Broker service (trusted): the only writer of secret versions (Part 6 §3.3).

The API forwards a secret it receives from a user straight here (never storing or logging it) and gets back
metadata only. Internal calls are authenticated with ``WORKX_BROKER_TOKEN`` (mTLS in production).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Literal

import httpx
from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from workx.core import ids
from workx.core.db import Database
from workx.core.errors import ApiError
from workx.core.orm import utcnow
from workx.core.settings import TrustedSettings
from workx.domains.audit import service as audit
from workx.domains.connections import catalog
from workx.domains.connections.models import Connection, ConnectorInstallation, Credential
from workx.domains.tenancy.models import Membership
from workx.platform import outbox
from workx.trusted.credentials import keys, oauth
from workx.trusted.credentials.models import OAuthTransaction
from workx.trusted.credentials.vault import Vault, open_sealed, seal

OAUTH_TRANSACTION_TTL = timedelta(minutes=10)


class SecretIn(BaseModel):
    tenant_id: uuid.UUID
    connection_id: uuid.UUID
    actor_membership_id: uuid.UUID
    kind: Literal["api_key", "app_secret", "oauth_refresh", "oauth_access"] = "api_key"
    usage_class: Literal["tool", "channel"] = "tool"
    value: str = Field(min_length=1, max_length=8192)
    not_after: datetime | None = None


class DestroyIn(BaseModel):
    tenant_id: uuid.UUID
    connection_id: uuid.UUID


class OAuthStartIn(BaseModel):
    tenant_id: uuid.UUID
    connection_id: uuid.UUID
    membership_id: uuid.UUID
    redirect_uri: str = Field(max_length=2000)
    return_to: str = Field(max_length=2000)


class OAuthCompleteIn(BaseModel):
    state: str = Field(max_length=200)
    code: str | None = Field(default=None, max_length=4000)
    error: str | None = Field(default=None, max_length=200)
    user_id: uuid.UUID


class InstallationSecretIn(BaseModel):
    tenant_id: uuid.UUID
    connector_id: str
    actor_membership_id: uuid.UUID
    value: str = Field(min_length=1, max_length=8192)


class SecretOut(BaseModel):
    credential_id: str
    version: int
    fingerprint: str


def vault_for(settings: TrustedSettings) -> Vault:
    fingerprint_key = hashlib.sha256(b"fingerprint|" + settings.secret_key.get_secret_value().encode()).digest()
    return Vault(keys.from_settings(settings), fingerprint_key)


def _state_hash(state: str) -> bytes:
    return hashlib.sha256(state.encode()).digest()


def create_broker_app(
    settings: TrustedSettings | None = None, db: Database | None = None, http: httpx.Client | None = None
) -> FastAPI:
    settings = settings or TrustedSettings()
    http = http or httpx.Client(timeout=15, follow_redirects=False)
    db = db or Database.connect(settings.broker_database_url)
    vault = vault_for(settings)
    app = FastAPI(title="WorkX Broker", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.vault = vault

    def check(token: str | None) -> None:
        if not token or not hmac.compare_digest(token, settings.broker_token.get_secret_value()):
            raise ApiError(401, "UNAUTHENTICATED", "Internal token required.")

    @app.exception_handler(ApiError)
    async def errors(_: object, exc: ApiError) -> JSONResponse:
        return JSONResponse({"code": exc.code, "detail": exc.detail}, status_code=exc.status)

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/internal/secrets")
    def put_secret(body: SecretIn, x_workx_internal_token: str | None = Header(default=None)) -> SecretOut:
        check(x_workx_internal_token)
        with db.transaction(tenant_id=body.tenant_id) as session:
            connection = session.get(Connection, body.connection_id, with_for_update=True)
            if connection is None or connection.status == "revoked":
                raise ApiError(404, "NOT_FOUND", "Unknown connection.")
            credential = session.query(Credential).filter_by(connection_id=connection.id, kind=body.kind).one_or_none()
            if credential is None:
                credential = Credential(
                    id=ids.uuid7(),
                    tenant_id=connection.tenant_id,
                    connection_id=connection.id,
                    usage_class=body.usage_class,
                    kind=body.kind,
                )
                session.add(credential)
                session.flush()
            version = vault.put(session, credential, body.value, not_after=body.not_after)
            if body.kind in ("api_key", "app_secret", "oauth_refresh"):
                connection.status, connection.last_error = "active", None
            audit.record(
                session,
                "credential.version_created",
                tenant_id=connection.tenant_id,
                actor_membership_id=body.actor_membership_id,
                target_type="connection",
                target_id=connection.id,
                data={"kind": body.kind, "version": version.version_no},
            )
            return SecretOut(
                credential_id=str(credential.id), version=version.version_no, fingerprint=version.fingerprint.hex()[:12]
            )

    @app.post("/internal/connections/destroy")
    def destroy(body: DestroyIn, x_workx_internal_token: str | None = Header(default=None)) -> dict[str, int]:
        """Crypto-shreds every secret version of a revoked connection (Part 6 §3.3)."""
        check(x_workx_internal_token)
        with db.transaction(tenant_id=body.tenant_id) as session:
            credentials = session.query(Credential).filter_by(connection_id=body.connection_id).all()
            destroyed = sum(vault.destroy_all(session, c.id) for c in credentials)
            for credential in credentials:
                credential.active_version_id = None
            audit.record(
                session,
                "credential.destroyed",
                tenant_id=body.tenant_id,
                target_type="connection",
                target_id=body.connection_id,
                data={"versions": destroyed},
            )
            return {"destroyed": destroyed}

    @app.post("/internal/installations/secret")
    def installation_secret(
        body: InstallationSecretIn, x_workx_internal_token: str | None = Header(default=None)
    ) -> dict[str, int]:
        """An OAuth connector's client secret, per workspace installation (never in installation config)."""
        check(x_workx_internal_token)
        with db.transaction(tenant_id=body.tenant_id) as session:
            if session.get(ConnectorInstallation, (body.tenant_id, body.connector_id)) is None:
                raise ApiError(404, "NOT_FOUND", "The connector is not installed.")
            version = oauth.put_installation_secret(session, vault, body.tenant_id, body.connector_id, body.value)
            audit.record(
                session,
                "connector.client_secret_set",
                tenant_id=body.tenant_id,
                actor_membership_id=body.actor_membership_id,
                data={"connector": body.connector_id, "version": version.version_no},
            )
            return {"version": version.version_no}

    @app.post("/internal/oauth/start")
    def oauth_start(body: OAuthStartIn, x_workx_internal_token: str | None = Header(default=None)) -> dict[str, str]:
        """Begins authorization code + PKCE for a member's connection; returns the provider's authorize URL."""
        check(x_workx_internal_token)
        with db.transaction(tenant_id=body.tenant_id) as session:
            connection = session.get(Connection, body.connection_id, with_for_update=True)
            if (
                connection is None
                or connection.status == "revoked"
                or connection.owner_membership_id != body.membership_id
            ):
                raise ApiError(404, "NOT_FOUND", "Unknown connection.")
            connector = catalog.get(connection.connector_id)
            installation = session.get(ConnectorInstallation, (body.tenant_id, connection.connector_id))
            if connector is None or connector.oauth is None or installation is None or not installation.enabled:
                raise ApiError(409, "CONNECTOR_NOT_INSTALLED", "This connector is not available in the workspace.")
            endpoints = oauth.endpoints_for(connector, dict(installation.config or {}), http)
            client_id = oauth.ensure_client(session, vault, installation, endpoints, body.redirect_uri, http)
            state = secrets.token_urlsafe(32)
            verifier, challenge = oauth.pkce_pair()
            transaction_id = ids.uuid7()
            ref = f"kek/t/{body.tenant_id}"
            ciphertext, nonce, wrapped, key_version = seal(
                vault.keys, ref, verifier.encode(), f"oauth|{transaction_id}".encode()
            )
            session.add(
                OAuthTransaction(
                    id=transaction_id,
                    tenant_id=body.tenant_id,
                    connector_id=connector.id,
                    connection_id=connection.id,
                    owner_scope=connection.owner_scope,
                    initiator_membership_id=body.membership_id,
                    state_hash=_state_hash(state),
                    verifier_ciphertext=ciphertext,
                    verifier_nonce=nonce,
                    verifier_wrapped_dek=wrapped,
                    key_ref=ref,
                    key_version=key_version,
                    redirect_uri=body.redirect_uri,
                    client_id=client_id,
                    return_to=body.return_to,
                    scopes=list(endpoints.scopes),
                    expires_at=utcnow() + OAUTH_TRANSACTION_TTL,
                )
            )
            return {"authorize_url": oauth.authorize_url(endpoints, client_id, body.redirect_uri, state, challenge)}

    @app.post("/internal/oauth/complete")
    def oauth_complete(
        body: OAuthCompleteIn, x_workx_internal_token: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """The provider redirected back: exchange the code (once) and store the tokens as secret versions."""
        check(x_workx_internal_token)
        digest = _state_hash(body.state)
        with db.transaction() as session:
            tenant_id = session.execute(text("SELECT workx_oauth_state_tenant(:h)"), {"h": digest}).scalar()
        if tenant_id is None:
            raise ApiError(400, "OAUTH_STATE_INVALID", "This authorization link is not valid.")
        with db.transaction(tenant_id=tenant_id) as session:
            transaction = session.execute(
                select(OAuthTransaction).where(OAuthTransaction.state_hash == digest).with_for_update()
            ).scalar_one()
            if transaction.consumed_at is not None or transaction.expires_at <= utcnow():
                raise ApiError(400, "OAUTH_STATE_INVALID", "This authorization link is not valid.")
            transaction.consumed_at = utcnow()  # single use, whatever happens next (committed below)
            member = session.get(Membership, transaction.initiator_membership_id)
            if member is None or member.user_id != body.user_id or member.status != "active":
                # Someone else's browser: the state is spent, the initiator starts again.
                return {"tenant_id": str(tenant_id), "return_to": "/", "status": "invalid"}
            result = {
                "tenant_id": str(tenant_id),
                "return_to": transaction.return_to,
                "connection_id": str(transaction.connection_id),
            }
            connection = session.get(Connection, transaction.connection_id, with_for_update=True)
            connector = catalog.get(transaction.connector_id)
            installation = session.get(ConnectorInstallation, (tenant_id, transaction.connector_id))
            if connection is None or connection.status == "revoked" or connector is None or installation is None:
                raise ApiError(400, "OAUTH_STATE_INVALID", "This authorization link is not valid.")
            if body.error or not body.code:
                connection.last_error = (body.error or "no_code")[:200]
                return {**result, "status": "denied"}
            verifier = open_sealed(
                vault.keys,
                transaction.key_ref,
                transaction.verifier_ciphertext,
                transaction.verifier_nonce,
                transaction.verifier_wrapped_dek,
                transaction.key_version,
                f"oauth|{transaction.id}".encode(),
            ).decode()
            endpoints = oauth.endpoints_for(connector, dict(installation.config or {}), http)
            try:
                tokens = oauth.exchange_code(
                    http,
                    endpoints,
                    transaction.client_id,
                    oauth.installation_secret(session, vault, tenant_id, connector.id),
                    body.code,
                    verifier,
                    transaction.redirect_uri,
                )
            except oauth.OAuthFailure as exc:
                connection.status, connection.last_error = "needs_auth", str(exc)[:200]
                return {**result, "status": "failed"}
            oauth.store_tokens(session, vault, connection, tokens)
            connection.status, connection.last_error = "active", None
            connection.external_account = tokens.account or connection.external_account
            connection.granted_scopes = tokens.scopes or list(transaction.scopes)
            connection.last_refresh_at = utcnow()
            outbox.emit(
                session,
                "connection.authorized",
                {
                    "tenant_id": str(tenant_id),
                    "connection_id": str(connection.id),
                    "connector_id": connector.id,
                    "membership_id": str(connection.owner_membership_id),
                },
                tenant_id=tenant_id,
            )
            audit.record(
                session,
                "connection.authorized",
                tenant_id=tenant_id,
                actor_user_id=body.user_id,
                actor_membership_id=member.id,
                target_type="connection",
                target_id=connection.id,
                data={"connector": connector.id, "scopes": connection.granted_scopes},
            )
            return {**result, "status": "authorized"}

    return app
