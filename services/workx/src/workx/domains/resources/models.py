from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from workx.core.orm import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    name: Mapped[str]
    description: Mapped[str] = mapped_column(server_default="")
    color: Mapped[str | None]
    context_md: Mapped[str] = mapped_column(server_default="")
    owner_membership_id: Mapped[uuid.UUID]
    visibility: Mapped[str] = mapped_column(server_default="private")
    row_version: Mapped[int] = mapped_column(server_default="1")
    deleted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(server_default="now()")


class ProjectMember(Base):
    __tablename__ = "project_members"

    tenant_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    membership_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    project_role: Mapped[str] = mapped_column(server_default="member")
    status: Mapped[str] = mapped_column(server_default="active")
    created_at: Mapped[datetime] = mapped_column(server_default="now()")


class ProjectAgent(Base):
    __tablename__ = "project_agents"

    tenant_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(server_default="now()")


class File(Base):
    __tablename__ = "files"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    name: Mapped[str]
    kind: Mapped[str] = mapped_column(server_default="doc")
    media_type: Mapped[str] = mapped_column(server_default="text/markdown")
    project_id: Mapped[uuid.UUID | None]
    source_task_id: Mapped[uuid.UUID | None]
    owner_membership_id: Mapped[uuid.UUID]
    visibility: Mapped[str] = mapped_column(server_default="private")
    current_version_id: Mapped[uuid.UUID | None]
    deleted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(server_default="now()")


class FileVersion(Base):
    __tablename__ = "file_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    file_id: Mapped[uuid.UUID]
    version_no: Mapped[int]
    size_bytes: Mapped[int] = mapped_column(server_default="0")
    sha256: Mapped[bytes | None]
    storage_key: Mapped[str | None]
    text_content: Mapped[str | None]
    created_by_membership_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")


class Automation(Base):
    __tablename__ = "automations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    name: Mapped[str]
    description: Mapped[str] = mapped_column(server_default="")
    schedule: Mapped[str]
    timezone: Mapped[str] = mapped_column(server_default="UTC")
    agent_id: Mapped[uuid.UUID | None]
    prompt: Mapped[str] = mapped_column(server_default="")
    enabled: Mapped[bool] = mapped_column(server_default="true")
    next_run_at: Mapped[datetime | None]
    last_run_at: Mapped[datetime | None]
    owner_membership_id: Mapped[uuid.UUID]
    visibility: Mapped[str] = mapped_column(server_default="private")
    deleted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(server_default="now()")


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    name: Mapped[str]
    problem: Mapped[str]
    role: Mapped[str] = mapped_column(server_default="")
    input: Mapped[str] = mapped_column(server_default="")
    output: Mapped[str] = mapped_column(server_default="")
    ecosystems: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    owner_membership_id: Mapped[uuid.UUID]
    visibility: Mapped[str] = mapped_column(server_default="private")
    deleted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(server_default="now()")
