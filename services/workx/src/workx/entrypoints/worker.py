"""Background worker: ``workx worker``. Dispatches the outbox and runs jobs (Part 10 §4)."""

from __future__ import annotations

import logging
import os
import socket
import time
from datetime import UTC, datetime

import httpx

from workx.core.db import Database
from workx.core.settings import ApiSettings
from workx.domains.connections.broker_client import BrokerClient
from workx.domains.resources.scheduler import schedule_tick
from workx.platform import jobs, mail

log = logging.getLogger("workx.worker")
RECONCILE_EVERY_MINUTES = 5


def load_handlers() -> None:
    """Importing handler modules registers them. Each phase adds its modules here."""
    import workx.domains.channels.jobs
    import workx.domains.connections.jobs
    import workx.domains.knowledge.jobs
    import workx.domains.resources.scheduler
    import workx.domains.runtime.jobs
    import workx.domains.tenancy.jobs  # noqa: F401


def build_context(settings: ApiSettings | None = None, db: Database | None = None) -> jobs.JobContext:
    settings = settings or ApiSettings()
    load_handlers()
    return jobs.JobContext(
        db=db or Database.connect(settings.database_url),
        settings=settings,
        services={
            "mailer": mail.from_url(settings.mail_url, settings.mail_from),
            "broker": BrokerClient(
                settings.broker_url, settings.broker_token.get_secret_value(), httpx.Client(timeout=15)
            ),
        },
    )


def schedule_reconcile(ctx: jobs.JobContext, now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    bucket = now.replace(second=0, microsecond=0, minute=now.minute - now.minute % RECONCILE_EVERY_MINUTES)
    with ctx.db.transaction() as session:
        for kind in ("reconcile", "reconcile_runtime"):
            jobs.enqueue(session, kind, {}, dedupe_key=f"{kind}:{bucket.isoformat()}", max_attempts=1)


def run(*, once: bool = False, idle_sleep: float = 1.0) -> int:
    ctx = build_context()
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    log.info("worker started", extra={"worker": worker_id, "handlers": sorted(jobs.registered())})
    while True:
        schedule_reconcile(ctx)
        schedule_tick(ctx)
        counts = jobs.run_once(ctx, worker_id)
        if once:
            print(counts)
            return 0
        if sum(v for k, v in counts.items() if k != "dispatched") == 0 and counts["dispatched"] == 0:
            time.sleep(idle_sleep)
