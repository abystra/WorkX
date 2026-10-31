"""Connection lifecycle rules shared by the API and background jobs (Part 6 §3.3, Seq 8)."""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from workx.core.orm import utcnow
from workx.domains.audit import service as audit
from workx.domains.connections.models import Connection
from workx.platform import outbox


def revoke_leases_for_connection(session: Session, connection_id: uuid.UUID) -> int:
    """Live tickets that may use this connection stop working immediately; gateways re-check epochs too."""
    result = session.execute(
        text(
            "UPDATE credential_leases SET revoked_at = now() "
            "WHERE revoked_at IS NULL AND kind = 'tool' AND scopes -> 'connection_ids' ? :id"
        ),
        {"id": str(connection_id)},
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def change_status(
    session: Session,
    connection: Connection,
    status: str,
    *,
    actor_user_id: uuid.UUID | None,
    actor_membership_id: uuid.UUID | None,
    reason: str,
) -> None:
    if connection.status == status:
        return
    connection.status = status
    connection.authz_epoch += 1
    connection.updated_at = utcnow()
    revoked = revoke_leases_for_connection(session, connection.id) if status in ("revoked", "suspended") else 0
    audit.record(
        session,
        f"connection.{status}",
        tenant_id=connection.tenant_id,
        actor_user_id=actor_user_id,
        actor_membership_id=actor_membership_id,
        target_type="connection",
        target_id=connection.id,
        data={"reason": reason, "tickets_revoked": revoked},
    )
    if status == "revoked":
        # The broker destroys secret versions and requests upstream revocation (job, Part 6 §3.3).
        outbox.emit(
            session,
            "connection.revoked",
            {"connection_id": str(connection.id), "tenant_id": str(connection.tenant_id)},
            tenant_id=connection.tenant_id,
        )
