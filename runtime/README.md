# Agent runtime

| Path | What it is |
| --- | --- |
| `runner/` | `workx-runner`: runs one Attempt inside the sandbox and speaks protocol v1 (`packages/contracts/runner-protocol`). Never imports the control plane. Engines: `claude-agent-sdk` (production) and `messages` (development and tests). |
| `e2b-template/` | E2B template definition: Runner with the Agent SDK (bundled Claude Code CLI), office libraries, a non-root `agent` user, no credentials. |
| `skills/` | Curated Skills (reviewed SDK plugins), copied into the template. |

The control-plane side lives in `services/workx`:

- Orchestrator, sandbox providers and tickets: `domains/runtime`.
- Model Gateway and Tool Gateway: `trusted/`.

## What has been verified, and where

These are covered by automated tests on every run (`scripts/check.sh backend`). The tests use real PostgreSQL, real gateway HTTP servers, and the Runner as a subprocess:

- `tests/runtime/test_vertical_slice.py`, using the `messages` engine:
  - the end-to-end slice: CRM tool calls, file output, usage metering, the canary check that the Runner's environment holds only two tickets;
  - cancel, with ticket revocation;
  - a crashed orchestrator ending as `interrupted`, then a retry with the next fence and no duplicate CRM write;
  - approve and reject;
  - the budget stop;
  - SSRF protection;
  - ticket and model scoping;
  - cross-tenant 404s.
- `tests/runtime/test_sdk_engine.py`: the **production engine**. The Claude Agent SDK and its bundled Claude Code CLI run through the real Model Gateway and Tool Gateway (an MCP tool call to the CRM, then an answer), and only the pinned model reaches upstream.

In both suites, the upstream model is `workx dev-model`, a scripted stand-in for the Messages API. **The real Anthropic API and E2B have not been exercised in this environment** (no credentials).

### Real model through the gateway (opt-in test)

`tests/runtime/test_real_model.py` runs the slice with a real model service behind the Model Gateway, for both engines. It runs only when these are set; the key stays in the environment and reaches only the Model Gateway:

```bash
export WORKX_REAL_MODEL_BASE_URL=https://api.anthropic.com WORKX_REAL_MODEL_API_KEY=<key> WORKX_REAL_MODEL=<model id>
```

```bash
uv run pytest services/workx/tests/runtime/test_real_model.py -s
```

It checks that the task succeeds, the model chose to call the CRM tool through the Tool Gateway, the answer names the top account, tokens were metered, and the Runner's environment held only tickets.

**Result on 2026-10-31 (not Anthropic):** run against DeepSeek's Anthropic-compatible endpoint (`deepseek-chat`), the only real model service reachable here. Both engines passed:

- `messages`: one CRM call, about 1,050 tokens metered;
- `claude-agent-sdk` (bundled Claude Code CLI): two tool calls (tool schema loading, then the CRM), about 11,600 tokens metered.

This verifies the real-model path through the platform (gateway, tickets, streaming, MCP tools, metering) with a real model. It does not verify Anthropic itself: the product's model tiers are Claude models (decision D-01), and that run is still outstanding.

## Real-service verification (run where credentials exist)

### 1. Anthropic API, with local sandboxes

```bash
export WORKX_ANTHROPIC_API_KEY=<key> WORKX_MODEL_TIERS='{"auto": "<model id>", "opus": "<id>", "sonnet": "<id>", "haiku": "<id>"}'
```

```bash
scripts/dev/stack.sh start
```

Open http://127.0.0.1:5174, sign in, and start a task such as "List our top CRM accounts and save them to a file". Expected:

- the conversation shows the tool steps, the answer and a file card;
- `GET /api/v1/tenants/{t}/tasks/{id}/events` lists `run.started` with `engine=claude-agent-sdk`, then `tool.started` and `tool.finished` (CRM), then `task.succeeded`;
- `usage_events` has `model_tokens` for the task.

### 2. E2B sandboxes

1. Build the template:

   ```bash
   WORKX_E2B_TEMPLATE=workx-runtime E2B_API_KEY=<key> uv run --with e2b python runtime/e2b-template/template.py build
   ```

2. Deploy the gateways at URLs the sandbox can reach (public HTTPS), and set:

   ```bash
   export WORKX_SANDBOX_PROVIDER=e2b WORKX_E2B_API_KEY=<key> WORKX_MODEL_GATEWAY_URL=https://model.gw.example WORKX_TOOL_GATEWAY_URL=https://tools.gw.example
   ```

3. Repeat the task from step 1, then check these acceptance points (Part 14 §2):
   - **Egress:** inside the sandbox, `curl https://example.com` fails, while the gateway hosts answer.
   - **Credentials:** `env` and `/proc/*/environ` in the sandbox contain only `WORKX_*_TICKET`, never an Anthropic or connector key.
   - **Cancel:** cancelling mid-run ends with `task.cancelled`, and the sandbox is terminated (`e2b sandbox list`).
   - **Crash recovery:** killing the orchestrator mid-run gives `interrupted` within the lease (60 s). A manual retry then runs as attempt 2 with fence 2 and does not repeat CRM writes (`GET /_stats` on the test CRM).
