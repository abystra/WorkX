"""Organization SSO policy (R2, Part 3 §3): an organization may require that its members' sessions were
authenticated by its identity provider. Enforced on every tenant-scoped request; the personal workspace and
other organizations are unaffected."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from workx.core import ids
from workx.core.errors import ApiError
from workx.domains.tenancy.models import Membership, Tenant

if TYPE_CHECKING:
    from workx.domains.identity.service import Principal


def login_url(tenant_ref: str, idp_alias: str) -> str:
    return "/api/v1/auth/login?" + urlencode({"idp_hint": idp_alias, "return_to": f"/t/{tenant_ref}/home"})


def satisfied(policy: dict[str, object], idp_alias: str | None) -> bool:
    return not policy.get("required") or (bool(idp_alias) and idp_alias == policy.get("idp_alias"))


def enforce(session: Session, principal: Principal, tenant_ref: str) -> None:
    tenant_id = ids.decode("tenant", tenant_ref)
    if tenant_id is None:
        return  # the route reports the unknown tenant
    policy = session.execute(
        select(Tenant.sso)
        .join(Membership, Membership.tenant_id == Tenant.id)
        .where(Tenant.id == tenant_id, Membership.user_id == principal.user_id, Membership.status == "active")
    ).scalar()
    if policy is None or satisfied(policy, principal.login_session.idp_alias):
        return
    alias = str(policy.get("idp_alias") or "")
    raise ApiError(
        403,
        "TENANT_REAUTH_REQUIRED",
        "This organization requires signing in with its identity provider.",
        data={"idp_hint": alias, "login_url": login_url(tenant_ref, alias)},
    )
