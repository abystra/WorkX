"""J1 sign-in against the development OIDC issuer (same protocol as Keycloak), sessions, CSRF, revocation."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from tests.support.auth import error_of, sign_in, start_login, unique_email
from workx.core import ids
from workx.core.db import Database
from workx.core.orm import utcnow
from workx.domains.identity.models import LoginSession, User
from workx.domains.tenancy import service as tenancy
from workx.domains.tenancy.models import Membership, Tenant


def test_sign_in_provisions_user_and_personal_workspace(client: TestClient, oidc: TestClient) -> None:
    email = unique_email("alex")
    callback = start_login(client, oidc, email, return_to="/t/x/library")
    done = client.get(callback, follow_redirects=False)
    assert done.headers["location"] == "http://web.test/t/x/library"
    cookie = done.headers["set-cookie"]
    assert "workx_session=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    me = client.get("/api/v1/me").json()
    assert me["email"] == email and me["id"].startswith("usr_") and me["csrf_token"]
    tenants = client.get("/api/v1/me/tenants").json()
    assert [(t["type"], t["role"]) for t in tenants] == [("personal", "owner")]


def test_unsafe_return_to_is_ignored(client: TestClient, oidc: TestClient) -> None:
    done = client.get(start_login(client, oidc, unique_email(), return_to="//evil.example/x"), follow_redirects=False)
    assert done.headers["location"] == "http://web.test/"


def test_unverified_email_is_refused(client: TestClient, oidc: TestClient, owner_db: Database) -> None:
    email = "unverified-" + unique_email()
    done = client.get(start_login(client, oidc, email), follow_redirects=False)
    assert error_of(done.headers["location"]) == "email_not_verified"
    with owner_db.transaction() as session:
        assert session.execute(select(User).where(User.primary_email == email)).first() is None
    assert client.get("/api/v1/me").status_code == 401


def test_callback_state_is_single_use_and_browser_bound(new_client: Callable[[], TestClient], oidc: TestClient) -> None:
    browser = new_client()
    callback = start_login(browser, oidc, unique_email())
    attacker = new_client()  # no binding cookie: login CSRF / leaked link
    assert error_of(attacker.get(callback, follow_redirects=False).headers["location"]) == "login_expired"
    # The failed attempt consumed the state; the real browser cannot reuse it either.
    assert error_of(browser.get(callback, follow_redirects=False).headers["location"]) == "login_expired"


def test_idp_error_and_missing_code(client: TestClient) -> None:
    denied = client.get("/api/v1/auth/callback?error=access_denied&state=x", follow_redirects=False)
    assert error_of(denied.headers["location"]) == "access_denied"
    odd = client.get("/api/v1/auth/callback?error=<script>", follow_redirects=False)
    assert error_of(odd.headers["location"]) == "login_failed"


def test_csrf_and_origin_are_enforced(client: TestClient, oidc: TestClient) -> None:
    sign_in(client, oidc)
    token = client.headers.pop("X-WorkX-CSRF")
    assert client.patch("/api/v1/me", json={"name": "New"}).json()["code"] == "CSRF_FAILED"
    client.headers["X-WorkX-CSRF"] = token
    cross = client.patch("/api/v1/me", json={"name": "New"}, headers={"Origin": "https://evil.example"})
    assert cross.status_code == 403
    ok = client.patch(
        "/api/v1/me", json={"name": "  New   Name ", "locale": "zh-CN"}, headers={"Origin": "http://web.test"}
    )
    assert ok.status_code == 200 and ok.json()["name"] == "New Name" and ok.json()["locale"] == "zh-CN"


def test_logout_revokes_session(client: TestClient, oidc: TestClient) -> None:
    sign_in(client, oidc)
    cookie = client.cookies.get("workx_session")
    out = client.post("/api/v1/auth/logout")
    assert out.status_code == 200 and out.json()["end_session_url"].startswith("http://testserver/logout")
    client.cookies.set("workx_session", cookie or "")
    assert client.get("/api/v1/me").json()["code"] == "SESSION_REVOKED"


def test_list_and_revoke_other_sessions(new_client: Callable[[], TestClient], oidc: TestClient) -> None:
    email = unique_email()
    laptop, phone = new_client(), new_client()
    sign_in(laptop, oidc, email)
    sign_in(phone, oidc, email)
    sessions = laptop.get("/api/v1/me/sessions").json()
    assert len(sessions) == 2 and sum(s["current"] for s in sessions) == 1
    other = next(s for s in sessions if not s["current"])
    assert laptop.delete(f"/api/v1/me/sessions/{other['id']}").status_code == 204
    assert phone.get("/api/v1/me").json()["code"] == "SESSION_REVOKED"
    stranger = new_client()
    sign_in(stranger, oidc)
    assert stranger.delete(f"/api/v1/me/sessions/{sessions[0]['id']}").status_code == 404


def test_sessions_expire_and_slide(client: TestClient, oidc: TestClient, owner_db: Database) -> None:
    me = sign_in(client, oidc)
    user_id = ids.decode("user", me["id"])
    with owner_db.transaction() as session:
        session.execute(
            update(LoginSession)
            .where(LoginSession.user_id == user_id)
            .values(last_seen_at=utcnow() - timedelta(hours=1))
        )
    assert client.get("/api/v1/me").status_code == 200
    with owner_db.transaction() as session:
        login = session.execute(select(LoginSession).where(LoginSession.user_id == user_id)).scalar_one()
        assert login.last_seen_at > utcnow() - timedelta(minutes=1)
        login.absolute_expires_at = utcnow() - timedelta(seconds=1)
    assert client.get("/api/v1/me").json()["code"] == "UNAUTHENTICATED"


def test_fifty_parallel_first_logins_create_one_personal_tenant(db: Database, owner_db: Database) -> None:
    with owner_db.transaction() as session:
        user = User(
            id=ids.uuid7(),
            idp_issuer="http://testserver",
            idp_subject=unique_email(),
            primary_email=unique_email(),
            email_verified_at=utcnow(),
            display_name="Racer",
        )
        session.add(user)

    def provision(_: int) -> None:
        with db.transaction(principal_id=user.id) as session:
            tenancy.ensure_personal_tenant(session, user_id=user.id, display_name="Racer")

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(provision, range(50)))
    with owner_db.transaction() as session:
        tenants = session.execute(
            select(func.count()).select_from(Tenant).where(Tenant.owner_user_id == user.id, Tenant.type == "personal")
        ).scalar_one()
        members = session.execute(
            select(func.count()).select_from(Membership).join(Tenant).where(Tenant.owner_user_id == user.id)
        ).scalar_one()
    assert (tenants, members) == (1, 1)


def test_preferences_require_membership(client: TestClient, oidc: TestClient) -> None:
    sign_in(client, oidc)
    personal = client.get("/api/v1/me/tenants").json()[0]["id"]
    assert client.put("/api/v1/me/preferences", json={"last_tenant_id": personal}).status_code == 204
    assert client.get("/api/v1/me").json()["last_tenant_id"] == personal
    _, stranger_tenant = ids.new("tenant")
    assert client.put("/api/v1/me/preferences", json={"last_tenant_id": stranger_tenant}).status_code == 404


def test_personal_provisioning_survives_prepared_statements(db: Database, owner_db: Database) -> None:
    """psycopg prepares a statement after 5 executions; ON CONFLICT inference must still match the index."""
    for _ in range(8):
        with owner_db.transaction() as session:
            user = User(
                id=ids.uuid7(),
                idp_issuer="http://testserver",
                idp_subject=unique_email(),
                primary_email=unique_email(),
                email_verified_at=utcnow(),
                display_name="Prepared",
            )
            session.add(user)
        with db.transaction(principal_id=user.id) as session:
            tenancy.ensure_personal_tenant(session, user_id=user.id, display_name="Prepared")
            tenancy.ensure_personal_tenant(session, user_id=user.id, display_name="Prepared")
