"""Part 3 §6.2 resource authorization: owner, grants, admins without grants, expiry, SQL/Python parity."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from tests.integration.test_tenancy import add_member, create_org
from tests.support.auth import sign_in
from workx.core import ids
from workx.core.db import Database
from workx.core.errors import ApiError
from workx.core.orm import utcnow
from workx.domains.authz import policy
from workx.domains.authz.models import ResourceGrant
from workx.domains.tenancy import service as tenancy


@dataclass(frozen=True)
class Thing:
    """A stand-in resource; real resource tables arrive with P-04 and use the same columns."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    owner_membership_id: uuid.UUID | None


@dataclass
class Org:
    tenant_id: uuid.UUID
    users: dict[str, uuid.UUID]
    members: dict[str, uuid.UUID]


@pytest.fixture
def org(new_client: Callable[[], TestClient], oidc: TestClient, owner_db: Database) -> Org:
    owner = new_client()
    owner_me = sign_in(owner, oidc)
    created = create_org(owner)
    users = {"owner": ids.decode("user", owner_me["id"])}
    members: dict[str, uuid.UUID] = {}
    for name, role in (("admin", "admin"), ("alice", "member"), ("bob", "member")):
        client = new_client()
        me = sign_in(client, oidc)
        users[name] = ids.decode("user", me["id"])  # type: ignore[assignment]
        members[name] = ids.decode("membership", add_member(owner_db, created["id"], me["id"], role))  # type: ignore[assignment]
    tid = ids.decode("tenant", created["id"])
    assert tid
    return Org(tid, users, members)  # type: ignore[arg-type]


@pytest.fixture
def actor_of(db: Database, org: Org) -> Iterator[Callable[[str], tuple[tenancy.Actor, object]]]:
    sessions = []

    def make(name: str) -> tuple[tenancy.Actor, object]:
        context = db.transaction(principal_id=org.users[name])
        session = context.__enter__()
        sessions.append(context)
        return tenancy.enter(session, user_id=org.users[name], tenant_id=org.tenant_id), session

    yield make
    for context in sessions:
        context.__exit__(None, None, None)


def test_owner_admin_member_and_grants(actor_of: Callable[[str], tuple[tenancy.Actor, object]], org: Org) -> None:
    alice, alice_session = actor_of("alice")
    thing = Thing(uuid.uuid4(), org.tenant_id, alice.membership.id)
    assert policy.allowed_actions(alice_session, alice, "agent", thing) == set(policy.ACTIONS)  # type: ignore[arg-type]

    admin, admin_session = actor_of("admin")
    # Management role grants no content access (Part 3 §6.2).
    assert policy.allowed_actions(admin_session, admin, "agent", thing) == set()  # type: ignore[arg-type]
    with pytest.raises(ApiError) as hidden:
        policy.authorize(admin_session, admin, "read", "agent", thing)  # type: ignore[arg-type]
    assert hidden.value.status == 404

    policy.set_sharing(
        alice_session,
        alice,
        "agent",
        thing,  # type: ignore[arg-type]
        policy.Sharing("selected", member_ids=(org.members["bob"],)),
        active_member_ids=set(org.members.values()),
    )
    alice_session.commit()  # type: ignore[attr-defined]
    bob, bob_session = actor_of("bob")
    assert policy.allowed_actions(bob_session, bob, "agent", thing) == {"read", "use"}  # type: ignore[arg-type]
    with pytest.raises(ApiError) as denied:
        policy.authorize(bob_session, bob, "edit", "agent", thing)  # type: ignore[arg-type]
    assert denied.value.status == 403
    assert policy.allowed_actions(admin_session, admin, "agent", thing) == set()  # type: ignore[arg-type]


def test_organization_visibility_and_explicit_actions(
    actor_of: Callable[[str], tuple[tenancy.Actor, object]], org: Org
) -> None:
    alice, session = actor_of("alice")
    thing = Thing(uuid.uuid4(), org.tenant_id, alice.membership.id)
    policy.set_sharing(
        session,
        alice,
        "agent",
        thing,
        policy.Sharing("organization", actions=("edit",)),  # type: ignore[arg-type]
        active_member_ids=set(org.members.values()),
    )
    session.commit()  # type: ignore[attr-defined]
    admin, admin_session = actor_of("admin")
    assert policy.allowed_actions(admin_session, admin, "agent", thing) == {"read", "use", "edit"}  # type: ignore[arg-type]
    assert policy.current_sharing(admin_session, admin, "agent", thing)["visibility"] == "organization"  # type: ignore[arg-type]
    bob, bob_session = actor_of("bob")
    with pytest.raises(ApiError) as no_share:
        policy.set_sharing(
            bob_session,
            bob,
            "agent",
            thing,
            policy.Sharing("private"),
            active_member_ids=set(),  # type: ignore[arg-type]
        )
    assert no_share.value.status == 403


