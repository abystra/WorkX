"""PostgreSQL job queue and outbox dispatcher (decision 10; Part 10 §4).

* ``outbox.emit`` writes events in the business transaction. ``dispatch_outbox`` turns each event into one
  job per subscribed handler; the dedupe key ``<event id>:<kind>`` makes that enqueue exactly-once.
* Workers claim jobs with ``FOR UPDATE SKIP LOCKED`` and a lease. A crashed worker's lease expires and the
  job is claimed again, so execution is at-least-once: handlers must be idempotent.
* Failures back off exponentially; after ``max_attempts`` the job is ``dead`` (the DLQ) until retried.
* Payloads carry IDs only. Handlers reload rows under the job's tenant context.
"""

from __future__ import annotations

import logging
import random
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from workx.core import ids
from workx.core.db import Database
from workx.core.orm import Base, utcnow
from workx.core.redaction import redact_text
from workx.platform.models import OutboxEvent

log = logging.getLogger("workx.jobs")
LEASE = timedelta(minutes=5)


class JobRow(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID | None]
    kind: Mapped[str]
    payload: Mapped[dict[str, Any]] = mapped_column(server_default="{}")
    dedupe_key: Mapped[str | None]
    status: Mapped[str] = mapped_column(server_default="queued")
    attempts: Mapped[int] = mapped_column(server_default="0")
    max_attempts: Mapped[int] = mapped_column(server_default="8")
    run_after: Mapped[datetime] = mapped_column(server_default="now()")
    locked_by: Mapped[str | None]
    locked_until: Mapped[datetime | None]
    last_error: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(server_default="now()")
    finished_at: Mapped[datetime | None]


@dataclass(frozen=True)
class Job:
    id: uuid.UUID
    tenant_id: uuid.UUID | None
    kind: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int


@dataclass
class JobContext:
    db: Database
    settings: Any
    services: dict[str, Any] = field(default_factory=dict)


Handler = Callable[[JobContext, Job], None]
_handlers: dict[str, Handler] = {}
_subscriptions: dict[str, list[str]] = {}


def handler(kind: str, *, topics: tuple[str, ...] = ()) -> Callable[[Handler], Handler]:
    """Registers a job handler, optionally subscribed to outbox topics."""

    def register(fn: Handler) -> Handler:
        _handlers[kind] = fn
        for topic in topics:
            _subscriptions.setdefault(topic, [])
            if kind not in _subscriptions[topic]:
                _subscriptions[topic].append(kind)
        return fn

    return register


def registered() -> dict[str, Handler]:
    return dict(_handlers)


def subscribe(topic: str, kind: str) -> None:
    """Fan an outbox topic out to a job kind handled by another process (e.g. the orchestrator's run_task)."""
    _subscriptions.setdefault(topic, [])
    if kind not in _subscriptions[topic]:
        _subscriptions[topic].append(kind)


def enqueue(
    session: Session,
    kind: str,
    payload: dict[str, Any],
    *,
    tenant_id: uuid.UUID | None = None,
    dedupe_key: str | None = None,
    run_after: datetime | None = None,
    max_attempts: int = 8,
) -> uuid.UUID | None:
    """Returns the new job id, or None when ``dedupe_key`` already exists."""
    job_id = ids.uuid7()
    inserted = session.execute(
        insert(JobRow)
        .values(
            id=job_id,
            tenant_id=tenant_id,
            kind=kind,
            payload=payload,
            dedupe_key=dedupe_key,
            run_after=run_after or utcnow(),
            max_attempts=max_attempts,
        )
        .on_conflict_do_nothing(index_elements=["dedupe_key"])
        .returning(JobRow.id)
    ).scalar()
    return inserted


