#!/usr/bin/env bash
# Runs the repository gates locally, as CI does. Usage: scripts/check.sh [backend|web|all]
# Backend needs PostgreSQL with the WorkX roles: scripts/dev/pg.sh start
set -euo pipefail
cd "$(dirname "$0")/.."
target="${1:-all}"

if [ "$target" = backend ] || [ "$target" = all ]; then
  uv run ruff check .
  uv run ruff format --check services runtime
  uv run mypy services/workx/src runtime/runner/src
  uv run lint-imports
  uv run workx openapi --check
  uv run pytest -q
fi

if [ "$target" = web ] || [ "$target" = all ]; then
  (cd apps/web && pnpm typecheck && pnpm test && pnpm build)
fi
