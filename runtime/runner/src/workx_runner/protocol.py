"""NDJSON frames on stdout (runner → orchestrator) and control messages on stdin (orchestrator → runner)."""

from __future__ import annotations

import json
import queue
import sys
import threading
from dataclasses import dataclass, field
from typing import Any, TextIO

MAX_FRAME_BYTES = 256 * 1024


class Emitter:
    def __init__(self, attempt_id: str, fence: int, out: TextIO | None = None) -> None:
        self.attempt_id = attempt_id
        self.fence = fence
        self._out = out or sys.stdout
        self._lock = threading.Lock()
        self._counter = 0

    def emit(self, type_: str, payload: dict[str, Any] | None = None) -> str:
        with self._lock:
            self._counter += 1
            event_id = f"e{self._counter}"
            frame = {
                "runner_event_id": event_id,
                "attempt_id": self.attempt_id,
                "fence": self.fence,
                "type": type_,
                "payload": payload or {},
            }
            line = json.dumps(frame, ensure_ascii=False)
            if len(line.encode()) > MAX_FRAME_BYTES:
                frame["payload"] = {"truncated": True, "type": type_}
                line = json.dumps(frame)
            self._out.write(line + "\n")
            self._out.flush()
            return event_id


@dataclass
class Control:
    """Reads control messages from stdin on a background thread."""

    cancelled: threading.Event = field(default_factory=threading.Event)
    approvals: queue.Queue[dict[str, Any]] = field(default_factory=queue.Queue)

    def start(self, stream: TextIO | None = None) -> None:
        source = stream or sys.stdin
        threading.Thread(target=self._read, args=(source,), daemon=True).start()

    def _read(self, stream: TextIO) -> None:
        for line in stream:
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if message.get("type") == "cancel":
                self.cancelled.set()
            elif message.get("type") == "approval":
                self.approvals.put(message)

    def wait_approval(self, approval_id: str, timeout: float) -> str | None:
        """Returns 'approved' / 'rejected', or None on timeout or cancellation."""
        deadline = timeout
        pending: list[dict[str, Any]] = []
        try:
            while deadline > 0 and not self.cancelled.is_set():
                try:
                    message = self.approvals.get(timeout=min(0.5, deadline))
                except queue.Empty:
                    deadline -= 0.5
                    continue
                if message.get("approval_id") == approval_id:
                    return str(message.get("decision"))
                pending.append(message)
            return None
        finally:
            for message in pending:
                self.approvals.put(message)
