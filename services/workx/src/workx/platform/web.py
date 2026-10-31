"""Shared web plumbing for domain routers: application state access and common dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import Request

from workx.core.db import Database
from workx.core.settings import ApiSettings


@dataclass
class AppState:
    settings: ApiSettings
    db: Database
    # Late-bound services registered by the entrypoint (identity provider client, mailer, ...).
    services: dict[str, Any] = field(default_factory=dict)


def app_state(request: Request) -> AppState:
    state: AppState = request.app.state.workx
    return state
