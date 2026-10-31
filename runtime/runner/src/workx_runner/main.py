"""``workx-runner <runspec.json>``: run one Attempt and exit.

Tickets are read from the environment variables named in the RunSpec, then removed from this process's
environment so tools started by the agent do not inherit them.
"""

from __future__ import annotations

import os
import sys
import traceback

from workx_runner.protocol import Control, Emitter
from workx_runner.spec import RunSpec


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("usage: workx-runner <runspec.json>", file=sys.stderr)
        return 2
    spec = RunSpec.load(args[0])
    emitter = Emitter(spec["attempt_id"], int(spec["fencing_token"]))
    model_ticket = os.environ.pop(spec["model_gateway"]["ticket_env"], "")
    tool_ticket = os.environ.pop(spec["tool_gateway"]["ticket_env"], "")
    control = Control()
    control.start()
    os.makedirs(spec["outputs_dir"], exist_ok=True)
    os.makedirs(spec["cwd"], exist_ok=True)
    try:
        if spec["engine"] == "claude-agent-sdk":
            from workx_runner.engine_sdk import SdkEngine

            reason = SdkEngine(spec, emitter, control, model_ticket, tool_ticket).run()
        else:
            from workx_runner.engine_messages import MessagesEngine

            engine = MessagesEngine(spec, emitter, control, model_ticket, tool_ticket)
            reason = engine.run()
            emitter.emit("run.usage", {"usage": engine.usage})
    except Exception as exc:
        emitter.emit(
            "run.error", {"detail": f"{type(exc).__name__}: {exc}"[:500], "trace": traceback.format_exc()[-2000:]}
        )
        reason = "error"
    emitter.emit("run.finished", {"reason": reason})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
