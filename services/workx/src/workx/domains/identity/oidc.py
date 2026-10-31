"""OpenID Connect relying party: authorization code flow with PKCE (S256), nonce, and ID-token validation
against the issuer's JWKS (Part 8 J1, Part 9 §3). Works with Keycloak or any compliant issuer."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from joserfc import jwt
from joserfc.errors import InvalidKeyIdError, JoseError
from joserfc.jwk import KeySet

from workx.core.errors import ApiError
from workx.core.settings import OidcSettings

_ALGORITHMS = ["RS256", "ES256", "PS256"]
_CACHE_SECONDS = 300


class OidcError(Exception):
    """The identity provider response could not be trusted. ``code`` is shown on the sign-in page."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


@dataclass
class OidcProvider:
    settings: OidcSettings
    http: httpx.Client
    _metadata: dict[str, Any] | None = None
    _jwks: Any = None
    _fetched_at: float = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.settings.issuer)

    def metadata(self) -> dict[str, Any]:
        if not self.configured:
            raise ApiError(503, "IDENTITY_PROVIDER_NOT_CONFIGURED", "Sign-in is not configured for this deployment.")
        if self._metadata is None or time.monotonic() - self._fetched_at > _CACHE_SECONDS:
            issuer = self.settings.issuer.rstrip("/")
            if not issuer.startswith("https://") and not self.settings.allow_insecure_issuer:
                raise ApiError(503, "IDENTITY_PROVIDER_INSECURE", "The identity provider must use HTTPS.")
            try:
                response = self.http.get(f"{issuer}/.well-known/openid-configuration", timeout=10)
                response.raise_for_status()
                metadata = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise ApiError(503, "UPSTREAM_UNAVAILABLE", "The identity provider is not reachable.") from exc
            if metadata.get("issuer", "").rstrip("/") != issuer:
                raise ApiError(503, "IDENTITY_PROVIDER_MISMATCH", "Identity provider metadata does not match.")
            self._metadata = metadata
            self._jwks = None
            self._fetched_at = time.monotonic()
        return self._metadata

    def _keys(self, refresh: bool = False) -> KeySet:
        if self._jwks is None or refresh:
            try:
                response = self.http.get(self.metadata()["jwks_uri"], timeout=10)
                response.raise_for_status()
                self._jwks = KeySet.import_key_set(response.json())
            except (httpx.HTTPError, ValueError) as exc:
                raise OidcError("idp_unreachable", "Signing keys not available") from exc
        keys: KeySet = self._jwks
        return keys

    def authorization_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        nonce: str,
        code_challenge: str,
        intent: str,
        idp_hint: str | None = None,
    ) -> str:
        params = {
            "response_type": "code",
            "client_id": self.settings.client_id,
            "redirect_uri": redirect_uri,
            "scope": self.settings.scopes,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if intent == "signup":
            # Keycloak and others honor prompt=create for registration (OIDC Prompt Create spec).
            params["prompt"] = "create"
        if idp_hint:
            # Keycloak goes straight to the brokered identity provider (organization SSO).
            params["kc_idp_hint"] = idp_hint
        return f"{self.metadata()['authorization_endpoint']}?{urlencode(params)}"

    def exchange_code(self, *, code: str, code_verifier: str, redirect_uri: str) -> dict[str, Any]:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
            "client_id": self.settings.client_id,
        }
        secret = self.settings.client_secret.get_secret_value()
        # Confidential client (Keycloak default): client_secret_basic. Public client: client_id in the body only.
        try:
            if secret:
                auth = httpx.BasicAuth(self.settings.client_id, secret)
                response = self.http.post(self.metadata()["token_endpoint"], data=data, auth=auth, timeout=15)
            else:
                response = self.http.post(self.metadata()["token_endpoint"], data=data, timeout=15)
        except httpx.HTTPError as exc:
            raise OidcError("idp_unreachable", "Token endpoint not reachable") from exc
        if response.status_code != 200:
            raise OidcError("token_exchange_failed", f"Token endpoint returned {response.status_code}")
        tokens: dict[str, Any] = response.json()
        if "id_token" not in tokens:
            raise OidcError("token_exchange_failed", "No ID token returned")
        return tokens

    def verify_id_token(self, id_token: str, *, nonce: str) -> dict[str, Any]:
        registry = jwt.JWTClaimsRegistry(
            leeway=60,
            iss={"essential": True, "value": self.metadata()["issuer"]},
            aud={"essential": True, "value": self.settings.client_id},
            sub={"essential": True},
            exp={"essential": True},
            nonce={"essential": True, "value": nonce},
        )
        for refresh in (False, True):
            try:
                token = jwt.decode(id_token, self._keys(refresh=refresh), algorithms=_ALGORITHMS)
                registry.validate(token.claims)
                return dict(token.claims)
            except InvalidKeyIdError as exc:
                # An unknown key id can mean the issuer rotated keys: refresh the JWKS once.
                if not refresh:
                    continue
                raise OidcError("invalid_id_token", "ID token signed with an unknown key") from exc
            except (JoseError, ValueError) as exc:
                raise OidcError("invalid_id_token", f"ID token rejected: {exc}") from exc
        raise OidcError("invalid_id_token", "ID token rejected")

    def end_session_url(self, *, id_token_hint: str | None, post_logout_redirect_uri: str) -> str | None:
        endpoint = self.metadata().get("end_session_endpoint") if self.configured else None
        if not endpoint:
            return None
        params = {"post_logout_redirect_uri": post_logout_redirect_uri, "client_id": self.settings.client_id}
        if id_token_hint:
            params["id_token_hint"] = id_token_hint
        return f"{endpoint}?{urlencode(params)}"
