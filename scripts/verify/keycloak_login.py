"""Real-service check for B-02: sign in through a running Keycloak with the WorkX realm.

Drives a browser-like client through API /auth/login → Keycloak login form → API /auth/callback, then
checks /me, the personal workspace, logout with RP-initiated end-session, and revocation.
See infra/keycloak/README.md for the exact setup. Exit code 0 means every step passed.
"""

from __future__ import annotations

import argparse
import html
import re
import sys

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="alex@example.com")
    parser.add_argument("--password", default="workx-dev-password")
    args = parser.parse_args()

    def step(name: str, ok: bool, detail: str = "") -> None:
        print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ': ' + detail}")
        if not ok:
            raise SystemExit(1)

    browser = httpx.Client(follow_redirects=False, timeout=20)
    start = browser.get(f"{args.api}/api/v1/auth/login", params={"return_to": "/verified"})
    step(
        "API redirects to Keycloak",
        start.status_code == 302 and "/protocol/openid-connect/auth" in start.headers["location"],
        f"{start.status_code} {start.headers.get('location')}",
    )
    step("PKCE S256 requested", "code_challenge_method=S256" in start.headers["location"])
    page = browser.get(start.headers["location"])
    match = re.search(r'<form[^>]+id="kc-form-login"[^>]+action="([^"]+)"', page.text)
    step("Keycloak login form shown", page.status_code == 200 and match is not None, str(page.status_code))
    assert match
    posted = browser.post(html.unescape(match.group(1)), data={"username": args.username, "password": args.password})
    step(
        "Keycloak redirects back to the API",
        posted.status_code == 302 and "/api/v1/auth/callback" in posted.headers.get("location", ""),
        f"{posted.status_code} {posted.headers.get('location')}",
    )
    done = browser.get(posted.headers["location"])
    step(
        "API sets the session and returns to the app",
        done.status_code == 302
        and done.headers["location"].endswith("/verified")
        and "error=" not in done.headers["location"],
        done.headers.get("location", ""),
    )
    me = browser.get(f"{args.api}/api/v1/me")
    step("/me returns the Keycloak user", me.status_code == 200 and me.json()["email"] == args.username, me.text)
    tenants = browser.get(f"{args.api}/api/v1/me/tenants").json()
    step("personal workspace provisioned", any(t["type"] == "personal" for t in tenants), str(tenants))
    out = browser.post(f"{args.api}/api/v1/auth/logout", headers={"X-WorkX-CSRF": me.json()["csrf_token"]})
    step(
        "logout returns Keycloak end-session URL",
        out.status_code == 200 and "/protocol/openid-connect/logout" in (out.json().get("end_session_url") or ""),
        out.text,
    )
    browser.cookies.set("workx_session", done.cookies.get("workx_session") or "")
    revoked = browser.get(f"{args.api}/api/v1/me")
    step("revoked session is rejected", revoked.status_code == 401, revoked.text)
    print("Keycloak sign-in verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
