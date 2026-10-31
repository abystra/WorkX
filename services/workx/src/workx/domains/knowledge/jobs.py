"""Knowledge worker: ingestion runs as jobs (retried with backoff on embedding outages)."""

from __future__ import annotations

import uuid
from datetime import timedelta

import httpx
from sqlalchemy import text

from workx.core.orm import utcnow
from workx.domains.knowledge import service
from workx.domains.knowledge.embed import EmbeddingClient
from workx.domains.knowledge.models import KnowledgeSource
from workx.platform import jobs, storage


@jobs.handler("knowledge_ingest", topics=("knowledge.revision_requested",))
def knowledge_ingest(ctx: jobs.JobContext, job: jobs.Job) -> None:
    settings = ctx.settings
    services = ctx.services.get("knowledge")
    if services is None:
        services = service.Services(
            db=ctx.db,
            objects=storage.from_url(settings.object_store_url),
            embeddings=EmbeddingClient(
                settings.model_gateway_url, settings.embedding_token.get_secret_value(), httpx.Client(timeout=120)
            ),
            tika_url=getattr(settings, "tika_url", ""),
            broker=ctx.services.get("broker"),
        )
        ctx.services["knowledge"] = services
    service.ingest(services, uuid.UUID(job.payload["tenant_id"]), uuid.UUID(job.payload["revision_id"]))


SYNC_EVERY = timedelta(minutes=15)


@jobs.handler("knowledge_sync_tick")
def knowledge_sync_tick(ctx: jobs.JobContext, job: jobs.Job) -> None:
    """Connector sources re-sync periodically (R2): upstream edits and deletions reach the index."""
    with ctx.db.transaction() as session:
        due = session.execute(
            text("SELECT tenant_id, id FROM workx_due_knowledge_syncs(:before, 50)"), {"before": utcnow() - SYNC_EVERY}
        ).all()
    for tenant_id, source_id in due:
        with ctx.db.transaction(tenant_id=tenant_id) as session:
            source = session.get(KnowledgeSource, source_id, with_for_update=True)
            if source is not None and source.deleted_at is None:
                service.start_revision(session, source, None)
