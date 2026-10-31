"""Envelope encryption for secret versions (Part 6 §3.2-§3.3).

Each version has its own random 256-bit data key; AES-256-GCM with associated data
``tenant|credential|version|usage_class`` so a ciphertext cannot be moved to another row. The data key is wrapped
by the KeyProvider under a per-tenant key reference. Plaintext exists only in trusted-process memory.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from workx.core import ids
from workx.core.errors import ApiError
from workx.core.orm import utcnow
from workx.domains.connections.models import Credential
from workx.trusted.credentials.keys import KeyProvider
from workx.trusted.credentials.models import SecretVersion

RETIRING_GRACE = timedelta(minutes=10)


def key_ref(tenant_id: uuid.UUID) -> str:
    return f"kek/t/{tenant_id}"


def _aad(tenant_id: uuid.UUID, credential_id: uuid.UUID, version_no: int, usage_class: str) -> bytes:
    return f"{tenant_id}|{credential_id}|{version_no}|{usage_class}".encode()


def seal(keys: KeyProvider, ref: str, plaintext: bytes, aad: bytes) -> tuple[bytes, bytes, bytes, int]:
    dek = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    ciphertext = AESGCM(dek).encrypt(nonce, plaintext, aad)
    wrapped, version = keys.wrap(ref, dek)
    return ciphertext, nonce, wrapped, version


def open_sealed(
    keys: KeyProvider, ref: str, ciphertext: bytes, nonce: bytes, wrapped: bytes, key_version: int, aad: bytes
) -> bytes:
    dek = keys.unwrap(ref, wrapped, key_version)
    return AESGCM(dek).decrypt(nonce, ciphertext, aad)


@dataclass(frozen=True)
class Vault:
    keys: KeyProvider
    fingerprint_key: bytes

    def put(
        self, session: Session, credential: Credential, plaintext: str, *, not_after: datetime | None = None
    ) -> SecretVersion:
        """Writes a new active version; the previous one is kept 'retiring' for in-flight calls."""
        locked = session.get(Credential, credential.id, with_for_update=True)
        assert locked is not None
        number = (
            session.execute(
                select(func.coalesce(func.max(SecretVersion.version_no), 0)).where(
                    SecretVersion.credential_id == locked.id
                )
            ).scalar_one()
            + 1
        )
        ref = key_ref(locked.tenant_id)
        ciphertext, nonce, wrapped, key_version = seal(
            self.keys, ref, plaintext.encode(), _aad(locked.tenant_id, locked.id, number, locked.usage_class)
        )
        version = SecretVersion(
            id=ids.uuid7(),
            tenant_id=locked.tenant_id,
            credential_id=locked.id,
            version_no=number,
            ciphertext=ciphertext,
            nonce=nonce,
            wrapped_dek=wrapped,
            key_ref=ref,
            key_version=key_version,
            fingerprint=hmac.new(self.fingerprint_key, plaintext.encode(), hashlib.sha256).digest(),
            not_after=not_after,
            state="active",
            created_at=utcnow(),
        )
        session.add(version)
        if locked.active_version_id is not None:
            previous = session.get(SecretVersion, locked.active_version_id)
            if previous is not None and previous.state == "active":
                previous.state, previous.retired_at = "retiring", utcnow()
        session.flush()
        locked.active_version_id = version.id
        locked.row_version += 1
        return version

    def read(self, session: Session, credential: Credential) -> tuple[str, SecretVersion]:
        if credential.active_version_id is None:
            raise ApiError(409, "NEEDS_AUTH", "This connection has no usable credential.")
        version = session.get(SecretVersion, credential.active_version_id)
        if version is None or version.state != "active":
            raise ApiError(409, "NEEDS_AUTH", "This connection has no usable credential.")
        plaintext = open_sealed(
            self.keys,
            version.key_ref,
            version.ciphertext,
            version.nonce,
            version.wrapped_dek,
            version.key_version,
            _aad(credential.tenant_id, credential.id, version.version_no, credential.usage_class),
        )
        return plaintext.decode(), version

    def destroy_retired(self, session: Session, credential_id: uuid.UUID, *, now: datetime | None = None) -> int:
        """Crypto-shreds versions retired longer than the grace period (ciphertext and wrapped key overwritten)."""
        moment = now or utcnow()
        rows = (
            session.execute(
                select(SecretVersion).where(
                    SecretVersion.credential_id == credential_id,
                    SecretVersion.state == "retiring",
                    SecretVersion.retired_at < moment - RETIRING_GRACE,
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            row.state, row.ciphertext, row.wrapped_dek, row.nonce = "destroyed", b"", b"", b""
        return len(rows)

    def destroy_all(self, session: Session, credential_id: uuid.UUID) -> int:
        rows = (
            session.execute(
                select(SecretVersion).where(
                    SecretVersion.credential_id == credential_id, SecretVersion.state != "destroyed"
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            row.state, row.ciphertext, row.wrapped_dek, row.nonce, row.retired_at = "destroyed", b"", b"", b"", utcnow()
        return len(rows)
