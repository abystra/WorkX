"""Knowledge worker: ingestion runs as jobs (retried with backoff on embedding outages)."""

from __future__ import annotations

import uuid

import httpx

from workx.domains.knowledge import service
from workx.domains.knowledge.embed import EmbeddingClient
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
        )
        ctx.services["knowledge"] = services
    service.ingest(services, uuid.UUID(job.payload["tenant_id"]), uuid.UUID(job.payload["revision_id"]))
