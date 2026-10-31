"""Automations scheduler (R2, P-10): due automations become tasks of their owner, once per slot; missed slots
after downtime run once; inactive owners and missing workmates are recorded as skipped."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI
from sqlalchemy import text

from workx.core import ids
from workx.core.db import Database
from workx.domains.resources import scheduler
from workx.entrypoints.worker import build_context
from workx.platform import jobs


def _tick(api_app: FastAPI, db: Database) -> None:
    ctx = build_context(api_app.state.workx.settings, db)
    scheduler.schedule_tick(ctx, datetime.now(UTC) + timedelta(days=3650))  # a fresh minute key per call
    job = jobs.Job(id=ids.uuid7(), tenant_id=None, kind="automation_tick", payload={}, attempts=1, max_attempts=1)
    scheduler.automation_tick(ctx, job)


def _make_due(owner_db: Database, automation_id: str, minutes_ago: int = 1) -> None:
    with owner_db.transaction() as session:
        session.execute(
            text("UPDATE automations SET next_run_at = now() - make_interval(mins => :m) WHERE id = :a"),
            {"m": minutes_ago, "a": ids.decode("automation", automation_id)},
        )


def test_due_automation_creates_one_task_per_slot(
    team: dict[str, Any], api_app: FastAPI, db: Database, owner_db: Database
) -> None:
    alice, base = team["alice"], team["base"]
    created = alice.post(
        f"{base}/automations",
        json={
            "name": "Weekly summary",
            "description": "Summarize the week",
            "prompt": "Summarize this week",
            "schedule": "0 9 * * 1",
            "timezone": "Asia/Shanghai",
        },
    )
    assert created.status_code == 201, created.text
    automation = created.json()
    _make_due(owner_db, automation["id"], minutes_ago=60 * 24 * 3)  # down for three days: one run, not many
    _tick(api_app, db)
    _tick(api_app, db)  # a second worker tick in the same window does nothing
    runs = alice.get(f"{base}/automations/{automation['id']}/runs").json()
    assert len(runs) == 1 and runs[0]["status"] == "created" and runs[0]["task_id"]
    task = alice.get(f"{base}/tasks/{runs[0]['task_id']}").json()
    assert task["status"] == "queued" and task["name"].startswith("Weekly summary")
    detail = alice.get(f"{base}/automations").json()
    mine = next(a for a in detail if a["id"] == automation["id"])
    assert datetime.fromisoformat(mine["next_run_at"]) > datetime.now(UTC)  # next Monday 09:00 Shanghai


def test_inactive_owner_or_paused_automation_does_not_run(
    team: dict[str, Any], api_app: FastAPI, db: Database, owner_db: Database
) -> None:
    alice, bob, base = team["alice"], team["bob"], team["base"]
    mine = bob.post(
        f"{base}/automations",
        json={"name": "Bob's digest", "prompt": "Digest", "schedule": "*/5 * * * *", "timezone": "UTC"},
    ).json()
    paused = alice.post(
        f"{base}/automations",
        json={"name": "Paused", "prompt": "Never", "schedule": "*/5 * * * *", "timezone": "UTC", "enabled": False},
    ).json()
    _make_due(owner_db, mine["id"])
    _make_due(owner_db, paused["id"])
    with owner_db.transaction() as session:
        session.execute(
            text("UPDATE memberships SET status = 'deactivated' WHERE id = :m"),
            {"m": ids.decode("membership", team["bob_membership"])},
        )
    _tick(api_app, db)
    with owner_db.transaction() as session:
        rows = session.execute(
            text("SELECT automation_id, status, reason FROM automation_runs WHERE automation_id IN (:a, :b)"),
            {"a": ids.decode("automation", mine["id"]), "b": ids.decode("automation", paused["id"])},
        ).all()
    assert [(r.status, r.reason) for r in rows] == [("skipped", "owner_inactive")]
