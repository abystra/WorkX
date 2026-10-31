"""Knowledge sources and the ingestion pipeline (Part 7 §1, §5).

A source is made from a Library file and inherits that file's permissions (sharing the file shares its
knowledge). Each ingestion builds a new revision: scan → parse → chunk → embed → index → publish; publishing is
one UPDATE of ``published_revision_id``, so searches never see a half-built revision. Unchanged chunks reuse the
previous revision's embeddings.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from workx.core import ids
from workx.core.db import Database
from workx.core.errors import ApiError
from workx.core.orm import utcnow
from workx.domains.connections.models import Connection
from workx.domains.knowledge import chunk as chunking
from workx.domains.knowledge.embed import EmbeddingClient
from workx.domains.knowledge.models import KnowledgeChunk, KnowledgeRevision, KnowledgeSource
from workx.domains.knowledge.parse import Block, ParseFailure, ParseResult, parse
from workx.domains.knowledge.text import index_text
from workx.domains.resources import events
from workx.domains.resources.models import File, FileVersion
from workx.domains.tenancy.service import Actor
from workx.platform import outbox

log = logging.getLogger("workx.knowledge")
MAX_BYTES = 100 * 1024 * 1024


def create_or_refresh(session: Session, actor: Actor, file: File) -> KnowledgeSource:
    """Idempotent per file: an existing source is returned (re-ingested if the file changed or it failed)."""
    source = session.execute(
        select(KnowledgeSource)
        .where(KnowledgeSource.tenant_id == actor.tenant.id, KnowledgeSource.file_id == file.id)
        .where(KnowledgeSource.deleted_at.is_(None))
        .with_for_update()
    ).scalar_one_or_none()
    if source is None:
        source = KnowledgeSource(
            id=ids.uuid7(),
            tenant_id=actor.tenant.id,
            file_id=file.id,
            name=file.name,
            owner_membership_id=actor.membership.id,
            status="processing",
        )
        session.add(source)
        session.flush()
        start_revision(session, source, file)
        return source
    latest = (
        session.execute(
            select(KnowledgeRevision)
            .where(KnowledgeRevision.source_id == source.id)
            .order_by(KnowledgeRevision.revision_no.desc())
        )
        .scalars()
        .first()
    )
    if source.status == "failed" or latest is None or latest.file_version_id != file.current_version_id:
        start_revision(session, source, file)
    return source


def create_connector_source(session: Session, actor: Actor, connection: Connection, name: str) -> KnowledgeSource:
    """A member's own connected account as private knowledge (R2): synced now and then periodically."""
    source = session.execute(
        select(KnowledgeSource)
        .where(KnowledgeSource.tenant_id == actor.tenant.id, KnowledgeSource.connection_id == connection.id)
        .where(KnowledgeSource.deleted_at.is_(None))
        .with_for_update()
    ).scalar_one_or_none()
    if source is None:
        source = KnowledgeSource(
            id=ids.uuid7(),
            tenant_id=actor.tenant.id,
            kind="connector",
            file_id=None,
            connection_id=connection.id,
            name=name,
            owner_membership_id=actor.membership.id,
            status="processing",
        )
        session.add(source)
        session.flush()
    start_revision(session, source, None)
    return source


def start_revision(session: Session, source: KnowledgeSource, file: File | None) -> KnowledgeRevision:
    if source.kind == "file" and (file is None or file.current_version_id is None):
        raise ValueError("file has no content")
    number = (
        session.execute(
            select(func.coalesce(func.max(KnowledgeRevision.revision_no), 0)).where(
                KnowledgeRevision.source_id == source.id
            )
        ).scalar_one()
        + 1
    )
    revision = KnowledgeRevision(
        id=ids.uuid7(),
        tenant_id=source.tenant_id,
        source_id=source.id,
        revision_no=number,
        file_version_id=file.current_version_id if file else None,
    )
    session.add(revision)
    source.error_code = None
    if source.published_revision_id is None:
        source.status = "processing"  # a re-sync keeps the published revision searchable meanwhile
    if file is not None:
        source.name = file.name
    session.flush()
    outbox.emit(
        session,
        "knowledge.revision_requested",
        {"tenant_id": str(source.tenant_id), "revision_id": str(revision.id)},
        tenant_id=source.tenant_id,
    )
    events.publish(
        session,
        source.tenant_id,
        "knowledge.source.updated",
        {"source_id": ids.encode("knowledge_source", source.id), "status": "processing"},
    )
    return revision


