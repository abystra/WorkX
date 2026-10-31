"""Alembic environment. Migrations are hand-written SQL-first revisions; RLS policies and functions are
part of them. They run as the schema owner (``workx_owner``), never as the runtime role."""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, pool

config = context.config


def run() -> None:
    url = config.get_main_option("sqlalchemy.url")
    assert url, "sqlalchemy.url is required"
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, transaction_per_migration=True, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Offline migrations are not supported; run against a database.")
run()
