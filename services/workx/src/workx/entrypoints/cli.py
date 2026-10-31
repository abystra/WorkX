"""``workx`` command: run processes, migrate the database, export the OpenAPI contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

SERVICE_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = SERVICE_ROOT.parents[1]
OPENAPI_PATH = REPO_ROOT / "packages" / "contracts" / "openapi" / "workx.v1.yaml"


def alembic_config(url: str | None = None):  # type: ignore[no-untyped-def]
    from alembic.config import Config

    from workx.core.settings import MigrationSettings

    config = Config()
    config.set_main_option("script_location", str(SERVICE_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url or MigrationSettings().migration_database_url)
    return config


def render_openapi() -> str:
    from workx.entrypoints.api import create_app

    spec = create_app().openapi()
    return yaml.safe_dump(json.loads(json.dumps(spec)), sort_keys=False, allow_unicode=True, width=120)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="workx")
    sub = parser.add_subparsers(dest="command", required=True)

    api = sub.add_parser("api", help="run the HTTP API")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8000)
    api.add_argument("--reload", action="store_true")

    db = sub.add_parser("db", help="database migrations")
    db_sub = db.add_subparsers(dest="action", required=True)
    up = db_sub.add_parser("upgrade")
    up.add_argument("revision", nargs="?", default="head")
    down = db_sub.add_parser("downgrade")
    down.add_argument("revision")
    db_sub.add_parser("current")

    dev = sub.add_parser("dev-oidc", help="run the local development OIDC issuer (never in production)")
    dev.add_argument("--host", default="127.0.0.1")
    dev.add_argument("--port", type=int, default=8100)
    dev.add_argument("--issuer", default="")

    oa = sub.add_parser("openapi", help="write or check packages/contracts/openapi/workx.v1.yaml")
    mode = oa.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "api":
        import uvicorn

        from workx.core.logging import configure
        from workx.core.settings import ApiSettings

        settings = ApiSettings()
        configure(settings.log_level)
        uvicorn.run(
            "workx.entrypoints.api:create_app", factory=True, host=args.host, port=args.port, reload=args.reload
        )
        return 0

    if args.command == "dev-oidc":
        import uvicorn

        from workx.core.settings import BaseWorkxSettings
        from workx.entrypoints.dev_oidc import create_dev_oidc_app

        issuer = args.issuer or f"http://{args.host}:{args.port}"
        uvicorn.run(
            create_dev_oidc_app(issuer, environment=BaseWorkxSettings().environment), host=args.host, port=args.port
        )
        return 0

    if args.command == "db":
        from alembic import command

        config = alembic_config()
        if args.action == "upgrade":
            command.upgrade(config, args.revision)
        elif args.action == "downgrade":
            command.downgrade(config, args.revision)
        else:
            command.current(config, verbose=True)
        return 0

    if args.command == "openapi":
        rendered = render_openapi()
        if args.write:
            OPENAPI_PATH.parent.mkdir(parents=True, exist_ok=True)
            OPENAPI_PATH.write_text(rendered, encoding="utf-8")
            print(f"wrote {OPENAPI_PATH.relative_to(REPO_ROOT)}")
            return 0
        current = OPENAPI_PATH.read_text(encoding="utf-8") if OPENAPI_PATH.exists() else ""
        if current != rendered:
            print(
                "OpenAPI contract is stale: run `uv run workx openapi --write` and commit the result.", file=sys.stderr
            )
            return 1
        print("OpenAPI contract is up to date.")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