@dataclass
class Services:
    db: Database
    objects: object  # ObjectStore
    embeddings: EmbeddingClient
    tika_url: str = ""
    broker: Any = None  # BrokerClient: documents of connector sources


def _stage(db: Database, tenant_id: uuid.UUID, revision_id: uuid.UUID, stage: str) -> None:
    with db.transaction(tenant_id=tenant_id) as session:
        session.execute(update(KnowledgeRevision).where(KnowledgeRevision.id == revision_id).values(stage=stage))


def _fail(db: Database, tenant_id: uuid.UUID, revision_id: uuid.UUID, code: str, detail: str) -> None:
    with db.transaction(tenant_id=tenant_id) as session:
        revision = session.get(KnowledgeRevision, revision_id, with_for_update=True)
        assert revision is not None
        revision.state, revision.error_code, revision.error_detail = "failed", code, detail[:500]
        source = session.get(KnowledgeSource, revision.source_id, with_for_update=True)
        assert source is not None
        # A source with an earlier published revision stays searchable on that revision.
        if source.published_revision_id is None:
            source.status, source.error_code = "failed", code
        events.publish(
            session,
            tenant_id,
            "knowledge.source.updated",
            {"source_id": ids.encode("knowledge_source", source.id), "status": source.status},
        )


def _document_blocks(documents: list[dict[str, Any]]) -> list[Block]:
    """Synced documents → blocks with a document locator (one heading per document)."""
    blocks: list[Block] = []
    for doc in documents:
        locator = {"document": doc["id"]}
        blocks.append(Block("heading", doc.get("title") or doc["id"], level=1, locator=locator))
        for part in re.split(r"\n\s*\n", str(doc.get("body") or "")):
            if part.strip():
                blocks.append(Block("paragraph", part.strip(), locator=locator))
    return blocks


