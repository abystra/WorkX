"""Connector installations, connections and usage policies (Part 6 §2-§4, Part 3 §6.1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from workx.core import ids
from workx.core.errors import ApiError, conflict, forbidden, not_found, validation
from workx.domains.audit import service as audit
from workx.domains.connections import catalog, resolve, service
from workx.domains.connections.broker_client import BrokerClient
from workx.domains.connections.models import Connection, ConnectionUsagePolicy, ConnectorInstallation
from workx.domains.identity.auth import Authenticated, State, current_principal
from workx.domains.identity.service import safe_return_to
from workx.domains.resources import events
from workx.domains.resources.common import decode
from workx.domains.tenancy.api import tenant_uuid
from workx.domains.tenancy.service import Actor, clean_name, tenant_scope
from workx.platform.web import AppState

router = APIRouter(tags=["connections"])


def broker(state: AppState) -> BrokerClient:
    client: BrokerClient = state.services["broker"]
    return client


def _manager_or_personal_owner(actor: Actor) -> bool:
    return actor.is_manager or (actor.tenant.type == "personal" and actor.role == "owner")


class ConnectorOut(BaseModel):
    id: str
    name: str
    cls: str
    auth: str
    identity: str
    tools: list[str]
    installed: bool
    enabled: bool
    allowed_tools: list[str] | None
    # Settings an owner/admin provides when installing (client_secret goes to the client-secret endpoint).
    config_fields: list[str] = Field(default_factory=list)


@router.get("/tenants/{tenant_id}/connectors", summary="Connector catalog and this workspace's installations")
def connectors(tenant_id: str, principal: Authenticated, state: State) -> list[ConnectorOut]:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id)) as (session, actor):
        rows = {
            r.connector_id: r
            for r in session.execute(
                select(ConnectorInstallation).where(ConnectorInstallation.tenant_id == actor.tenant.id)
            ).scalars()
        }
        out = []
        for c in catalog.CONNECTORS.values():
            row = rows.get(c.id)
            installed = row is not None or c.default_installed
            out.append(
                ConnectorOut(
                    id=c.id,
                    name=c.name,
                    cls=c.cls,
                    auth=c.auth,
                    identity=c.identity,
                    tools=list(c.tools),
                    installed=installed,
                    enabled=bool(row.enabled) if row else c.default_installed,
                    allowed_tools=row.allowed_tools if row else None,
                    config_fields=list(c.config_fields),
                )
            )
        return out


class InstallationIn(BaseModel):
    enabled: bool = True
    allowed_tools: list[str] | None = None
    config: dict[str, str] = Field(default_factory=dict)


@router.put(
    "/tenants/{tenant_id}/connectors/{connector_id}/installation", summary="Install, configure or disable a connector"
)
def install(
    tenant_id: str, connector_id: str, body: InstallationIn, principal: Authenticated, state: State
) -> ConnectorOut:
    connector = catalog.get(connector_id)
    if connector is None:
        raise not_found()
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id), write=True) as (
        session,
        actor,
    ):
        if not _manager_or_personal_owner(actor):
            raise forbidden("Only owners and admins can install connectors.")
        if body.allowed_tools is not None and not set(body.allowed_tools) <= set(connector.tools):
            raise validation("Unknown tool for this connector.", data={"field": "allowed_tools"})
        unknown = set(body.config) - set(connector.config_fields)
        if unknown:
            raise validation(f"Unknown settings: {', '.join(sorted(unknown))}", data={"field": "config"})
        row = session.get(ConnectorInstallation, (actor.tenant.id, connector.id)) or ConnectorInstallation(
            tenant_id=actor.tenant.id, connector_id=connector.id, installed_by_membership_id=actor.membership.id
        )
        # Secret settings (client secrets) never live in installation config; they go to the broker.
        if "client_secret" in body.config:
            raise validation("Send client secrets through the connection's secret endpoint.", data={"field": "config"})
        row.enabled, row.allowed_tools, row.config = body.enabled, body.allowed_tools, body.config
        session.add(row)
        audit.record(
            session,
            "connector.installation_changed",
            tenant_id=actor.tenant.id,
            actor_user_id=actor.user_id,
            actor_membership_id=actor.membership.id,
            data={"connector": connector.id, "enabled": body.enabled},
        )
        return ConnectorOut(
            id=connector.id,
            name=connector.name,
            cls=connector.cls,
            auth=connector.auth,
            identity=connector.identity,
            tools=list(connector.tools),
            installed=True,
            enabled=body.enabled,
            allowed_tools=body.allowed_tools,
            config_fields=list(connector.config_fields),
        )


class ConnectionOut(BaseModel):
    id: str
    connector_id: str
    connector_name: str
    auth: str
    name: str
    scope: Literal["member", "tenant"]
    owner_id: str
    status: str
    external_account: str | None
    granted_scopes: list[str]
    last_used_at: datetime | None
    created_at: datetime
    mine: bool
    # Workmates named in the usage policy (shared connections); the UI shows them as "bound workmates".
    agent_ids: list[str] = Field(default_factory=list)


def _encode_ref(principal_type: str, ref: str) -> str:
    if principal_type in ("membership", "project", "agent"):
        return ids.encode(principal_type, uuid.UUID(ref))
    return ref


def _agent_ids(session: Session, connection_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    out: dict[uuid.UUID, list[str]] = {}
    if not connection_ids:
        return out
    for row in session.execute(
        select(ConnectionUsagePolicy).where(
            ConnectionUsagePolicy.connection_id.in_(connection_ids), ConnectionUsagePolicy.principal_type == "agent"
        )
    ).scalars():
        out.setdefault(row.connection_id, []).append(_encode_ref("agent", row.principal_ref))
    return out


def _out(c: Connection, actor: Actor, agent_ids: list[str] | None = None) -> ConnectionOut:
    connector = catalog.CONNECTORS[c.connector_id]
    return ConnectionOut(
        id=ids.encode("connection", c.id),
        connector_id=c.connector_id,
        connector_name=connector.name,
        auth=connector.auth,
        name=c.name,
        scope=c.owner_scope,
        owner_id=ids.encode("membership", c.owner_membership_id),
        status=c.status,
        external_account=c.external_account,
        granted_scopes=list(c.granted_scopes),
        last_used_at=c.last_used_at,
        created_at=c.created_at,
        mine=c.owner_membership_id == actor.membership.id,
        agent_ids=agent_ids or [],
    )


def _one(session: Session, c: Connection, actor: Actor) -> ConnectionOut:
    return _out(c, actor, _agent_ids(session, [c.id]).get(c.id))


@router.get(
    "/tenants/{tenant_id}/connections", summary="Connections: yours, shared ones, and (for admins) all metadata"
)
def list_connections(tenant_id: str, principal: Authenticated, state: State) -> list[ConnectionOut]:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id)) as (session, actor):
        query = select(Connection).where(Connection.tenant_id == actor.tenant.id, Connection.status != "revoked")
        if not actor.is_manager:
            query = query.where(
                or_(Connection.owner_membership_id == actor.membership.id, Connection.owner_scope == "tenant")
            )
        rows = list(session.execute(query.order_by(Connection.created_at)).scalars())
        agents = _agent_ids(session, [c.id for c in rows])
        return [_out(c, actor, agents.get(c.id)) for c in rows]


class ConnectionIn(BaseModel):
    connector_id: str
    name: str = Field(max_length=80)
    scope: Literal["member", "tenant"] = "member"
    secret: str | None = Field(default=None, max_length=8192)


def _load(session: object, actor: Actor, connection_id: str) -> Connection:
    row = session.get(Connection, decode("connection", connection_id), with_for_update=True)  # type: ignore[attr-defined]
    if row is None or row.tenant_id != actor.tenant.id or row.status == "revoked":
        raise not_found()
    if not (actor.is_manager or row.owner_membership_id == actor.membership.id):
        raise not_found()
    return row  # type: ignore[no-any-return]


@router.post(
    "/tenants/{tenant_id}/connections", status_code=201, summary="Create a connection (API keys go to the broker)"
)
def create_connection(tenant_id: str, body: ConnectionIn, principal: Authenticated, state: State) -> ConnectionOut:
    connector = catalog.get(body.connector_id)
    if connector is None or connector.auth == "none":
        raise validation("This connector does not use connections.", data={"field": "connector_id"})
    tid = tenant_uuid(tenant_id)
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tid, write=True) as (session, actor):
        if body.connector_id not in {c.id for c, _ in resolve.installed(session, tid)}:
            raise conflict("CONNECTOR_NOT_INSTALLED", "Install this connector in the workspace first.")
        if body.scope == "tenant" and not _manager_or_personal_owner(actor):
            raise forbidden("Only owners and admins can create shared connections.")
        if connector.identity == "user" and body.scope == "tenant":
            raise validation("This connector acts as each member; connect it per member.", data={"field": "scope"})
        if connector.auth == "api_key" and not body.secret:
            raise validation("Enter the API key.", data={"field": "secret"})
        connection = Connection(
            id=ids.uuid7(),
            tenant_id=actor.tenant.id,
            connector_id=connector.id,
            name=clean_name(body.name, maximum=80),
            owner_scope=body.scope,
            owner_membership_id=actor.membership.id,
            status="pending",
        )
        session.add(connection)
        session.flush()
        audit.record(
            session,
            "connection.created",
            tenant_id=actor.tenant.id,
            actor_user_id=actor.user_id,
            actor_membership_id=actor.membership.id,
            target_type="connection",
            target_id=connection.id,
            data={"connector": connector.id, "scope": body.scope},
        )
        connection_id, membership_id = connection.id, actor.membership.id
    if body.secret:
        broker(state).put_secret(
            tenant_id=tid, connection_id=connection_id, actor_membership_id=membership_id, value=body.secret
        )
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tid) as (session, actor):
        return _one(session, _load(session, actor, ids.encode("connection", connection_id)), actor)


class SecretIn(BaseModel):
    secret: str = Field(min_length=1, max_length=8192)


@router.post("/tenants/{tenant_id}/connections/{connection_id}/secret", summary="Rotate the connection's API key")
def rotate(tenant_id: str, connection_id: str, body: SecretIn, principal: Authenticated, state: State) -> ConnectionOut:
    tid = tenant_uuid(tenant_id)
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tid, write=True) as (session, actor):
        connection = _load(session, actor, connection_id)
        if catalog.CONNECTORS[connection.connector_id].auth != "api_key":
            raise conflict("INVALID_STATE", "Reconnect OAuth connections instead.")
        membership_id = actor.membership.id
    broker(state).put_secret(
        tenant_id=tid,
        connection_id=decode("connection", connection_id),
        actor_membership_id=membership_id,
        value=body.secret,
    )
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tid) as (session, actor):
        return _one(session, _load(session, actor, connection_id), actor)


class ConnectionPatch(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    status: Literal["active", "suspended"] | None = None


@router.patch("/tenants/{tenant_id}/connections/{connection_id}", summary="Rename, pause or resume a connection")
def patch_connection(
    tenant_id: str, connection_id: str, body: ConnectionPatch, principal: Authenticated, state: State
) -> ConnectionOut:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id), write=True) as (
        session,
        actor,
    ):
        connection = _load(session, actor, connection_id)
        if body.name is not None:
            connection.name = clean_name(body.name, maximum=80)
        if body.status is not None:
            if body.status == "active" and connection.status not in ("suspended", "active"):
                raise conflict("INVALID_STATE", "Only paused connections can be resumed.")
            service.change_status(
                session,
                connection,
                body.status,
                actor_user_id=actor.user_id,
                actor_membership_id=actor.membership.id,
                reason="manual",
            )
        session.flush()
        events.publish(session, actor.tenant.id, "connection.updated", {"connection_id": connection_id})
        return _one(session, connection, actor)


@router.delete(
    "/tenants/{tenant_id}/connections/{connection_id}", status_code=204, summary="Revoke a connection (admins: any)"
)
def revoke(tenant_id: str, connection_id: str, principal: Authenticated, state: State) -> Response:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id), write=True) as (
        session,
        actor,
    ):
        connection = _load(session, actor, connection_id)
        service.change_status(
            session,
            connection,
            "revoked",
            actor_user_id=actor.user_id,
            actor_membership_id=actor.membership.id,
            reason="manual",
        )
        events.publish(session, actor.tenant.id, "connection.updated", {"connection_id": connection_id})
    return Response(status_code=204)


class PolicyRule(BaseModel):
    principal_type: Literal["role", "membership", "project", "agent", "tenant"]
    principal_ref: str = ""
    allowed_tools: list[str]


@router.get("/tenants/{tenant_id}/connections/{connection_id}/usage-policy", summary="Who may use a shared connection")
def get_policy(tenant_id: str, connection_id: str, principal: Authenticated, state: State) -> list[PolicyRule]:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id)) as (session, actor):
        connection = _load(session, actor, connection_id)
        rows = session.execute(
            select(ConnectionUsagePolicy).where(ConnectionUsagePolicy.connection_id == connection.id)
        ).scalars()
        return [
            PolicyRule(
                principal_type=r.principal_type,
                principal_ref=_encode_ref(r.principal_type, r.principal_ref),
                allowed_tools=list(r.allowed_tools),
            )
            for r in rows
        ]


@router.put(
    "/tenants/{tenant_id}/connections/{connection_id}/usage-policy", summary="Set who may use a shared connection"
)
def put_policy(
    tenant_id: str, connection_id: str, body: list[PolicyRule], principal: Authenticated, state: State
) -> list[PolicyRule]:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id), write=True) as (
        session,
        actor,
    ):
        connection = _load(session, actor, connection_id)
        if connection.owner_scope != "tenant":
            raise conflict("INVALID_STATE", "Member connections are used only by their owner.")
        if not _manager_or_personal_owner(actor):
            raise forbidden()
        tools = set(catalog.CONNECTORS[connection.connector_id].tools)
        session.execute(delete(ConnectionUsagePolicy).where(ConnectionUsagePolicy.connection_id == connection.id))
        for rule in body:
            if not set(rule.allowed_tools) <= tools:
                raise validation("Unknown tool for this connector.", data={"field": "allowed_tools"})
            ref = rule.principal_ref
            if rule.principal_type in ("membership", "project", "agent"):
                kind = {"membership": "membership", "project": "project", "agent": "agent"}[rule.principal_type]
                ref = str(decode(kind, rule.principal_ref))
            elif rule.principal_type == "role" and ref not in ("owner", "admin", "member"):
                raise validation("Unknown role.", data={"field": "principal_ref"})
            session.add(
                ConnectionUsagePolicy(
                    id=ids.uuid7(),
                    tenant_id=actor.tenant.id,
                    connection_id=connection.id,
                    principal_type=rule.principal_type,
                    principal_ref=ref,
                    allowed_tools=sorted(set(rule.allowed_tools)),
                )
            )
        # Narrowing who may use the connection takes effect for running tasks too.
        connection.authz_epoch += 1
        service.revoke_leases_for_connection(session, connection.id)
        audit.record(
            session,
            "connection.policy_changed",
            tenant_id=actor.tenant.id,
            actor_user_id=actor.user_id,
            actor_membership_id=actor.membership.id,
            target_type="connection",
            target_id=connection.id,
            data={"rules": len(body)},
        )
        return body


class ClientSecretIn(BaseModel):
    secret: str = Field(min_length=1, max_length=8192)


@router.put(
    "/tenants/{tenant_id}/connectors/{connector_id}/client-secret",
    status_code=204,
    summary="Set an OAuth connector's client secret (stored by the broker, never returned)",
)
def put_client_secret(
    tenant_id: str, connector_id: str, body: ClientSecretIn, principal: Authenticated, state: State
) -> Response:
    connector = catalog.get(connector_id)
    if connector is None or connector.oauth is None:
        raise not_found()
    tid = tenant_uuid(tenant_id)
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tid) as (session, actor):
        if not _manager_or_personal_owner(actor):
            raise forbidden("Only owners and admins can configure connectors.")
        if session.get(ConnectorInstallation, (tid, connector_id)) is None:
            raise conflict("CONNECTOR_NOT_INSTALLED", "Install this connector in the workspace first.")
        membership_id = actor.membership.id
    broker(state).put_installation_secret(
        tenant_id=tid, connector_id=connector_id, actor_membership_id=membership_id, value=body.secret
    )
    return Response(status_code=204)


class AuthorizeIn(BaseModel):
    return_to: str = Field(default="/", max_length=2000)


class AuthorizeOut(BaseModel):
    authorize_url: str


@router.post(
    "/tenants/{tenant_id}/connections/{connection_id}/authorize",
    summary="Start OAuth for your connection: open the returned URL in the browser",
)
def authorize(
    tenant_id: str, connection_id: str, body: AuthorizeIn, principal: Authenticated, state: State
) -> AuthorizeOut:
    tid = tenant_uuid(tenant_id)
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tid) as (session, actor):
        connection = _load(session, actor, connection_id)
        connector = catalog.CONNECTORS[connection.connector_id]
        if connector.auth != "oauth":
            raise conflict("INVALID_STATE", "This connection does not use OAuth.")
        if connection.owner_membership_id != actor.membership.id:
            raise forbidden("Only the person who owns this connection can authorize it.")
        connection_uuid, membership_id = connection.id, actor.membership.id
    started = broker(state).oauth_start(
        {
            "tenant_id": str(tid),
            "connection_id": str(connection_uuid),
            "membership_id": str(membership_id),
            "redirect_uri": f"{state.settings.api_base_url.rstrip('/')}/api/v1/oauth/callback",
            "return_to": safe_return_to(body.return_to),
        }
    )
    return AuthorizeOut(authorize_url=str(started["authorize_url"]))


@router.get(
    "/oauth/callback",
    summary="OAuth redirect target for connections (browser navigation)",
    response_class=RedirectResponse,
    status_code=303,
)
def oauth_callback(
    request: Request, state: State, code: str | None = None, error: str | None = None, state_param: str = ""
) -> RedirectResponse:
    web = state.settings.public_base_url.rstrip("/")
    oauth_state = request.query_params.get("state", state_param)
    try:
        principal = current_principal(request, state)
    except Exception:
        return RedirectResponse(f"{web}/session-expired", status_code=303)
    try:
        result = broker(state).oauth_complete(
            {"state": oauth_state, "code": code, "error": error, "user_id": str(principal.user_id)}
        )
    except ApiError:
        return RedirectResponse(f"{web}/?connection=invalid", status_code=303)
    target = safe_return_to(str(result.get("return_to") or "/"))
    separator = "&" if "?" in target else "?"
    return RedirectResponse(f"{web}{target}{separator}connection={result.get('status', 'failed')}", status_code=303)
