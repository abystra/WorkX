"""Binding resolution at Attempt start (Part 6 §4.2): which tools this initiator may use, and through which
connection. Produces names and ids only; the ticket carries them, the gateway resolves the secret."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from workx.domains.connections.catalog import CONNECTORS, Connector
from workx.domains.connections.models import Connection, ConnectionUsagePolicy, ConnectorInstallation
from workx.domains.tenancy.models import Membership


@dataclass
class Bindings:
    tools: list[str] = field(default_factory=list)
    connections: dict[str, str] = field(default_factory=dict)  # tool → connection id
    epochs: dict[str, int] = field(default_factory=dict)  # connection id → authz_epoch at issue time
    missing_user_auth: list[str] = field(default_factory=list)  # user-identity connectors without a connection


def installed(session: Session, tenant_id: uuid.UUID) -> list[tuple[Connector, ConnectorInstallation | None]]:
    rows = {
        r.connector_id: r
        for r in session.execute(
            select(ConnectorInstallation).where(ConnectorInstallation.tenant_id == tenant_id)
        ).scalars()
    }
    out = []
    for connector in CONNECTORS.values():
        row = rows.get(connector.id)
        if row is not None and not row.enabled:
            continue
        if row is None and not connector.default_installed:
            continue
        out.append((connector, row))
    return out


def _policy_allows(
    policies: list[ConnectionUsagePolicy], member: Membership, project_ids: set[str], agent_id: str, tool: str
) -> bool:
    for policy in policies:
        matches = (
            (policy.principal_type == "tenant")
            or (policy.principal_type == "role" and policy.principal_ref == member.role)
            or (policy.principal_type == "membership" and policy.principal_ref == str(member.id))
            or (policy.principal_type == "project" and policy.principal_ref in project_ids)
            or (policy.principal_type == "agent" and policy.principal_ref == agent_id)
        )
        if matches and tool in policy.allowed_tools:
            return True
    return False


def resolve(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    initiator: Membership,
    agent_id: uuid.UUID,
    project_id: uuid.UUID | None,
    required_connectors: list[str] | None = None,
) -> Bindings:
    bindings = Bindings()
    project_ids = {str(project_id)} if project_id else set()
    for connector, installation in installed(session, tenant_id):
        allowed = (
            set(installation.allowed_tools) if installation and installation.allowed_tools else set(connector.tools)
        )
        tools = [t for t in connector.tools if t in allowed]
        if connector.auth == "none":
            bindings.tools.extend(tools)
            continue
        if connector.identity == "user":
            connection = (
                session.execute(
                    select(Connection)
                    .where(
                        Connection.tenant_id == tenant_id,
                        Connection.connector_id == connector.id,
                        Connection.owner_scope == "member",
                        Connection.owner_membership_id == initiator.id,
                        Connection.status == "active",
                    )
                    .order_by(Connection.updated_at.desc())
                )
                .scalars()
                .first()
            )
            if connection is None:
                if required_connectors and connector.id in required_connectors:
                    bindings.missing_user_auth.append(connector.id)
                continue
            for tool in tools:
                bindings.tools.append(tool)
                bindings.connections[tool] = str(connection.id)
            bindings.epochs[str(connection.id)] = connection.authz_epoch
            continue
        candidates = (
            session.execute(
                select(Connection)
                .where(
                    Connection.tenant_id == tenant_id,
                    Connection.connector_id == connector.id,
                    Connection.owner_scope == "tenant",
                    Connection.status == "active",
                )
                .order_by(Connection.created_at)
            )
            .scalars()
            .all()
        )
        for connection in candidates:
            policies = list(
                session.execute(
                    select(ConnectionUsagePolicy).where(ConnectionUsagePolicy.connection_id == connection.id)
                ).scalars()
            )
            for tool in tools:
                if tool not in bindings.connections and _policy_allows(
                    policies, initiator, project_ids, str(agent_id), tool
                ):
                    bindings.tools.append(tool)
                    bindings.connections[tool] = str(connection.id)
                    bindings.epochs[str(connection.id)] = connection.authz_epoch
    return bindings
