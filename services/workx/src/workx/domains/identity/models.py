from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from workx.core.orm import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    idp_issuer: Mapped[str]
    idp_subject: Mapped[str]
    primary_email: Mapped[str] = mapped_column(String)
    email_verified_at: Mapped[datetime]
    display_name: Mapped[str]
    locale: Mapped[str] = mapped_column(server_default="en")
    status: Mapped[str] = mapped_column(server_default="active")
    notifications_enabled: Mapped[bool] = mapped_column(server_default="true")
    last_tenant_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(server_default="now()")


class LoginSession(Base):
    __tablename__ = "login_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    session_hash: Mapped[bytes]
    auth_strength: Mapped[str] = mapped_column(server_default="password")
    idp_sid: Mapped[str | None]
    id_token_hint: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    last_seen_at: Mapped[datetime] = mapped_column(server_default="now()")
    expires_at: Mapped[datetime]
    absolute_expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    ip_hash: Mapped[bytes | None]
    user_agent: Mapped[str | None]


class OidcLoginTransaction(Base):
    __tablename__ = "oidc_login_transactions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    state_hash: Mapped[bytes]
    browser_binding_hash: Mapped[bytes]
    code_verifier: Mapped[str]
    nonce: Mapped[str]
    intent: Mapped[str]
    return_to: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    expires_at: Mapped[datetime]
    consumed_at: Mapped[datetime | None]
