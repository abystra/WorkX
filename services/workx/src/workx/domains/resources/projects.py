"""Project membership feeds project grants (Part 3 §6.2 "Project" visibility)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from workx.domains.authz import policy
from workx.domains.resources.models import ProjectMember
from workx.domains.tenancy.service import Actor

PROJECT_MEMBER_ACTIONS = {"read", "use", "comment"}


def project_ids_for(session: Session, actor: Actor) -> list[uuid.UUID]:
    return list(
        session.execute(
            select(ProjectMember.project_id).where(
                ProjectMember.tenant_id == actor.tenant.id,
                ProjectMember.membership_id == actor.membership.id,
                ProjectMember.status == "active",
            )
        ).scalars()
    )


policy.register_project_membership(project_ids_for)
