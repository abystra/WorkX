"""Knowledge API (Part 7, Part 11): make Library files searchable, attach them to workmates, search."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from workx.core import ids
from workx.core.errors import ApiError, conflict, validation
from workx.core.orm import utcnow
from workx.domains.agents import service as agents
from workx.domains.agents.models import Agent
from workx.domains.audit import service as audit
from workx.domains.authz import policy
from workx.domains.identity.auth import Authenticated, State
from workx.domains.knowledge import search as retrieval
from workx.domains.knowledge import service
from workx.domains.knowledge.embed import EmbeddingClient
from workx.domains.knowledge.models import KnowledgeRevision, KnowledgeSource
from workx.domains.resources import events
from workx.domains.resources.common import decode, load, require
from workx.domains.resources.models import File
from workx.domains.resources.projects import project_ids_for
from workx.domains.tenancy.api import tenant_uuid
from workx.domains.tenancy.service import Actor, tenant_scope

router = APIRouter(tags=["knowledge"])


class RevisionOut(BaseModel):
    revision: int
    state: str
    stage: str
    completeness: str
    parser: str | None
    chunk_count: int
    error_code: str | None
    note: str | None


class SourceOut(BaseModel):
    id: str
    file_id: str
    name: str
    status: str
    error_code: str | None
    latest: RevisionOut | None
    updated_at: datetime


def _file_readable(session: Session, actor: Actor, file: File) -> bool:
    if "read" in policy.allowed_actions(session, actor, "file", file):
        return True
    return bool(file.project_id and file.project_id in project_ids_for(session, actor))


def _out(session: Session, source: KnowledgeSource) -> SourceOut:
    latest = (
        session.execute(
            select(KnowledgeRevision)
            .where(KnowledgeRevision.source_id == source.id)
            .order_by(KnowledgeRevision.revision_no.desc())
        )
        .scalars()
        .first()
    )
    return SourceOut(
        id=ids.encode("knowledge_source", source.id),
        file_id=ids.encode("file", source.file_id),
        name=source.name,
        status=source.status,
        error_code=source.error_code,
        latest=RevisionOut(
            revision=latest.revision_no,
            state=latest.state,
            stage=latest.stage,
            completeness=latest.completeness,
            parser=latest.parser,
            chunk_count=latest.chunk_count,
            error_code=latest.error_code,
            note=latest.error_detail,
        )
        if latest
        else None,
        updated_at=source.updated_at,
    )


def _visible(session: Session, actor: Actor) -> list[KnowledgeSource]:
    rows = session.execute(
        select(KnowledgeSource, File)
        .join(File, File.id == KnowledgeSource.file_id)
        .where(KnowledgeSource.tenant_id == actor.tenant.id, KnowledgeSource.deleted_at.is_(None))
        .where(File.deleted_at.is_(None))
        .order_by(KnowledgeSource.updated_at.desc())
    ).all()
    return [source for source, file in rows if _file_readable(session, actor, file)]


@router.get("/tenants/{tenant_id}/knowledge-sources", summary="Knowledge sources made from files you can read")
def list_sources(tenant_id: str, principal: Authenticated, state: State) -> list[SourceOut]:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id)) as (session, actor):
        return [_out(session, s) for s in _visible(session, actor)]


class SourceIn(BaseModel):
    file_id: str


@router.post(
    "/tenants/{tenant_id}/knowledge-sources",
    summary="Make a Library file a knowledge source (idempotent per file); starts ingestion",
)
def create_source(
    tenant_id: str, body: SourceIn, principal: Authenticated, state: State, response: Response
) -> SourceOut:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id), write=True) as (
        session,
        actor,
    ):
        file = load(session, File, actor, body.file_id, "file", lock=True)
        extra = {"read", "use"} if file.project_id and file.project_id in project_ids_for(session, actor) else set()
        require(session, actor, "use", "file", file, extra)
        if file.current_version_id is None:
            raise conflict("INVALID_STATE", "This file has no content yet.")
        existed = session.execute(
            select(KnowledgeSource.id).where(
                KnowledgeSource.tenant_id == actor.tenant.id,
                KnowledgeSource.file_id == file.id,
                KnowledgeSource.deleted_at.is_(None),
            )
        ).scalar()
        source = service.create_or_refresh(session, actor, file)
        if existed is None:
            audit.record(
                session,
                "knowledge_source.created",
                tenant_id=actor.tenant.id,
                actor_user_id=actor.user_id,
                actor_membership_id=actor.membership.id,
                target_type="knowledge_source",
                target_id=source.id,
                data={"file_id": str(file.id)},
            )
        response.status_code = 200 if existed else 201
        return _out(session, source)


def _load_source(session: Session, actor: Actor, source_id: str) -> tuple[KnowledgeSource, File]:
    source = session.get(KnowledgeSource, decode("knowledge_source", source_id), with_for_update=True)
    if source is None or source.tenant_id != actor.tenant.id or source.deleted_at is not None:
        raise ApiError(404, "NOT_FOUND", "Not found.")
    file = session.get(File, source.file_id)
    if file is None or file.deleted_at is not None or not _file_readable(session, actor, file):
        raise ApiError(404, "NOT_FOUND", "Not found.")
    return source, file


@router.get("/tenants/{tenant_id}/knowledge-sources/{source_id}", summary="Knowledge source with ingestion status")
def get_source(tenant_id: str, source_id: str, principal: Authenticated, state: State) -> SourceOut:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id)) as (session, actor):
        return _out(session, _load_source(session, actor, source_id)[0])


@router.post("/tenants/{tenant_id}/knowledge-sources/{source_id}/reindex", summary="Build a new revision")
def reindex(tenant_id: str, source_id: str, principal: Authenticated, state: State) -> SourceOut:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id), write=True) as (
        session,
        actor,
    ):
        source, file = _load_source(session, actor, source_id)
        service.start_revision(session, source, file)
        return _out(session, source)


@router.delete(
    "/tenants/{tenant_id}/knowledge-sources/{source_id}",
    status_code=204,
    summary="Stop using a file as knowledge (excluded from search immediately)",
)
def delete_source(tenant_id: str, source_id: str, principal: Authenticated, state: State) -> Response:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id), write=True) as (
        session,
        actor,
    ):
        source, file = _load_source(session, actor, source_id)
        if source.owner_membership_id != actor.membership.id and "edit" not in policy.allowed_actions(
            session, actor, "file", file
        ):
            raise ApiError(403, "FORBIDDEN", "Only the person who added it or an editor of the file can remove it.")
        source.deleted_at = utcnow()
        audit.record(
            session,
            "knowledge_source.deleted",
            tenant_id=actor.tenant.id,
            actor_user_id=actor.user_id,
            actor_membership_id=actor.membership.id,
            target_type="knowledge_source",
            target_id=source.id,
        )
        events.publish(
            session, actor.tenant.id, "knowledge.source.updated", {"source_id": source_id, "status": "deleted"}
        )
    return Response(status_code=204)


class AgentKnowledgeIn(BaseModel):
    source_ids: list[str] = Field(max_length=50)


@router.put("/tenants/{tenant_id}/agents/{agent_id}/knowledge", summary="Knowledge sources a workmate may search")
def set_agent_knowledge(
    tenant_id: str, agent_id: str, body: AgentKnowledgeIn, principal: Authenticated, state: State
) -> dict[str, Any]:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id), write=True) as (
        session,
        actor,
    ):
        agent = load(session, Agent, actor, agent_id, "agent", lock=True)
        require(session, actor, "edit", "agent", agent)
        chosen: list[uuid.UUID] = []
        for external in dict.fromkeys(body.source_ids):
            try:
                source, _ = _load_source(session, actor, external)
            except ApiError as exc:
                raise validation("Unknown knowledge source.", data={"field": "source_ids"}) from exc
            chosen.append(source.id)
        published = agents.update(session, actor, agent, {"knowledge_source_ids": chosen})
        events.publish(session, actor.tenant.id, "agent.updated", {"agent_id": agent_id})
        return {
            "id": agent_id,
            "knowledge_source_ids": [ids.encode("knowledge_source", s) for s in agent.knowledge_source_ids],
            "published_version": published,
        }


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    source_ids: list[str] | None = Field(default=None, max_length=50)
    k: int = Field(default=8, ge=1, le=20)


class PassageOut(BaseModel):
    citation_id: str
    source_id: str
    source: str
    section: str
    locator: dict[str, Any]
    text: str
    score: float
    flagged: bool


@router.post("/tenants/{tenant_id}/knowledge/search", summary="Search knowledge you can read (hybrid, cited)")
def search_knowledge(tenant_id: str, body: SearchIn, principal: Authenticated, state: State) -> list[PassageOut]:
    tid = tenant_uuid(tenant_id)
    client: EmbeddingClient = state.services["embeddings"]
    try:
        profile, [vector] = client.embed([body.query], tenant_id=tid)
    except ApiError:
        profile, vector = "", None  # embedding outage: full-text results only
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tid, write=True) as (session, actor):
        if body.source_ids is None:
            sources = [s.id for s in _visible(session, actor)]
        else:
            sources = [decode("knowledge_source", s) for s in body.source_ids]
        passages = retrieval.search(
            session,
            tenant_id=tid,
            membership_id=actor.membership.id,
            query=body.query,
            source_ids=sources,
            query_vector=vector,
            profile=profile,
            k=body.k,
        )
        return [
            PassageOut(
                citation_id=p.citation_id,
                source_id=p.source_id,
                source=p.source_name,
                section=p.heading_path,
                locator=p.locator,
                text=p.text,
                score=p.score,
                flagged=p.untrusted_instructions,
            )
            for p in passages
        ]
