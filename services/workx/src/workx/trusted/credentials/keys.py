"""KeyProvider: wraps and unwraps per-version data keys (Part 6 §3.2, decision 12).

* ``LocalKeyProvider``: AES-256-GCM with a key derived per ``key_ref`` (HKDF) from one master key. Development
  and single-node self-hosting.
* ``OpenBaoTransitProvider``: OpenBao/Vault Transit encrypt/decrypt; the KEK never leaves OpenBao.
* ``AwsKmsProvider``: AWS KMS Encrypt/Decrypt with an encryption context per ``key_ref``.

Only the trusted processes construct a KeyProvider.
"""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import parse_qs, urlparse

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from workx.core.settings import TrustedSettings


class KeyProvider(Protocol):
    name: str

    def wrap(self, key_ref: str, dek: bytes) -> tuple[bytes, int]: ...
    def unwrap(self, key_ref: str, wrapped: bytes, key_version: int) -> bytes: ...


@dataclass
class LocalKeyProvider:
    master_key: bytes
    name: str = "local"

    def _kek(self, key_ref: str) -> bytes:
        return HKDF(algorithm=SHA256(), length=32, salt=b"workx-kek", info=key_ref.encode()).derive(self.master_key)

    def wrap(self, key_ref: str, dek: bytes) -> tuple[bytes, int]:
        nonce = os.urandom(12)
        return nonce + AESGCM(self._kek(key_ref)).encrypt(nonce, dek, key_ref.encode()), 1

    def unwrap(self, key_ref: str, wrapped: bytes, key_version: int) -> bytes:
        return AESGCM(self._kek(key_ref)).decrypt(wrapped[:12], wrapped[12:], key_ref.encode())


@dataclass
class OpenBaoTransitProvider:
    base_url: str
    token: str
    mount: str = "transit"
    name: str = "openbao"
    http: httpx.Client = field(default_factory=lambda: httpx.Client(timeout=10))

    def _key(self, key_ref: str) -> str:
        return key_ref.replace("/", "-")

    def wrap(self, key_ref: str, dek: bytes) -> tuple[bytes, int]:
        response = self.http.post(
            f"{self.base_url}/v1/{self.mount}/encrypt/{self._key(key_ref)}",
            headers={"X-Vault-Token": self.token},
            json={"plaintext": base64.b64encode(dek).decode()},
        )
        response.raise_for_status()
        ciphertext = response.json()["data"]["ciphertext"]  # "vault:v<N>:<b64>"
        return ciphertext.encode(), int(ciphertext.split(":")[1][1:])

    def unwrap(self, key_ref: str, wrapped: bytes, key_version: int) -> bytes:
        response = self.http.post(
            f"{self.base_url}/v1/{self.mount}/decrypt/{self._key(key_ref)}",
            headers={"X-Vault-Token": self.token},
            json={"ciphertext": wrapped.decode()},
        )
        response.raise_for_status()
        return base64.b64decode(response.json()["data"]["plaintext"])


@dataclass
class AwsKmsProvider:
    key_arn: str
    name: str = "awskms"
    client: Any = None

    def __post_init__(self) -> None:
        if self.client is None:
            import boto3

            self.client = boto3.client("kms")

    def wrap(self, key_ref: str, dek: bytes) -> tuple[bytes, int]:
        result = self.client.encrypt(KeyId=self.key_arn, Plaintext=dek, EncryptionContext={"key_ref": key_ref})
        return bytes(result["CiphertextBlob"]), 1

    def unwrap(self, key_ref: str, wrapped: bytes, key_version: int) -> bytes:
        result = self.client.decrypt(CiphertextBlob=wrapped, EncryptionContext={"key_ref": key_ref})
        return bytes(result["Plaintext"])


def from_settings(settings: TrustedSettings) -> KeyProvider:
    spec = settings.key_provider
    if spec == "local":
        raw = settings.local_master_key.get_secret_value()
        if not raw:
            if settings.is_production:
                raise RuntimeError("WORKX_LOCAL_MASTER_KEY is required")
            # Development and tests only: derived from the (non-production) secret key.
            raw = settings.secret_key.get_secret_value()
        return LocalKeyProvider(hashlib.sha256(raw.encode()).digest())
    if spec.startswith("openbao:"):
        parsed = urlparse(spec.removeprefix("openbao:"))
        mount = parse_qs(parsed.query).get("mount", ["transit"])[0]
        return OpenBaoTransitProvider(
            f"{parsed.scheme}://{parsed.netloc}", settings.openbao_token.get_secret_value(), mount
        )
    if spec.startswith("awskms:"):
        return AwsKmsProvider(spec.removeprefix("awskms:"))
    raise ValueError("WORKX_KEY_PROVIDER must be local, openbao:<url> or awskms:<arn>")
