# workx service

Python modular monolith (docs/architecture/10-BACKEND-PLATFORM.md, 12-REPOSITORY.md). One package, several
entrypoints; `workx.trusted` is imported only by trusted entrypoints (enforced by import-linter).

## Local setup

```bash
scripts/dev/pg.sh start          # PostgreSQL 16 on 127.0.0.1:54329 with roles workx_owner / workx_app
uv sync
eval "$(scripts/dev/pg.sh url)"  # WORKX_DATABASE_URL (runtime role) and WORKX_MIGRATION_DATABASE_URL (owner)
uv run workx db upgrade
uv run workx api                 # http://127.0.0.1:8000/healthz, /api/v1/docs
```

## Checks

```bash
scripts/check.sh backend   # ruff, format, mypy --strict, import-linter, OpenAPI freshness, pytest on real PostgreSQL
```

Tests create a throwaway database per session as `workx_owner`, migrate it, and run the app as `workx_app`
(not the owner, `NOBYPASSRLS`), so privileges and row-level security behave as in production.

After changing routes or models, regenerate the committed contract: `uv run workx openapi --write`.
