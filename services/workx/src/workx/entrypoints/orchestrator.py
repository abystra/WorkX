"""Orchestrator process: ``workx orchestrator``. Claims queued Tasks and supervises their Attempts."""

from __future__ import annotations

import logging
import os
import socket
import time
from concurrent.futures import ThreadPoolExecutor

from workx.core.db import Database
from workx.core.settings import OrchestratorSettings
from workx.domains.runtime.orchestrator import Orchestrator
from workx.domains.runtime.sandbox import E2BProvider, LocalProcessProvider, SandboxProvider

log = logging.getLogger("workx.orchestrator")


def build_provider(settings: OrchestratorSettings) -> SandboxProvider:
    if settings.sandbox_provider == "e2b":
        if not settings.e2b_api_key.get_secret_value():
            raise SystemExit("WORKX_E2B_API_KEY is required for the e2b sandbox provider")
        return E2BProvider(settings.e2b_api_key.get_secret_value(), settings.e2b_template)
    if settings.is_production:
        raise SystemExit("The local_process sandbox is for development only; use e2b in staging and production")
    return LocalProcessProvider()


def run(*, max_parallel: int = 8, idle_sleep: float = 0.5) -> int:
    settings = OrchestratorSettings()
    if not settings.model_tiers:
        log.warning("WORKX_MODEL_TIERS is empty: tasks will fail with model_not_configured")
    orchestrator = Orchestrator(
        Database.connect(settings.database_url),
        settings,
        build_provider(settings),
        f"{socket.gethostname()}:{os.getpid()}",
    )
    with ThreadPoolExecutor(max_workers=max_parallel, thread_name_prefix="attempt") as pool:
        while True:
            started = orchestrator.claim_and_start()
            for item in started:
                pool.submit(orchestrator.run, item)
            if not started:
                time.sleep(idle_sleep)
