from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from workx.core.orm import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    slug: Mapped[str]
    type: Mapped[str]
    name: Mapped[str]
    owner_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(server_default="active")
    plan_id: Mapped[str] = mapped_column(server_default="free")
    region_cell: Mapped[str] = mapped_column(server_default="default")
    authz_epoch: Mapped[int] = mapped_column(server_default="1")
    settings: Mapped[dict[str, Any]] = mapped_column(server_default="{}")
    row_version: Mapped[int] = mapped_column(server_default="1")
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(server_default="now()")


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str]
    parent_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(server_default="now()")


class Membership(Base):
    __tablename__ = "memberships"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str]
    status: Mapped[str] = mapped_column(server_default="active")
    display_name: Mapped[str | None]
    department_id: Mapped[uuid.UUID | None]
    preferences: Mapped[dict[str, Any]] = mapped_column(server_default="{}")
    authz_epoch: Mapped[int] = mapped_column(server_default="1")
    row_version: Mapped[int] = mapped_column(server_default="1")
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(server_default="now()")


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    email_normalized: Mapped[str] = mapped_column(String)
    role: Mapped[str]
    token_digest: Mapped[bytes]
    status: Mapped[str] = mapped_column(server_default="pending")
    expires_at: Mapped[datetime]
    invited_by_membership_id: Mapped[uuid.UUID]
    consumed_by_user_id: Mapped[uuid.UUID | None]
    accepted_membership_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(server_default="now()")
