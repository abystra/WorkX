import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

from tests.conftest import ProvisionedDatabase
from workx.entrypoints.cli import alembic_config


def test_downgrade_to_base_and_back(test_database: ProvisionedDatabase) -> None:
    config = alembic_config(test_database.owner_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine(test_database.owner_url)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT workx_tenant_id()")).scalar() is None
    engine.dispose()


def test_runtime_role_cannot_create_objects(test_database: ProvisionedDatabase) -> None:
    engine = create_engine(test_database.app_url)
    with engine.connect() as conn, pytest.raises(ProgrammingError):
        conn.execute(text("CREATE TABLE should_fail (id int)"))
    with engine.connect() as conn:
        role = conn.execute(text("SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname = current_user")).one()
    assert role == (False, False)
    engine.dispose()


def test_rls_context_is_transaction_local(test_database: ProvisionedDatabase) -> None:
    import uuid

    from workx.core.db import Database

    db = Database.connect(test_database.app_url, pool_size=1)
    tenant = uuid.uuid4()
    with db.transaction(tenant_id=tenant) as session:
        assert session.execute(text("SELECT workx_tenant_id()")).scalar() == tenant
    with db.transaction() as session:
        assert session.execute(text("SELECT workx_tenant_id()")).scalar() is None
    db.dispose()
