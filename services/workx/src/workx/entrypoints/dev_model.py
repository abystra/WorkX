"""``workx dev-model``: a scripted stand-in for the Anthropic Messages API (streaming), for local development
and tests behind the real Model Gateway. It never runs in staging or production.

The script is chosen by a marker in the user's request (SCENARIO:<name>) and advances by counting the
tool results already in the conversation, the way a real model would continue after each tool call.
It records the API key and model it received so tests can prove the gateway injected the real key.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Iterator
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from workx.core.settings import Environment

UPSTREAM_KEY = "sk-upstream-test-key-0123456789"

SCRIPTS: dict[str, list[dict[str, Any]]] = {
    "slice": [
        {"text": "Let me look up the accounts.", "tool": ("crm_list_accounts", {"limit": 3})},
        {"tool": ("crm_create_note", {"account_id": "acc_001", "text": "Top account this quarter"})},
        {
            "tool": (
                "write_output_file",
                {
                    "name": "top-accounts.md",
                    "content": "# Top accounts\n\n1. Northwind Traders\n2. Contoso Ltd\n3. Fabrikam\n",
                },
            )
        },
        {"text": "Here are your top accounts. I saved them to top-accounts.md and noted Northwind in the CRM."},
    ],
    "slow": [
        {"tool": ("crm_create_note", {"account_id": "acc_002", "text": "Follow up"})},
        {"text": "Thinking hard about this", "delay": 30},
    ],
    "approval": [
        {"tool": ("crm_send_email", {"account_id": "acc_003", "subject": "Renewal", "body": "Shall we renew?"})},
        {"text": "Done."},
    ],
    "ssrf": [
        {"tool": ("web_fetch", {"url": "http://127.0.0.1:1/admin"})},
        {"text": "I could not fetch that page."},
    ],
    "sdk": [
        {"text": "Checking the CRM.", "tool": ("mcp__workx__crm_list_accounts", {"limit": 2})},
        {"text": "Northwind Traders and Contoso Ltd are your top accounts."},
    ],
    "xlsx": [
        {
            "text": "Creating the spreadsheet.",
            "tool": (
                "Bash",
                {
                    "command": (
                        'python3 -c "import openpyxl; b = openpyxl.Workbook(); s = b.active; '
                        "s.append(['Account', 'Revenue']); s.append(['Northwind Traders', 4200000]); "
                        "s.append(['Contoso Ltd', 3100000]); b.save('{outputs}/top-accounts.xlsx')\""
                    ),
                    "description": "Create top-accounts.xlsx",
                },
            ),
        },
        {"text": "I saved top-accounts.xlsx with your two largest accounts."},
    ],
    "forbidden_tool": [
        {"tool": ("delete_everything", {})},
        {"text": "That tool is not available."},
    ],
}


def _scenario(body: dict[str, Any]) -> str:
    for message in body.get("messages", []):
        content = message.get("content")
        texts = (
            [content] if isinstance(content, str) else [c.get("text", "") for c in content or [] if isinstance(c, dict)]
        )
        for text in texts:
            if "SCENARIO:" in text:
                return text.split("SCENARIO:", 1)[1].split()[0]
    return "slice"


def _outputs_dir(body: dict[str, Any]) -> str:
    match = re.search(r"Save files for the user in (\S+?)\.(?:\s|\"|$)", json.dumps(body))
    return match.group(1) if match else "/mnt/session/outputs"


def _fill(value: Any, outputs: str) -> Any:
    if isinstance(value, str):
        return value.replace("{outputs}", outputs)
    if isinstance(value, dict):
        return {k: _fill(v, outputs) for k, v in value.items()}
    return value


def _step(body: dict[str, Any]) -> int:
    count = 0
    for message in body.get("messages", []):
        if message.get("role") == "user" and isinstance(message.get("content"), list):
            count += sum(1 for c in message["content"] if isinstance(c, dict) and c.get("type") == "tool_result")
    return count


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def create_dev_model_app(*, key: str = UPSTREAM_KEY, environment: Environment = Environment.DEVELOPMENT) -> FastAPI:
    if environment in (Environment.STAGING, Environment.PRODUCTION):
        raise RuntimeError("The development model must not run in staging or production.")
    app = FastAPI(title="WorkX development model", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.seen = []

    @app.post("/v1/messages", response_model=None)
    async def messages(request: Request) -> Any:
        body = await request.json()
        app.state.seen.append(
            {"key": request.headers.get("x-api-key"), "model": body.get("model"), "step": _step(body)}
        )
        if request.headers.get("x-api-key") != key:
            return JSONResponse(
                {"type": "error", "error": {"type": "authentication_error", "message": "bad key"}}, status_code=401
            )
        script = SCRIPTS[_scenario(body)]
        step = script[min(_step(body), len(script) - 1)]

        def stream() -> Iterator[str]:
            message_id = f"msg_{uuid.uuid4().hex[:12]}"
            yield _sse(
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": message_id,
                        "type": "message",
                        "role": "assistant",
                        "content": [],
                        "model": body["model"],
                        "usage": {"input_tokens": 100, "output_tokens": 1},
                    },
                },
            )
            index = 0
            if "text" in step:
                yield _sse(
                    "content_block_start",
                    {"type": "content_block_start", "index": index, "content_block": {"type": "text", "text": ""}},
                )
                for word in step["text"].split(" "):
                    yield _sse(
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": index,
                            "delta": {"type": "text_delta", "text": word + " "},
                        },
                    )
                    if step.get("delay"):
                        time.sleep(step["delay"] / max(len(step["text"].split(" ")), 1))
                yield _sse("content_block_stop", {"type": "content_block_stop", "index": index})
                index += 1
            if "tool" in step:
                name, args = step["tool"]
                args = _fill(args, _outputs_dir(body))
                yield _sse(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": index,
                        "content_block": {
                            "type": "tool_use",
                            "id": f"toolu_{uuid.uuid4().hex[:8]}",
                            "name": name,
                            "input": {},
                        },
                    },
                )
                raw = json.dumps(args)
                yield _sse(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": index,
                        "delta": {"type": "input_json_delta", "partial_json": raw[: len(raw) // 2]},
                    },
                )
                yield _sse(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": index,
                        "delta": {"type": "input_json_delta", "partial_json": raw[len(raw) // 2 :]},
                    },
                )
                yield _sse("content_block_stop", {"type": "content_block_stop", "index": index})
            stop = "tool_use" if "tool" in step else "end_turn"
            yield _sse(
                "message_delta",
                {"type": "message_delta", "delta": {"stop_reason": stop}, "usage": {"output_tokens": 50}},
            )
            yield _sse("message_stop", {"type": "message_stop"})

        return StreamingResponse(stream(), media_type="text/event-stream")

    return app
