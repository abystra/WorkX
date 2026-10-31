from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from workx.core.orm import Base


class ResourceGrant(Base):
    __tablename__ = "resource_grants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    resource_type: Mapped[str]
    resource_id: Mapped[uuid.UUID]
    principal_type: Mapped[str]
    principal_id: Mapped[uuid.UUID]
    actions: Mapped[list[str]] = mapped_column(ARRAY(Text))
    granted_by_membership_id: Mapped[uuid.UUID | None]
    expires_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")


class ServicePrincipal(Base):
    __tablename__ = "service_principals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    kind: Mapped[str]
    ref_id: Mapped[uuid.UUID | None]
    status: Mapped[str] = mapped_column(server_default="active")
    allowed_actions: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
