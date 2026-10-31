"""JSON logs with the shared redaction policy and the current request ID."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from workx.core import context
from workx.core.redaction import redact, redact_text

_RESERVED = set(vars(logging.makeLogRecord({})))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        extra = {k: v for k, v in vars(record).items() if k not in _RESERVED and not k.startswith("_")}
        body: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact_text(record.getMessage()),
            "request_id": context.request_id.get() or None,
            **redact(extra),
        }
        if record.exc_info:
            body["exc"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(body, default=str, ensure_ascii=False)


def configure(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
