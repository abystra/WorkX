from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from workx.core.orm import Base


class SecretVersion(Base):
    __tablename__ = "secret_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    credential_id: Mapped[uuid.UUID]
    version_no: Mapped[int]
    ciphertext: Mapped[bytes]
    nonce: Mapped[bytes]
    wrapped_dek: Mapped[bytes]
    key_ref: Mapped[str]
    key_version: Mapped[int]
    fingerprint: Mapped[bytes]
    not_after: Mapped[datetime | None]
    state: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    retired_at: Mapped[datetime | None]


class OAuthTransaction(Base):
    __tablename__ = "oauth_transactions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    connector_id: Mapped[str]
    connection_id: Mapped[uuid.UUID | None]
    owner_scope: Mapped[str]
    initiator_membership_id: Mapped[uuid.UUID]
    state_hash: Mapped[bytes]
    verifier_ciphertext: Mapped[bytes]
    verifier_nonce: Mapped[bytes]
    verifier_wrapped_dek: Mapped[bytes]
    key_ref: Mapped[str]
    key_version: Mapped[int]
    redirect_uri: Mapped[str]
    client_id: Mapped[str] = mapped_column(server_default="")
    return_to: Mapped[str]
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text))
    expires_at: Mapped[datetime]
    consumed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
