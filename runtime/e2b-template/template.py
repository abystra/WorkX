"""E2B template for WorkX Attempts (Part 4 §5, Part 5; backlog B-09).

Build (needs an E2B API key):        python runtime/e2b-template/template.py build
Inspect offline (no network needed): python runtime/e2b-template/template.py dockerfile

The image contains the Runner with the Claude Agent SDK (which bundles the Claude Code CLI) and the libraries
curated Skills use for office formats. It contains no credentials: tickets arrive per Attempt in the Runner's
environment, and egress is denied except the gateways when the sandbox is created (domains/runtime/sandbox.py).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from e2b import Template

REPO = Path(__file__).resolve().parents[2]
ALIAS = os.environ.get("WORKX_E2B_TEMPLATE", "workx-runtime")
OFFICE_LIBRARIES = ["openpyxl", "python-docx", "python-pptx", "pypdf", "pandas", "matplotlib"]


def definition() -> object:
    return (
        Template(file_context_path=str(REPO))
        .from_python_image("3.12")
        .run_cmd(
            [
                "useradd --create-home --uid 1000 agent",
                "mkdir -p /mnt/session/workspace /mnt/session/outputs /run/workx /mnt/skills",
                "chown -R agent:agent /mnt/session /run/workx",
            ],
            user="root",
        )
        .copy("runtime/runner", "/opt/workx-runner", user="root")
        .copy("runtime/skills", "/mnt/skills", user="root")
        .run_cmd("pip install --no-cache-dir '/opt/workx-runner[sdk]' && rm -rf /opt/workx-runner", user="root")
        .pip_install(OFFICE_LIBRARIES)
        .set_envs(
            {
                "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                "DISABLE_TELEMETRY": "1",
            }
        )
        .set_user("agent")
        .set_workdir("/mnt/session/workspace")
    )


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else "dockerfile"
    template = definition()
    if command == "dockerfile":
        print(Template.to_dockerfile(template))  # type: ignore[arg-type]
        return 0
    if command == "build":
        info = Template.build(template, alias=ALIAS, cpu_count=2, memory_mb=4096)  # type: ignore[arg-type]
        print(f"built {ALIAS}: {info}")
        return 0
    print("usage: template.py dockerfile|build", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
