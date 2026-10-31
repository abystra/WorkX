"""Database engine and transactions.

Services connect as ``workx_app``, which neither owns tables nor bypasses row-level security. Each unit of
work runs in one transaction; tenant-scoped work sets ``app.tenant_id`` and ``app.principal_id`` with
``SET LOCAL`` so RLS policies apply (Part 3, Part 11).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker


@dataclass(frozen=True)
class Database:
    engine: Engine
    sessions: sessionmaker[Session]

    @classmethod
    def connect(cls, url: str, *, pool_size: int = 10) -> Database:
        engine = create_engine(url, pool_size=pool_size, max_overflow=pool_size, pool_pre_ping=True, future=True)
        return cls(engine, sessionmaker(engine, expire_on_commit=False))

    @contextmanager
    def transaction(
        self, *, tenant_id: uuid.UUID | None = None, principal_id: uuid.UUID | None = None
    ) -> Iterator[Session]:
        with self.sessions() as session, session.begin():
            set_context(session, tenant_id=tenant_id, principal_id=principal_id)
            yield session

    def dispose(self) -> None:
        self.engine.dispose()


def set_context(session: Session, *, tenant_id: uuid.UUID | None, principal_id: uuid.UUID | None) -> None:
    """Sets the RLS context for the current transaction only (``set_config(..., true)`` == SET LOCAL)."""
    session.execute(
        text("SELECT set_config('app.tenant_id', :t, true), set_config('app.principal_id', :p, true)"),
        {"t": str(tenant_id) if tenant_id else "", "p": str(principal_id) if principal_id else ""},
    )
