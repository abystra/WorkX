#!/usr/bin/env bash
# Local full stack against the real API: development OIDC issuer, API, worker, orchestrator, broker, model and
# tool gateways, test CRM, web (integration mode).
#   scripts/dev/stack.sh start | stop | status
# Web: http://127.0.0.1:5174 (proxies /api to the API on :8000). Sign in with any email at the dev issuer.
# Model: with WORKX_ANTHROPIC_API_KEY and WORKX_MODEL_TIERS set, tasks use the real Anthropic API and the
# Claude Agent SDK engine; otherwise a scripted development model answers (clearly fake) via the messages engine.
# Test CRM: connect it in the app (Ecosystem › CRM) with the key "dev-crm-key" (or WORKX_DEV_CRM_KEY).
# Logs and pid files: .local/run/. Requires scripts/dev/pg.sh start and a migrated database.
set -euo pipefail
cd "$(dirname "$0")/../.."
RUN=.local/run
mkdir -p "$RUN"
WEB=http://127.0.0.1:5174

start_one() {
  local name="$1"; shift
  if [ -f "$RUN/$name.pid" ] && kill -0 "$(cat "$RUN/$name.pid")" 2>/dev/null; then echo "$name already running"; return; fi
  # Own process group, so stop also ends grandchildren (npx → node, uv → python).
  setsid nohup "$@" > "$RUN/$name.log" 2>&1 &
  echo $! > "$RUN/$name.pid"
  echo "$name started (pid $(cat "$RUN/$name.pid"), log $RUN/$name.log)"
}

case "${1:-start}" in
  start)
    eval "$(scripts/dev/pg.sh url)"
    export WORKX_OIDC_ISSUER=http://127.0.0.1:8100 WORKX_OIDC_ALLOW_INSECURE_ISSUER=true WORKX_SESSION_COOKIE_SECURE=false
    export WORKX_API_BASE_URL=$WEB WORKX_PUBLIC_BASE_URL=$WEB WORKX_MAIL_URL="file:$RUN/mail"
    uv run workx db upgrade
    export WORKX_CRM_BASE_URL=http://127.0.0.1:8300 WORKX_BROKER_URL=http://127.0.0.1:8220
    export WORKX_MODEL_GATEWAY_URL=http://127.0.0.1:8200 WORKX_TOOL_GATEWAY_URL=http://127.0.0.1:8210
    if [ -n "${WORKX_ANTHROPIC_API_KEY:-}" ] && [ -n "${WORKX_MODEL_TIERS:-}" ]; then
      export WORKX_RUNNER_ENGINE=claude-agent-sdk
    else
      export WORKX_ANTHROPIC_BASE_URL=http://127.0.0.1:8400 WORKX_ANTHROPIC_API_KEY=sk-upstream-test-key-0123456789
      export WORKX_MODEL_TIERS='{"auto": "dev-model", "opus": "dev-model", "sonnet": "dev-model", "haiku": "dev-model"}'
      export WORKX_RUNNER_ENGINE=messages
      start_one dev-model uv run workx dev-model --port 8400
    fi
    start_one dev-oidc uv run workx dev-oidc --port 8100
    start_one dev-crm uv run workx dev-crm --port 8300
    start_one broker uv run workx broker --port 8220
    start_one api uv run workx api --port 8000
    start_one worker uv run workx worker
    start_one model-gateway uv run workx model-gateway --port 8200
    start_one tool-gateway uv run workx tool-gateway --port 8210
    start_one orchestrator uv run workx orchestrator
    start_one web bash -c "cd apps/web && exec npx vite --mode integration --port 5174 --strictPort"
    echo "Open $WEB"
    ;;
  stop)
    for name in web orchestrator tool-gateway model-gateway worker api broker dev-crm dev-oidc dev-model; do
      if [ -f "$RUN/$name.pid" ]; then
        kill -- "-$(cat "$RUN/$name.pid")" 2>/dev/null || kill "$(cat "$RUN/$name.pid")" 2>/dev/null || true
        rm -f "$RUN/$name.pid"
        echo "$name stopped"
      fi
    done
    ;;
  status)
    for name in dev-oidc dev-model dev-crm broker api worker model-gateway tool-gateway orchestrator web; do
      if [ -f "$RUN/$name.pid" ] && kill -0 "$(cat "$RUN/$name.pid")" 2>/dev/null; then echo "$name running"; else echo "$name stopped"; fi
    done
    ;;
  *) echo "usage: $0 start|stop|status" >&2; exit 2 ;;
esac
