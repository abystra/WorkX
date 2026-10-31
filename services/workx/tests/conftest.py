"""Test infrastructure: a fresh PostgreSQL database per test session (scripts/dev/pg.sh provides the cluster).

Migrations run as the schema owner; the application under test connects as ``workx_app`` so row-level
security and privileges are exercised exactly as in production.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic import command
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from workx.core.db import Database
from workx.core.settings import ApiSettings, Environment, OidcSettings
from workx.entrypoints.api import create_app
from workx.entrypoints.cli import alembic_config
from workx.entrypoints.dev_oidc import create_dev_oidc_app

ISSUER = "http://testserver"
API_BASE = "http://api.test"
WEB_BASE = "http://web.test"

OWNER_URL = os.environ.get(
    "WORKX_TEST_OWNER_URL", "postgresql+psycopg://workx_owner:workx_owner_dev@127.0.0.1:54329/postgres"
)
APP_URL = os.environ.get("WORKX_TEST_APP_URL", "postgresql+psycopg://workx_app:workx_app_dev@127.0.0.1:54329/postgres")
BROKER_URL = os.environ.get(
    "WORKX_TEST_BROKER_URL", "postgresql+psycopg://workx_broker:workx_broker_dev@127.0.0.1:54329/postgres"
)


@dataclass(frozen=True)
class ProvisionedDatabase:
    name: str
    owner_url: str
    app_url: str
    broker_url: str


def _with_db(url: str, name: str) -> str:
    return make_url(url).set(database=name).render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def test_database() -> Iterator[ProvisionedDatabase]:
    name = f"workx_test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(OWNER_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    database = ProvisionedDatabase(name, _with_db(OWNER_URL, name), _with_db(APP_URL, name), _with_db(BROKER_URL, name))
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
        "api_base_url": API_BASE,
        "public_base_url": WEB_BASE,
        "oidc": OidcSettings(issuer=ISSUER, allow_insecure_issuer=True),
        "broker_url": "http://testserver",
    }
    values.update(overrides)
    return ApiSettings(**values)  # type: ignore[arg-type]


@pytest.fixture(scope="session")
def oidc() -> TestClient:
    """In-process development OIDC issuer; also the API's HTTP client for discovery, JWKS and tokens."""
    return TestClient(create_dev_oidc_app(ISSUER, environment=Environment.TEST))


@pytest.fixture(scope="session")
def mail_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("mail")


@pytest.fixture(scope="session")
def objects_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("objects")


@pytest.fixture(scope="session")
def broker_db(test_database: ProvisionedDatabase) -> Iterator[Database]:
    database = Database.connect(test_database.broker_url, pool_size=5)
    yield database
    database.dispose()


@pytest.fixture(scope="session")
def broker_app(test_database: ProvisionedDatabase, broker_db: Database) -> FastAPI:
    from workx.core.settings import TrustedSettings
    from workx.trusted.broker.app import create_broker_app

    settings = TrustedSettings(environment=Environment.TEST, broker_database_url=test_database.broker_url)
    return create_broker_app(settings, broker_db)


@pytest.fixture(scope="session")
def broker_http(broker_app: FastAPI) -> TestClient:
    return TestClient(broker_app)


@pytest.fixture(scope="session")
def api_app(
    test_database: ProvisionedDatabase,
    db: Database,
    oidc: TestClient,
    mail_dir: Path,
    objects_dir: Path,
    broker_http: TestClient,
) -> FastAPI:
    settings = make_settings(test_database, mail_url=f"file:{mail_dir}", object_store_url=f"file:{objects_dir}")
    return create_app(settings, db, oidc_http=oidc, broker_http=broker_http)


@pytest.fixture
def new_client(api_app: FastAPI) -> Callable[[], TestClient]:
    """A fresh browser: its own cookie jar against the same API."""
    return lambda: TestClient(api_app, base_url=API_BASE, raise_server_exceptions=False)


@pytest.fixture
def client(new_client: Callable[[], TestClient]) -> TestClient:
    return new_client()
