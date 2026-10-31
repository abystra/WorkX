#!/usr/bin/env bash
# Local full stack against the real API: development OIDC issuer, API, worker, web (integration mode).
#   scripts/dev/stack.sh start | stop | status
# Web: http://127.0.0.1:5174 (proxies /api to the API on :8000). Sign in with any email at the dev issuer.
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
    start_one dev-oidc uv run workx dev-oidc --port 8100
    start_one api uv run workx api --port 8000
    start_one worker uv run workx worker
    start_one web bash -c "cd apps/web && exec npx vite --mode integration --port 5174 --strictPort"
    echo "Open $WEB"
    ;;
  stop)
    for name in web worker api dev-oidc; do
      if [ -f "$RUN/$name.pid" ]; then
        kill -- "-$(cat "$RUN/$name.pid")" 2>/dev/null || kill "$(cat "$RUN/$name.pid")" 2>/dev/null || true
        rm -f "$RUN/$name.pid"
        echo "$name stopped"
      fi
    done
    ;;
  status)
    for name in dev-oidc api worker web; do
      if [ -f "$RUN/$name.pid" ] && kill -0 "$(cat "$RUN/$name.pid")" 2>/dev/null; then echo "$name running"; else echo "$name stopped"; fi
    done
    ;;
  *) echo "usage: $0 start|stop|status" >&2; exit 2 ;;
esac
