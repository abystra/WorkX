"""Runtime wiring for the job queue: queued Tasks become ``run_task`` jobs for the orchestrator; the worker's
reconciler ends Attempts whose lease expired."""

from __future__ import annotations

from workx.domains.runtime.orchestrator import reconcile_expired_attempts
from workx.platform import jobs

jobs.subscribe("task.queued", "run_task")


@jobs.handler("reconcile_runtime")
def reconcile_runtime(ctx: jobs.JobContext, job: jobs.Job) -> None:
    reconcile_expired_attempts(ctx.db)