def ingest(services: Services, tenant_id: uuid.UUID, revision_id: uuid.UUID) -> str:
    """Runs one revision through the pipeline. Safe to re-run: chunks of the revision are rebuilt."""
    from workx.domains.artifacts import service as artifacts

    db = services.db
    with db.transaction(tenant_id=tenant_id) as session:
        revision = session.get(KnowledgeRevision, revision_id)
        if revision is None or revision.state != "building":
            return "skipped"
        source = session.get(KnowledgeSource, revision.source_id)
        version = session.get(FileVersion, revision.file_version_id) if revision.file_version_id else None
        if source is None or source.deleted_at is not None or (source.kind == "file" and version is None):
            return "skipped"
        if version is not None:
            session.expunge(version)
        source_id, kind, connection_id = source.id, source.kind, source.connection_id
        media_type = (version.media_type or "text/markdown") if version else ""
    _stage(db, tenant_id, revision_id, "scanning")
    if kind == "connector":
        _stage(db, tenant_id, revision_id, "parsing")
        try:
            documents = services.broker.connection_documents(tenant_id=tenant_id, connection_id=connection_id)
        except ApiError as exc:
            _fail(db, tenant_id, revision_id, exc.code, exc.detail)
            return "failed"
        parsed = ParseResult(_document_blocks(documents), "connector")
    else:
        assert version is not None
        if version.size_bytes > MAX_BYTES:
            _fail(db, tenant_id, revision_id, "TOO_LARGE", "Files over 100 MB cannot be used as knowledge.")
            return "failed"
        data = artifacts.read(services.objects, version)  # type: ignore[arg-type]
        _stage(db, tenant_id, revision_id, "parsing")
        try:
            parsed = parse(data, media_type, tika_url=services.tika_url)
        except ParseFailure as exc:
            _fail(db, tenant_id, revision_id, exc.code, str(exc))
            return "failed"
    _stage(db, tenant_id, revision_id, "chunking")
    chunks = chunking.chunk(parsed.blocks)
    keys = [c.key(source_id) for c in chunks]
    _stage(db, tenant_id, revision_id, "embedding")
    with db.transaction(tenant_id=tenant_id) as session:
        previous = {
            row.chunk_key: (row.embedding, row.embedding_profile)
            for row in session.execute(
                select(KnowledgeChunk.chunk_key, KnowledgeChunk.embedding, KnowledgeChunk.embedding_profile).where(
                    KnowledgeChunk.source_id == source_id,
                    KnowledgeChunk.chunk_key.in_(keys),
                    KnowledgeChunk.revision_id != revision_id,
                )
            )
        }
    missing = [i for i, k in enumerate(keys) if k not in previous]
    try:
        profile, fresh = (
            services.embeddings.embed(
                [f"{chunks[i].heading_path}\n{chunks[i].text}".strip() for i in missing], tenant_id=tenant_id
            )
            if missing
            else ("", [])
        )
    except Exception as exc:
        log.warning("embedding failed", extra={"revision": str(revision_id)})
        raise RuntimeError("embedding service unavailable") from exc
    vectors: list[list[float] | None] = [None] * len(chunks)
    profiles: list[str | None] = [None] * len(chunks)
    for i, vector in zip(missing, fresh, strict=True):
        vectors[i], profiles[i] = vector, profile
    for i, key in enumerate(keys):
        if vectors[i] is None:
            reused, reused_profile = previous[key]
            if profile and reused_profile != profile:  # never mix profiles inside one revision
                vectors[i], profiles[i] = (
                    services.embeddings.embed([chunks[i].text], tenant_id=tenant_id)[1][0],
                    profile,
                )
            else:
                vectors[i], profiles[i] = reused, reused_profile
                profile = profile or (reused_profile or "")
    _stage(db, tenant_id, revision_id, "indexing")
    with db.transaction(tenant_id=tenant_id) as session:
        session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.revision_id == revision_id))
        for item, key, stored, chunk_profile in zip(chunks, keys, vectors, profiles, strict=True):
            session.add(
                KnowledgeChunk(
                    id=ids.uuid7(),
                    tenant_id=tenant_id,
                    source_id=source_id,
                    revision_id=revision_id,
                    ordinal=item.ordinal,
                    chunk_key=key,
                    text=item.text,
                    heading_path=item.heading_path,
                    locator=item.locator,
                    locator_quality=item.locator_quality,
                    content_flags=item.flags,
                    tsv=func.to_tsvector("simple", index_text(f"{item.heading_path} {item.text}")),
                    embedding=stored,
                    embedding_profile=chunk_profile,
                )
            )
        revision = session.get(KnowledgeRevision, revision_id, with_for_update=True)
        source = session.get(KnowledgeSource, source_id, with_for_update=True)
        assert revision is not None and source is not None
        if revision.state != "building" or source.deleted_at is not None:
            return "skipped"
        if source.published_revision_id is not None:
            session.execute(
                update(KnowledgeRevision)
                .where(KnowledgeRevision.id == source.published_revision_id)
                .values(state="superseded")
            )
        revision.state, revision.stage, revision.published_at = "published", "done", utcnow()
        revision.chunk_count, revision.embedding_profile = len(chunks), profile or None
        revision.completeness, revision.parser = parsed.completeness, parsed.parser
        revision.error_detail = "; ".join(parsed.warnings)[:500] or None
        source.published_revision_id, source.status, source.error_code = revision.id, "ready", None
        source.last_synced_at = utcnow() if source.kind == "connector" else source.last_synced_at
        events.publish(
            session,
            tenant_id,
            "knowledge.source.updated",
            {"source_id": ids.encode("knowledge_source", source.id), "status": "ready"},
        )
    return "published"
