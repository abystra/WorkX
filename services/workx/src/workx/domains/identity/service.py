"""Sign-in flow and login sessions (Part 3 §1, Part 8 J1, Part 10 §3).

The browser never sees tokens from the identity provider: the API runs the code flow, then issues its own
opaque session cookie. Only SHA-256 digests of session values are stored.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from workx.core import ids
from workx.core.errors import ApiError
from workx.core.orm import utcnow
from workx.core.settings import ApiSettings
from workx.domains.audit import service as audit
from workx.domains.identity import tokens
from workx.domains.identity.models import LoginSession, OidcLoginTransaction, User
from workx.domains.identity.oidc import OidcError, OidcProvider
from workx.domains.tenancy import service as tenancy

log = logging.getLogger("workx.identity")
LOGIN_TRANSACTION_TTL = timedelta(minutes=10)
SLIDE_INTERVAL = timedelta(minutes=1)


def safe_return_to(value: str | None) -> str:
    """Same-origin relative paths only (mirrors apps/web safeReturnTo)."""
    if value and value.startswith("/") and not value.startswith("//") and not value.startswith("/\\"):
        return value[:2000]
    return "/"


@dataclass(frozen=True)
class LoginStart:
    authorization_url: str
    browser_binding: str


def begin_login(
    session: Session, provider: OidcProvider, settings: ApiSettings, *, intent: str, return_to: str | None
) -> LoginStart:
    if intent not in ("login", "signup"):
        intent = "login"
    state, binding, verifier, nonce = (tokens.random_token() for _ in range(4))
    session.add(
        OidcLoginTransaction(
            id=ids.uuid7(),
            state_hash=tokens.digest(state),
            browser_binding_hash=tokens.digest(binding),
            code_verifier=verifier,
            nonce=nonce,
            intent=intent,
            return_to=safe_return_to(return_to),
            expires_at=utcnow() + LOGIN_TRANSACTION_TTL,
        )
    )
    url = provider.authorization_url(
        redirect_uri=callback_url(settings),
        state=state,
        nonce=nonce,
        code_challenge=tokens.pkce_challenge(verifier),
        intent=intent,
    )
    return LoginStart(url, binding)


def callback_url(settings: ApiSettings) -> str:
    return f"{settings.api_base_url.rstrip('/')}/api/v1/auth/callback"


def mark_consumed(session: Session, state: str) -> None:
    row = session.execute(
        select(OidcLoginTransaction).where(OidcLoginTransaction.state_hash == tokens.digest(state))
    ).scalar_one_or_none()
    if row is not None and row.consumed_at is None:
        row.consumed_at = utcnow()


@dataclass(frozen=True)
class LoginResult:
    user: User
    session_token: str
    return_to: str


def complete_login(
    session: Session,
    provider: OidcProvider,
    settings: ApiSettings,
    *,
    state: str,
    code: str,
    browser_binding: str | None,
    user_agent: str | None,
    client_ip: str | None,
) -> LoginResult:
    transaction = session.execute(
        select(OidcLoginTransaction).where(OidcLoginTransaction.state_hash == tokens.digest(state)).with_for_update()
    ).scalar_one_or_none()
    if transaction is None or transaction.consumed_at is not None or transaction.expires_at < utcnow():
        raise OidcError("login_expired", "Unknown, used or expired login state")
    # Single use, even when the rest of the callback fails.
    transaction.consumed_at = utcnow()
    session.flush()
    if not browser_binding or transaction.browser_binding_hash != tokens.digest(browser_binding):
        raise OidcError("login_expired", "Login was started in a different browser")
    token_set = provider.exchange_code(
        code=code, code_verifier=transaction.code_verifier, redirect_uri=callback_url(settings)
    )
    claims = provider.verify_id_token(token_set["id_token"], nonce=transaction.nonce)
    user = upsert_user(session, issuer=provider.metadata()["issuer"], claims=claims)
    tenancy.ensure_personal_tenant(session, user_id=user.id, display_name=user.display_name)
    raw = tokens.random_token()
    now = utcnow()
    login = LoginSession(
        id=ids.uuid7(),
        user_id=user.id,
        session_hash=tokens.digest(raw),
        auth_strength=str(claims.get("acr") or "password")[:64],
        idp_sid=claims.get("sid"),
        id_token_hint=token_set["id_token"],
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(days=settings.session_sliding_days),
        absolute_expires_at=now + timedelta(days=settings.session_absolute_days),
        ip_hash=tokens.digest(tokens.derive(settings.secret_key.get_secret_value(), "ip", client_ip or "")),
        user_agent=(user_agent or "")[:300] or None,
    )
    session.add(login)
    audit.record(session, "auth.login", actor_user_id=user.id, data={"intent": transaction.intent})
    return LoginResult(user, raw, transaction.return_to)


def upsert_user(session: Session, *, issuer: str, claims: dict[str, Any]) -> User:
    email = str(claims.get("email") or "").strip()
    if not email or claims.get("email_verified") is not True:
        # Tenants are provisioned only for verified email addresses (Part 8 J1).
        raise OidcError("email_not_verified", "Verify your email address with the identity provider first.")
    name = str(claims.get("name") or claims.get("preferred_username") or email.split("@")[0])[:80]
    user = session.execute(
        select(User).where(User.idp_issuer == issuer, User.idp_subject == str(claims["sub"]))
    ).scalar_one_or_none()
    if user is None:
        if session.execute(select(User.id).where(User.primary_email == email)).first():
            # One account per verified email (Part 3 §1). Linking a second identity is an explicit, later flow.
            raise OidcError("email_in_use", "This email already belongs to another WorkX account.")
        user = User(
            id=ids.uuid7(),
            idp_issuer=issuer,
            idp_subject=str(claims["sub"]),
            primary_email=email,
            email_verified_at=utcnow(),
            display_name=name,
            locale=str(claims.get("locale") or "en")[:10],
        )
        session.add(user)
        session.flush()
        audit.record(session, "user.signed_up", actor_user_id=user.id)
    else:
        if user.status != "active":
            raise OidcError("account_disabled", "This account is disabled.")
        user.primary_email = email
    return user


@dataclass(frozen=True)
class Principal:
    user: User
    login_session: LoginSession
    session_token: str

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id

    def recently_authenticated(self, minutes: int) -> bool:
        return self.login_session.created_at > utcnow() - timedelta(minutes=minutes)


def authenticate(session: Session, raw_token: str | None, settings: ApiSettings) -> Principal:
    if not raw_token:
        raise ApiError(401, "UNAUTHENTICATED", "Sign in to continue.")
    row = session.execute(
        select(LoginSession, User)
        .join(User, User.id == LoginSession.user_id)
        .where(LoginSession.session_hash == tokens.digest(raw_token))
    ).first()
    if row is None:
        raise ApiError(401, "UNAUTHENTICATED", "Sign in to continue.")
    login, user = row
    now = utcnow()
    if login.revoked_at is not None or user.status != "active":
        raise ApiError(401, "SESSION_REVOKED", "Your session was ended. Sign in again.")
    if login.expires_at <= now or login.absolute_expires_at <= now:
        raise ApiError(401, "UNAUTHENTICATED", "Your session expired. Sign in again.")
    if now - login.last_seen_at > SLIDE_INTERVAL:
        login.last_seen_at = now
        login.expires_at = min(now + timedelta(days=settings.session_sliding_days), login.absolute_expires_at)
    return Principal(user, login, raw_token)


def csrf_token(settings: ApiSettings, raw_session_token: str) -> str:
    return tokens.derive(settings.secret_key.get_secret_value(), "csrf", raw_session_token)


def revoke_session(session: Session, login: LoginSession, *, actor_user_id: uuid.UUID, reason: str) -> None:
    if login.revoked_at is None:
        login.revoked_at = utcnow()
        audit.record(
            session,
            "auth.session_revoked",
            actor_user_id=actor_user_id,
            target_type="login_session",
            target_id=login.id,
            data={"reason": reason},
        )


def revoke_all_sessions(session: Session, user_id: uuid.UUID, *, reason: str) -> int:
    result = session.execute(
        update(LoginSession)
        .where(LoginSession.user_id == user_id, LoginSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    audit.record(session, "auth.sessions_revoked", actor_user_id=user_id, data={"reason": reason})
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def active_sessions(session: Session, user_id: uuid.UUID) -> list[LoginSession]:
    now: datetime = utcnow()
    return list(
        session.execute(
            select(LoginSession)
            .where(LoginSession.user_id == user_id, LoginSession.revoked_at.is_(None), LoginSession.expires_at > now)
            .order_by(LoginSession.last_seen_at.desc())
        ).scalars()
    )
