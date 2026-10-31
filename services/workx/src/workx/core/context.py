"""Per-request context carried through logs, errors and audit records."""

from __future__ import annotations

from contextvars import ContextVar

request_id: ContextVar[str] = ContextVar("request_id", default="")
