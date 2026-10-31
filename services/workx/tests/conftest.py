"""Test infrastructure: a fresh PostgreSQL database per test session (scripts/dev/pg.sh provides the cluster).

Migrations run as the schema owner; the application under test connects as ``workx_app`` so row-level
security and privileges are exercised exactly as in production.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from workx.core.db import Database
from workx.core.settings import ApiSettings, Environment
from workx.entrypoints.api import create_app
from workx.entrypoints.cli import alembic_config

OWNER_URL = os.environ.get(
    "WORKX_TEST_OWNER_URL", "postgresql+psycopg://workx_owner:workx_owner_dev@127.0.0.1:54329/postgres"
)
APP_URL = os.environ.get("WORKX_TEST_APP_URL", "postgresql+psycopg://workx_app:workx_app_dev@127.0.0.1:54329/postgres")


@dataclass(frozen=True)
class ProvisionedDatabase:
    name: str
    owner_url: str
    app_url: str


def _with_db(url: str, name: str) -> str:
    return make_url(url).set(database=name).render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def test_database() -> Iterator[ProvisionedDatabase]:
    name = f"workx_test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(OWNER_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    database = ProvisionedDatabase(name, _with_db(OWNER_URL, name), _with_db(APP_URL, name))
    command.upgrade(alembic_config(database.owner_url), "head")
    try:
        yield database
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture(scope="session")
def db(test_database: ProvisionedDatabase) -> Iterator[Database]:
    database = Database.connect(test_database.app_url, pool_size=5)
    yield database
    database.dispose()


@pytest.fixture(scope="session")
def owner_db(test_database: ProvisionedDatabase) -> Iterator[Database]:
    """Schema-owner connection for test setup/inspection only. Bypasses RLS like a migration would."""
    database = Database.connect(test_database.owner_url, pool_size=2)
    yield database
    database.dispose()


def make_settings(test_database: ProvisionedDatabase, **overrides: object) -> ApiSettings:
    values: dict[str, object] = {
        "environment": Environment.TEST,
        "database_url": test_database.app_url,
        "session_cookie_secure": False,
    }
    values.update(overrides)
    return ApiSettings(**values)  # type: ignore[arg-type]


@pytest.fixture
def client(test_database: ProvisionedDatabase, db: Database) -> Iterator[TestClient]:
    app = create_app(make_settings(test_database), db)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