def test_expired_grants_and_list_filter(
    actor_of: Callable[[str], tuple[tenancy.Actor, object]], org: Org, owner_db: Database
) -> None:
    alice, _ = actor_of("alice")
    shared, private = (
        Thing(uuid.uuid4(), org.tenant_id, alice.membership.id),
        Thing(uuid.uuid4(), org.tenant_id, alice.membership.id),
    )
    with owner_db.transaction() as owner_session:
        for thing, expires in ((shared, utcnow() + timedelta(hours=1)), (private, utcnow() - timedelta(seconds=1))):
            owner_session.add(
                ResourceGrant(
                    id=ids.uuid7(),
                    tenant_id=org.tenant_id,
                    resource_type="agent",
                    resource_id=thing.id,
                    principal_type="membership",
                    principal_id=org.members["bob"],
                    actions=["read"],
                    expires_at=expires,
                )
            )
    bob, bob_session = actor_of("bob")
    assert policy.allowed_actions(bob_session, bob, "agent", shared) == {"read"}  # type: ignore[arg-type]
    assert policy.allowed_actions(bob_session, bob, "agent", private) == set()  # type: ignore[arg-type]
    # The SQL list filter agrees: build a VALUES list of candidate ids and filter it.
    candidates = (
        text("SELECT * FROM (VALUES (:a, :o), (:b, :o)) AS t(id, owner)")
        .bindparams(a=shared.id, b=private.id, o=alice.membership.id)
        .columns(id=ResourceGrant.resource_id.type, owner=ResourceGrant.principal_id.type)
        .subquery()
    )
    visible = (
        bob_session.execute(  # type: ignore[attr-defined]
            select(candidates.c.id).where(
                policy.readable(bob, "agent", id_column=candidates.c.id, owner_column=candidates.c.owner)
            )
        )
        .scalars()
        .all()
    )
    assert visible == [shared.id]


def test_personal_workspaces_stay_private(new_client: Callable[[], TestClient], oidc: TestClient, db: Database) -> None:
    client = new_client()
    me = sign_in(client, oidc)
    personal = ids.decode("tenant", client.get("/api/v1/me/tenants").json()[0]["id"])
    user = ids.decode("user", me["id"])
    assert personal and user
    with db.transaction(principal_id=user) as session:
        actor = tenancy.enter(session, user_id=user, tenant_id=personal)
        thing = Thing(uuid.uuid4(), personal, actor.membership.id)
        with pytest.raises(ApiError) as refused:
            policy.set_sharing(session, actor, "agent", thing, policy.Sharing("organization"), active_member_ids=set())
        assert refused.value.code == "VALIDATION_FAILED"


def test_sql_workx_can_matches_python(actor_of: Callable[[str], tuple[tenancy.Actor, object]], org: Org) -> None:
    alice, session = actor_of("alice")
    things = [Thing(uuid.uuid4(), org.tenant_id, alice.membership.id) for _ in range(3)]
    member_ids = set(org.members.values())
    policy.set_sharing(
        session,
        alice,
        "agent",
        things[0],
        policy.Sharing("selected", member_ids=(org.members["bob"],)),
        active_member_ids=member_ids,
    )  # type: ignore[arg-type]
    policy.set_sharing(
        session,
        alice,
        "agent",
        things[1],
        policy.Sharing("organization", actions=("export",)),
        active_member_ids=member_ids,
    )  # type: ignore[arg-type]
    session.commit()  # type: ignore[attr-defined]
    for name in ("alice", "bob", "admin"):
        actor, actor_session = actor_of(name)
        for thing in things:
            python_actions = policy.allowed_actions(actor_session, actor, "agent", thing)  # type: ignore[arg-type]
            for action in policy.ACTIONS:
                sql = actor_session.execute(  # type: ignore[attr-defined]
                    text("SELECT workx_can(:t, :m, :o, 'agent', :r, :a)"),
                    {
                        "t": org.tenant_id,
                        "m": actor.membership.id,
                        "o": thing.owner_membership_id,
                        "r": thing.id,
                        "a": action,
                    },
                ).scalar()
                assert sql == (action in python_actions), (name, thing, action)
