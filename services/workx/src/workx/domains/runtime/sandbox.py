"""Sandbox providers (Part 4 §5, Part 5). The orchestrator only uses this interface.

* ``local_process``: a directory per Attempt and the Runner as a local subprocess. Development and tests;
  not an isolation boundary.
* ``e2b``: an E2B sandbox from the WorkX template with egress denied except the gateway hosts. Production.

Both start the Runner with an explicitly built environment: nothing from the orchestrator's own environment
is inherited, so no platform secret can reach the sandbox (decisions 7 and 19).
"""

from __future__ import annotations

import contextlib
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

# Fallback for checkouts where the runner package is not installed (repo root = parents[6]).
RUNNER_SRC = Path(__file__).resolve().parents[6] / "runtime" / "runner" / "src"


@dataclass(frozen=True)
class Paths:
    root: str
    cwd: str
    outputs: str
    run: str


@dataclass(frozen=True)
class OutputFile:
    name: str
    size: int
    is_symlink: bool
    is_file: bool


class RunnerProcess(Protocol):
    def lines(self, timeout: float) -> Iterator[str]: ...
    def send(self, line: str) -> None: ...
    def alive(self) -> bool: ...
    def kill(self) -> None: ...


class Sandbox(Protocol):
    ref: str
    paths: Paths

    def write_file(self, path: str, data: bytes) -> None: ...
    def read_file(self, path: str, limit: int) -> bytes: ...
    def list_outputs(self) -> list[OutputFile]: ...
    def start_runner(self, spec_path: str, env: dict[str, str]) -> RunnerProcess: ...
    def terminate(self) -> None: ...


class SandboxProvider(Protocol):
    name: str

    def create(self, attempt_ref: str, *, timeout_seconds: int, allow_hosts: list[str]) -> Sandbox: ...


# ------------------------------------------------------------------------------------------- local process


class _LocalProcess:
    def __init__(self, process: subprocess.Popen[str]) -> None:
        self.process = process
        self.queue: queue.Queue[str | None] = queue.Queue()
        self.ended = threading.Event()  # set once the end of output has been consumed
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self.queue.put(line.rstrip("\n"))
        self.queue.put(None)

    def lines(self, timeout: float) -> Iterator[str]:
        """Yields lines available within ``timeout``; stops early at end of output."""
        if self.ended.is_set():
            return
        try:
            item = self.queue.get(timeout=timeout)
        except queue.Empty:
            return
        while item is not None:
            yield item
            try:
                item = self.queue.get_nowait()
            except queue.Empty:
                return
        self.ended.set()

    def send(self, line: str) -> None:
        if self.process.stdin and self.process.poll() is None:
            with contextlib.suppress(BrokenPipeError, OSError):
                self.process.stdin.write(line + "\n")
                self.process.stdin.flush()

    def alive(self) -> bool:
        return not self.ended.is_set()

    def kill(self) -> None:
        if self.process.poll() is None:
            self.process.kill()


