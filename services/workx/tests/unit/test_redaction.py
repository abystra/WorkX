import json
import logging

from workx.core.logging import JsonFormatter
from workx.core.redaction import REDACTED, redact


def test_sensitive_keys_and_patterns() -> None:
    value = {
        "api_key": "abc",
        "nested": {"refresh_token": "r", "note": "uses sk-ant-api03-ABCDEFGHIJKL and Bearer abcdefghijkl"},
        "items": ["WORKX_CANARY_1234567890"],
        "count": 3,
    }
    out = redact(value)
    assert out["api_key"] == REDACTED
    assert out["nested"]["refresh_token"] == REDACTED
    assert "sk-ant" not in out["nested"]["note"] and "abcdefghijkl" not in out["nested"]["note"]
    assert out["items"] == [REDACTED]
    assert out["count"] == 3


def test_log_records_are_redacted() -> None:
    record = logging.makeLogRecord(
        {"msg": "calling with %s", "args": ("sk-ant-api03-SECRETSECRET",), "levelname": "INFO", "client_secret": "x"}
    )
    line = json.loads(JsonFormatter().format(record))
    assert "SECRETSECRET" not in line["msg"]
    assert line["client_secret"] == REDACTED


def test_ordinary_keys_that_contain_pass_are_kept() -> None:
    value = {"passages": ["a"], "passenger": "b", "password": "c", "pass": "d", "user_passwd": "e", "passphrase": "f"}
    out = redact(value)
    assert out["passages"] == ["a"] and out["passenger"] == "b"
    assert all(out[k] == REDACTED for k in ("password", "pass", "user_passwd", "passphrase"))
