"""Broker service (trusted): the only writer of secret versions (Part 6 §3.3).

The API forwards a secret it receives from a user straight here (never storing or logging it) and gets back
metadata only. Internal calls are authenticated with ``WORKX_BROKER_TOKEN`` (mTLS in production).
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime
from typing import Literal

from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from workx.core import ids
from workx.core.db import Database
from workx.core.errors import ApiError
from workx.core.settings import TrustedSettings
from workx.domains.audit import service as audit
from workx.domains.connections.models import Connection, Credential
from workx.trusted.credentials import keys
from workx.trusted.credentials.vault import Vault


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


class SecretOut(BaseModel):
    credential_id: str
    version: int
    fingerprint: str


def vault_for(settings: TrustedSettings) -> Vault:
    fingerprint_key = hashlib.sha256(b"fingerprint|" + settings.secret_key.get_secret_value().encode()).digest()
    return Vault(keys.from_settings(settings), fingerprint_key)


def create_broker_app(settings: TrustedSettings | None = None, db: Database | None = None) -> FastAPI:
    settings = settings or TrustedSettings()
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

    return app
