from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import REAL, Text
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from workx.core.orm import Base


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    file_id: Mapped[uuid.UUID]
    name: Mapped[str]
    owner_membership_id: Mapped[uuid.UUID]
    status: Mapped[str] = mapped_column(server_default="processing")
    error_code: Mapped[str | None]
    published_revision_id: Mapped[uuid.UUID | None]
    deleted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(server_default="now()")


class KnowledgeRevision(Base):
    __tablename__ = "knowledge_revisions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    source_id: Mapped[uuid.UUID]
    revision_no: Mapped[int]
    file_version_id: Mapped[uuid.UUID]
    state: Mapped[str] = mapped_column(server_default="building")
    stage: Mapped[str] = mapped_column(server_default="queued")
    completeness: Mapped[str] = mapped_column(server_default="complete")
    parser: Mapped[str | None]
    error_code: Mapped[str | None]
    error_detail: Mapped[str | None]
    chunk_count: Mapped[int] = mapped_column(server_default="0")
    embedding_profile: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    published_at: Mapped[datetime | None]


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    source_id: Mapped[uuid.UUID]
    revision_id: Mapped[uuid.UUID]
    ordinal: Mapped[int]
    chunk_key: Mapped[str]
    text: Mapped[str]
    heading_path: Mapped[str] = mapped_column(server_default="")
    locator: Mapped[dict[str, Any]] = mapped_column(server_default="{}")
    locator_quality: Mapped[str] = mapped_column(server_default="exact")
    content_flags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    tsv: Mapped[Any] = mapped_column(TSVECTOR)
    embedding: Mapped[list[float] | None] = mapped_column(ARRAY(REAL))
    embedding_profile: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")


class RetrievalLog(Base):
    __tablename__ = "retrieval_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID]
    task_id: Mapped[uuid.UUID | None]
    attempt_id: Mapped[uuid.UUID | None]
    membership_id: Mapped[uuid.UUID]
    query: Mapped[str]
    chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)))
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
