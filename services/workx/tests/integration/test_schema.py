"""ORM models map onto migration-owned tables: every mapped column must exist with the same nullability."""

import importlib
import pkgutil

from sqlalchemy import inspect

import workx.domains
import workx.platform
from workx.core.db import Database
from workx.core.orm import Base


def _import_all_models() -> None:
    for package in (workx.domains, workx.platform):
        for module in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
            if module.name.endswith(".models"):
                importlib.import_module(module.name)


def test_models_match_migrated_schema(owner_db: Database) -> None:
    _import_all_models()
    inspector = inspect(owner_db.engine)
    problems = []
    for table in Base.metadata.sorted_tables:
        columns = {c["name"]: c for c in inspector.get_columns(table.name)}
        if not columns:
            problems.append(f"missing table {table.name}")
            continue
        for column in table.columns:
            db_column = columns.get(column.name)
            if db_column is None:
                problems.append(f"missing column {table.name}.{column.name}")
            elif bool(db_column["nullable"]) != bool(column.nullable) and not column.primary_key:
                problems.append(f"nullability differs: {table.name}.{column.name}")
    assert not problems, problems