class _LocalSandbox:
    def __init__(self, ref: str, root: Path, keep_files: bool = False) -> None:
        self.ref = ref
        self.keep_files = keep_files
        self.paths = Paths(
            root=str(root),
            cwd=str(root / "session" / "workspace"),
            outputs=str(root / "session" / "outputs"),
            run=str(root / "run"),
        )
        for p in (self.paths.cwd, self.paths.outputs, self.paths.run, str(root / "home")):
            Path(p).mkdir(parents=True, exist_ok=True)
        self.process: _LocalProcess | None = None

    def write_file(self, path: str, data: bytes) -> None:
        Path(path).write_bytes(data)

    def read_file(self, path: str, limit: int) -> bytes:
        with open(path, "rb") as handle:
            return handle.read(limit + 1)

    def list_outputs(self) -> list[OutputFile]:
        out = []
        for entry in sorted(Path(self.paths.outputs).iterdir()):
            out.append(OutputFile(entry.name, entry.lstat().st_size, entry.is_symlink(), entry.is_file()))
        return out

    def start_runner(self, spec_path: str, env: dict[str, str]) -> RunnerProcess:
        runner_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(Path(self.paths.root) / "home"),
            "PYTHONPATH": str(RUNNER_SRC),
            "LANG": "C.UTF-8",
            **env,
        }
        stderr = open(Path(self.paths.run) / "runner.stderr.log", "w")  # noqa: SIM115 (lives as long as the process)
        process = subprocess.Popen(  # noqa: S603 (fixed argv, explicit env)
            [sys.executable, "-m", "workx_runner", spec_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr,
            text=True,
            cwd=self.paths.cwd,
            env=runner_env,
            bufsize=1,
        )
        self.process = _LocalProcess(process)
        return self.process

    def terminate(self) -> None:
        if self.process:
            self.process.kill()
        if not self.keep_files:
            shutil.rmtree(self.paths.root, ignore_errors=True)


class LocalProcessProvider:
    name = "local_process"

    def __init__(self, base_dir: str | None = None, *, keep_files: bool = False) -> None:
        self.base = Path(base_dir or tempfile.gettempdir()) / "workx-sandboxes"
        self.base.mkdir(parents=True, exist_ok=True)
        self.keep_files = keep_files  # debugging: leave the sandbox directory (and runner.stderr.log) behind

    def create(self, attempt_ref: str, *, timeout_seconds: int, allow_hosts: list[str]) -> Sandbox:
        root = Path(tempfile.mkdtemp(prefix=f"{attempt_ref}-", dir=self.base))
        return _LocalSandbox(root.name, root, self.keep_files)


# ------------------------------------------------------------------------------------------- E2B


class _E2BProcess:
    def __init__(self, sandbox: Any, handle: Any, lines_queue: queue.Queue[str | None]) -> None:
        self.sandbox = sandbox
        self.handle = handle
        self.queue = lines_queue
        self.buffer = ""
        self.finished = threading.Event()
        self.ended = threading.Event()

        def wait() -> None:
            with contextlib.suppress(Exception):
                handle.wait()
            self.queue.put(None)
            self.finished.set()

        threading.Thread(target=wait, daemon=True).start()

    def lines(self, timeout: float) -> Iterator[str]:
        if self.ended.is_set():
            return
        try:
            item = self.queue.get(timeout=timeout)
        except queue.Empty:
            return
        while item is not None:
            yield item
            try:
                item = self.queue.get_nowait()
            except queue.Empty:
                return
        self.ended.set()

    def send(self, line: str) -> None:
        with contextlib.suppress(Exception):
            self.sandbox.commands.send_stdin(self.handle.pid, line + "\n")

    def alive(self) -> bool:
        return not self.ended.is_set()

    def kill(self) -> None:
        with contextlib.suppress(Exception):
            self.handle.kill()


class _E2BSandbox:
    def __init__(self, sandbox: Any) -> None:
        self.sandbox = sandbox
        self.ref = sandbox.sandbox_id
        self.paths = Paths(root="/", cwd="/mnt/session/workspace", outputs="/mnt/session/outputs", run="/run/workx")
        sandbox.commands.run(f"mkdir -p {self.paths.cwd} {self.paths.outputs} {self.paths.run}", timeout=30)

    def write_file(self, path: str, data: bytes) -> None:
        self.sandbox.files.write(path, data)

    def read_file(self, path: str, limit: int) -> bytes:
        data = self.sandbox.files.read(path, format="bytes")
        return bytes(data[: limit + 1])

    def list_outputs(self) -> list[OutputFile]:
        entries = self.sandbox.files.list(self.paths.outputs)
        return [
            OutputFile(
                e.name,
                int(getattr(e, "size", 0) or 0),
                bool(getattr(e, "symlink_target", None)),
                str(e.type).endswith("file"),
            )
            for e in entries
        ]

    def start_runner(self, spec_path: str, env: dict[str, str]) -> RunnerProcess:
        lines: queue.Queue[str | None] = queue.Queue()
        buffer = {"text": ""}

        def on_stdout(chunk: str) -> None:
            buffer["text"] += chunk
            while "\n" in buffer["text"]:
                line, buffer["text"] = buffer["text"].split("\n", 1)
                lines.put(line)

        handle = self.sandbox.commands.run(
            f"workx-runner {spec_path}",
            background=True,
            envs=env,
            cwd=self.paths.cwd,
            on_stdout=on_stdout,
            stdin=True,
            timeout=0,
        )
        return _E2BProcess(self.sandbox, handle, lines)

    def terminate(self) -> None:
        with contextlib.suppress(Exception):
            self.sandbox.kill()


class E2BProvider:
    """Requires the ``e2b`` package and an API key. Egress is denied except the gateway hosts (Part 4 §8)."""

    name = "e2b"

    def __init__(self, api_key: str, template: str) -> None:
        self.api_key = api_key
        self.template = template

    def create(self, attempt_ref: str, *, timeout_seconds: int, allow_hosts: list[str]) -> Sandbox:
        from e2b import Sandbox as E2BSandbox

        sandbox = E2BSandbox.create(
            template=self.template,
            timeout=timeout_seconds,
            metadata={"workx_attempt": attempt_ref},
            api_key=self.api_key,
            network={"allow_out": allow_hosts, "deny_out": ["0.0.0.0/0"]},
        )
        return _E2BSandbox(sandbox)


def gateway_hosts(*urls: str) -> list[str]:
    return sorted({urlparse(u).hostname or "" for u in urls} - {""})
