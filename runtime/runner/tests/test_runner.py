"""Runner unit tests: no control-plane imports (Part 12 §3)."""

from __future__ import annotations

import io
import json
import threading
import time
from pathlib import Path

import pytest

from workx_runner.engine_messages import safe_output_path
from workx_runner.engine_sdk import inside
from workx_runner.protocol import Control, Emitter


def test_output_paths_stay_in_outputs(tmp_path: Path) -> None:
    assert safe_output_path(str(tmp_path), "report.md") == (tmp_path / "report.md").resolve()
    # Directory parts are dropped, hidden and empty names refused.
    assert safe_output_path(str(tmp_path), "../../etc/passwd") == (tmp_path / "passwd").resolve()
    for bad in ("", ".env", "..", "."):
        with pytest.raises(ValueError):
            safe_output_path(str(tmp_path), bad)


def test_sdk_path_guard(tmp_path: Path) -> None:
    roots = [str(tmp_path / "workspace"), str(tmp_path / "outputs")]
    assert inside(str(tmp_path / "workspace" / "a" / "b.txt"), roots)
    assert not inside(str(tmp_path / "workspace-evil" / "x"), roots)
    assert not inside("/etc/passwd", roots)


def test_frames_carry_attempt_fence_and_unique_ids() -> None:
    out = io.StringIO()
    emitter = Emitter("att_1", 7, out)
    emitter.emit("run.started", {"engine": "messages"})
    emitter.emit("assistant.delta", {"text": "x" * 400_000})
    frames = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [f["runner_event_id"] for f in frames] == ["e1", "e2"]
    assert all(f["attempt_id"] == "att_1" and f["fence"] == 7 for f in frames)
    assert frames[1]["payload"] == {"truncated": True, "type": "assistant.delta"}


def test_control_approvals_and_cancel() -> None:
    control = Control()
    approvals = (
        '{"type":"approval","approval_id":"apr_2","decision":"rejected"}\n'
        '{"type":"approval","approval_id":"apr_1","decision":"approved"}\n'
    )
    control.start(io.StringIO(approvals))
    time.sleep(0.1)
    assert control.wait_approval("apr_1", 2) == "approved"
    # Other decisions are kept for later.
    assert control.approvals.qsize() == 1
    control.start(io.StringIO('{"type":"cancel"}\nnot json\n'))
    time.sleep(0.1)
    assert control.cancelled.is_set()
    # Once cancelled, nobody waits for an approval any more.
    assert control.wait_approval("apr_9", 5) is None


def test_approval_wait_times_out() -> None:
    control = Control()
    started = time.monotonic()
    threading.Thread(target=lambda: None).start()
    assert control.wait_approval("apr_x", 0.6) is None
    assert time.monotonic() - started < 3
