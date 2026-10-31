"""Single redaction policy for logs, traces, events and audit (Part 11 §6).

Values under sensitive keys are replaced, and secret-looking substrings are masked anywhere in strings.
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_KEYS = re.compile(
    r"(^pass$|passw(or)?d|passphrase|secret|token|api[_-]?key|authorization|cookie|credential|private[_-]?key|refresh"
    r"|ticket|code_verifier)",
    re.IGNORECASE,
)
_SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),  # Anthropic keys
    re.compile(r"e2b_[A-Za-z0-9]{16,}"),  # E2B keys
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-~+/]{8,}=*"),
    re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),  # JWTs
    re.compile(r"WORKX_CANARY_[A-Za-z0-9]{8,}"),  # canary secrets injected by tests
]


def redact_text(value: str) -> str:
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub(REDACTED, value)
    return value


def redact(value: Any, *, _key: str = "") -> Any:
    if _key and _SENSITIVE_KEYS.search(_key):
        return REDACTED
    if isinstance(value, dict):
        return {k: redact(v, _key=str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return redact_text(value)
    return value
