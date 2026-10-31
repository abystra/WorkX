"""Opaque bearer values and their digests. Only digests are stored; HMAC-derived values are recomputed."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets


def random_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def digest(value: str) -> bytes:
    return hashlib.sha256(value.encode()).digest()


def derive(secret_key: str, purpose: str, value: str | bytes) -> str:
    """HMAC-SHA256(secret, purpose || value), base64url without padding."""
    data = value.encode() if isinstance(value, str) else value
    mac = hmac.new(secret_key.encode(), purpose.encode() + b"\x00" + data, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode()


def pkce_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def constant_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
