"""Outbox → jobs → handlers: exactly-once enqueue, at-least-once execution, backoff, DLQ, lease takeover."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update

from tests.integration.test_tenancy import create_org
from tests.support.auth import idem, sign_in, unique_email
from workx.core import ids
from workx.core.db import Database
from workx.core.orm import utcnow
from workx.domains.usage import service as usage
from workx.entrypoints.worker import build_context, schedule_reconcile
from workx.platform import jobs, outbox
from workx.platform.jobs import JobRow
from workx.platform.mail import FileMailer


@pytest.fixture
def isolated_queue(owner_db: Database) -> Iterator[None]:
    """Each test starts from an empty queue (other tests leave events behind)."""
    with owner_db.transaction() as session:
        session.execute(text("UPDATE outbox_events SET dispatched_at = now() WHERE dispatched_at IS NULL"))
        session.execute(text("DELETE FROM jobs"))
    yield


@pytest.fixture
def ctx(api_app: FastAPI, db: Database, tmp_path: Path) -> jobs.JobContext:
    context = build_context(api_app.state.workx.settings, db)
    context.services["mailer"] = FileMailer(tmp_path, "test@workx")
    return context


calls: list[str] = []


@jobs.handler("test.record", topics=("test.happened",))
def _record(ctx: jobs.JobContext, job: jobs.Job) -> None:
    calls.append(job.payload["value"])


@jobs.handler("test.flaky")
def _flaky(ctx: jobs.JobContext, job: jobs.Job) -> None:
    raise RuntimeError("upstream said no, token sk-ant-api03-SECRETSECRET")


def test_outbox_fans_out_exactly_once(db: Database, ctx: jobs.JobContext, isolated_queue: None) -> None:
    calls.clear()
    with db.transaction() as session:
        outbox.emit(session, "test.happened", {"value": "a"})
    assert jobs.dispatch_outbox(db) == 1
    assert jobs.dispatch_outbox(db) == 0  # already dispatched
    counts = jobs.run_once(ctx, "w1")
    assert counts.get("succeeded") == 1 and calls == ["a"]
    with db.transaction() as session:
        dedupe = session.execute(select(JobRow.dedupe_key).where(JobRow.kind == "test.record")).scalar_one()
        assert dedupe is not None and dedupe.endswith(":test.record")
        assert jobs.enqueue(session, "test.record", {"value": "dup"}, dedupe_key=dedupe) is None


def test_invitation_email_is_sent_by_the_worker(
    new_client: Callable[[], TestClient], oidc: TestClient, ctx: jobs.JobContext, tmp_path: Path, isolated_queue: None
) -> None:
    owner = new_client()
    sign_in(owner, oidc)
    org = create_org(owner)
    address = unique_email()
    owner.post(f"/api/v1/tenants/{org['id']}/invitations", json={"emails": address}, headers=idem())
    counts = jobs.run_once(ctx, "w1")
    assert counts.get("succeeded", 0) >= 1, counts
    mails = [p.read_text() for p in tmp_path.glob("*.eml")]
    assert any(address in m and "/invite/" in m for m in mails)


def test_failures_back_off_then_dead_letter_with_redacted_error(
    db: Database, ctx: jobs.JobContext, owner_db: Database, isolated_queue: None
) -> None:
    with db.transaction() as session:
        job_id = jobs.enqueue(session, "test.flaky", {}, max_attempts=2)
    assert job_id
    assert jobs.run_once(ctx, "w1") == {"dispatched": 0, "queued": 1}
    with owner_db.transaction() as session:
        row = session.get(JobRow, job_id)
        assert row is not None and row.run_after > utcnow() and row.attempts == 1
        assert "SECRETSECRET" not in (row.last_error or "") and "upstream said no" in (row.last_error or "")
        row.run_after = utcnow()
    assert jobs.run_once(ctx, "w1") == {"dispatched": 0, "dead": 1}
    assert [r.id for r in jobs.dead_letters(db)] == [job_id]
    assert jobs.retry(db, job_id) and not jobs.retry(db, job_id)
    with db.transaction() as session:
        assert session.get(JobRow, job_id).status == "queued"  # type: ignore[union-attr]


def test_expired_lease_is_taken_over(
    db: Database, ctx: jobs.JobContext, owner_db: Database, isolated_queue: None
) -> None:
    calls.clear()
    with db.transaction() as session:
        job_id = jobs.enqueue(session, "test.record", {"value": "x"})
    [claimed] = jobs.claim(db, "crashed-worker")
    assert claimed.id == job_id and jobs.claim(db, "w2") == []
    with owner_db.transaction() as session:
        session.execute(update(JobRow).where(JobRow.id == job_id).values(locked_until=utcnow() - timedelta(seconds=1)))
    [again] = jobs.claim(db, "w2")
    assert again.id == job_id and again.attempts == 2
    assert jobs.run_job(ctx, again, "w2") == "succeeded"
    # The crashed worker's late completion is ignored rather than overwriting the result.
    assert jobs.run_job(ctx, claimed, "crashed-worker") == "lost"


def test_unknown_kind_dead_letters(db: Database, ctx: jobs.JobContext, isolated_queue: None) -> None:
    with db.transaction() as session:
        jobs.enqueue(session, "no.such.handler", {}, max_attempts=1)
    assert jobs.run_once(ctx, "w1").get("dead") == 1


def test_reconciler_expires_invitations(
    new_client: Callable[[], TestClient],
    oidc: TestClient,
    ctx: jobs.JobContext,
    owner_db: Database,
    isolated_queue: None,
) -> None:
    owner = new_client()
    sign_in(owner, oidc)
    org = create_org(owner)
    [invite] = owner.post(
        f"/api/v1/tenants/{org['id']}/invitations", json={"emails": unique_email()}, headers=idem()
    ).json()
    with owner_db.transaction() as session:
        session.execute(
            text("UPDATE invitations SET expires_at = now() - interval '1 minute' WHERE id = :i"),
            {"i": ids.decode("invitation", invite["id"])},
        )
    schedule_reconcile(ctx)
    schedule_reconcile(ctx)  # same 5-minute bucket: one job
    jobs.run_once(ctx, "w1")
    with owner_db.transaction() as session:
        status = session.execute(
            text("SELECT status FROM invitations WHERE id = :i"), {"i": ids.decode("invitation", invite["id"])}
        ).scalar_one()
        assert status == "expired"
        assert session.execute(text("SELECT count(*) FROM jobs WHERE kind = 'reconcile'")).scalar_one() == 1


def test_usage_is_metered_once_per_source_event(
    db: Database, owner_db: Database, client: TestClient, oidc: TestClient
) -> None:
    me = sign_in(client, oidc)
    tenant = ids.decode("tenant", client.get("/api/v1/me/tenants").json()[0]["id"])
    assert tenant
    source = str(uuid.uuid4())
    with db.transaction(tenant_id=tenant, principal_id=ids.decode("user", me["id"])) as session:
        assert usage.record(
            session, tenant_id=tenant, kind="model_tokens", quantity=1200, unit="token", source_event_id=source
        )
        assert not usage.record(
            session, tenant_id=tenant, kind="model_tokens", quantity=1200, unit="token", source_event_id=source
        )
    with owner_db.transaction() as session:
        total = session.execute(
            text("SELECT sum(quantity) FROM usage_events WHERE source_event_id = :s"), {"s": source}
        ).scalar()
        assert total == 1200