def dispatch_outbox(db: Database, *, limit: int = 200) -> int:
    with db.transaction() as session:
        events = (
            session.execute(
                select(OutboxEvent)
                .where(OutboxEvent.dispatched_at.is_(None))
                .order_by(OutboxEvent.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )
        for event in events:
            for kind in _subscriptions.get(event.topic, []):
                enqueue(
                    session,
                    kind,
                    {**event.payload, "event_id": str(event.id), "topic": event.topic},
                    tenant_id=event.tenant_id,
                    dedupe_key=f"{event.id}:{kind}",
                )
            event.dispatched_at = utcnow()
        return len(events)


def claim(
    db: Database, worker_id: str, *, kinds: tuple[str, ...] | None = None, limit: int = 10, lease: timedelta = LEASE
) -> list[Job]:
    """Claims ready jobs, optionally only of ``kinds`` (each process claims only what it can handle)."""
    with db.transaction() as session:
        rows = session.execute(
            text(
                """
                UPDATE jobs SET status = 'running', attempts = attempts + 1, locked_by = :worker,
                  locked_until = now() + make_interval(secs => :lease)
                WHERE id IN (
                  SELECT id FROM jobs
                  WHERE ((status = 'queued' AND run_after <= now()) OR (status = 'running' AND locked_until < now()))
                    AND (CAST(:kinds AS text[]) IS NULL OR kind = ANY(CAST(:kinds AS text[])))
                  ORDER BY run_after
                  LIMIT :limit
                  FOR UPDATE SKIP LOCKED
                )
                RETURNING id, tenant_id, kind, payload, attempts, max_attempts
                """
            ),
            {
                "worker": worker_id,
                "lease": lease.total_seconds(),
                "limit": limit,
                "kinds": list(kinds) if kinds else None,
            },
        ).all()
    return [Job(r.id, r.tenant_id, r.kind, r.payload, r.attempts, r.max_attempts) for r in rows]


def backoff(attempts: int) -> timedelta:
    base = min(2 ** max(attempts, 1), 900)
    return timedelta(seconds=base * (0.75 + random.random() / 2))  # noqa: S311 (jitter, not security)


def _finish(db: Database, job: Job, worker_id: str, error: str | None) -> str:
    with db.transaction() as session:
        row = session.get(JobRow, job.id, with_for_update=True)
        if row is None or row.locked_by != worker_id or row.status != "running":
            return "lost"  # lease expired and another worker took it over
        row.locked_by = None
        row.locked_until = None
        if error is None:
            row.status = "succeeded"
            row.finished_at = utcnow()
            row.last_error = None
        elif row.attempts >= row.max_attempts:
            row.status = "dead"
            row.finished_at = utcnow()
            row.last_error = error
        else:
            row.status = "queued"
            row.run_after = utcnow() + backoff(row.attempts)
            row.last_error = error
        return row.status


def run_job(ctx: JobContext, job: Job, worker_id: str) -> str:
    fn = _handlers.get(job.kind)
    try:
        if fn is None:
            raise LookupError(f"no handler registered for {job.kind}")
        fn(ctx, job)
    except Exception as exc:
        message = redact_text(f"{type(exc).__name__}: {exc}")[:2000]
        log.warning("job failed", extra={"job_id": str(job.id), "kind": job.kind, "attempt": job.attempts})
        return _finish(ctx.db, job, worker_id, message)
    return _finish(ctx.db, job, worker_id, None)


def complete(db: Database, job: Job, worker_id: str, result: str) -> str:
    """For processes that handle a job without a registered handler: 'succeeded', 'defer' (retry soon without
    counting an attempt) or 'error' (normal backoff and dead-lettering)."""
    if result == "defer":
        with db.transaction() as session:
            row = session.get(JobRow, job.id, with_for_update=True)
            if row is None or row.locked_by != worker_id:
                return "lost"
            row.status, row.locked_by, row.locked_until = "queued", None, None
            row.attempts = max(row.attempts - 1, 0)
            row.run_after = utcnow() + timedelta(seconds=5)
            return "queued"
    return _finish(db, job, worker_id, None if result == "succeeded" else result)


def run_once(ctx: JobContext, worker_id: str, *, limit: int = 10) -> dict[str, int]:
    counts = {"dispatched": dispatch_outbox(ctx.db)}
    for job in claim(ctx.db, worker_id, kinds=tuple(_handlers), limit=limit):
        status = run_job(ctx, job, worker_id)
        counts[status] = counts.get(status, 0) + 1
    return counts


def dead_letters(db: Database, *, limit: int = 100) -> list[JobRow]:
    with db.transaction() as session:
        return list(
            session.execute(
                select(JobRow).where(JobRow.status == "dead").order_by(JobRow.finished_at.desc()).limit(limit)
            ).scalars()
        )


def retry(db: Database, job_id: uuid.UUID) -> bool:
    with db.transaction() as session:
        result = session.execute(
            update(JobRow)
            .where(JobRow.id == job_id, JobRow.status == "dead")
            .values(status="queued", attempts=0, run_after=utcnow(), finished_at=None)
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]
