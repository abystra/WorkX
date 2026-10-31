"""Projects, files (Library), automations, scenarios and sharing routes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, false, func, or_, select
from sqlalchemy.orm import Session

from workx.core import ids
from workx.core.errors import not_found, validation
from workx.core.orm import utcnow
from workx.domains.agents.models import Agent
from workx.domains.audit import service as audit
from workx.domains.authz import policy
from workx.domains.identity.auth import Authenticated, State
from workx.domains.resources import events
from workx.domains.resources.common import active_member_ids, decode, load, maybe, require
from workx.domains.resources.models import Automation, File, FileVersion, Project, ProjectAgent, ProjectMember, Scenario
from workx.domains.resources.projects import PROJECT_MEMBER_ACTIONS, project_ids_for
from workx.domains.tasks.models import Task
from workx.domains.tenancy.api import tenant_uuid
from workx.domains.tenancy.service import Actor, clean_name, tenant_scope

router = APIRouter(tags=["resources"])


def _scope(state: Any, principal: Any, tenant_id: str, write: bool = False) -> Any:
    return tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id), write=write)


def _audit(session: Session, actor: Actor, action: str, kind: str, target: uuid.UUID, **data: Any) -> None:
    audit.record(
        session,
        action,
        tenant_id=actor.tenant.id,
        actor_user_id=actor.user_id,
        actor_membership_id=actor.membership.id,
        target_type=kind,
        target_id=target,
        data=data,
    )


# ---------------------------------------------------------------- projects


class ProjectOut(BaseModel):
    id: str
    name: str
    description: str
    color: str | None
    shared_context: str
    member_ids: list[str]
    agent_ids: list[str]
    task_count: int
    visibility: str
    resource_owner_id: str
    actions: list[str]
    updated_at: datetime


def _project_extra(session: Session, actor: Actor, project: Project) -> set[str]:
    return PROJECT_MEMBER_ACTIONS if project.id in project_ids_for(session, actor) else set()


def _project_out(session: Session, actor: Actor, project: Project, actions: set[str]) -> ProjectOut:
    members = (
        session.execute(
            select(ProjectMember.membership_id).where(
                ProjectMember.project_id == project.id, ProjectMember.status == "active"
            )
        )
        .scalars()
        .all()
    )
    agents = session.execute(select(ProjectAgent.agent_id).where(ProjectAgent.project_id == project.id)).scalars().all()
    tasks = session.execute(
        select(func.count()).select_from(Task).where(Task.project_id == project.id, Task.deleted_at.is_(None))
    ).scalar_one()
    return ProjectOut(
        id=ids.encode("project", project.id),
        name=project.name,
        description=project.description,
        color=project.color,
        shared_context=project.context_md,
        member_ids=[ids.encode("membership", m) for m in members],
        agent_ids=[ids.encode("agent", a) for a in agents],
        task_count=tasks,
        visibility=project.visibility,
        resource_owner_id=ids.encode("membership", project.owner_membership_id),
        actions=sorted(actions),
        updated_at=project.updated_at,
    )


def _readable_projects(session: Session, actor: Actor) -> Any:
    mine = project_ids_for(session, actor)
    return or_(
        policy.readable(
            actor, "project", id_column=Project.id, owner_column=Project.owner_membership_id, project_ids=mine
        ),
        Project.id.in_(mine) if mine else false(),
    )


@router.get("/tenants/{tenant_id}/projects", summary="Projects you own, belong to, or that are shared with you")
def list_projects(tenant_id: str, principal: Authenticated, state: State) -> list[ProjectOut]:
    with _scope(state, principal, tenant_id) as (session, actor):
        rows = (
            session.execute(
                select(Project)
                .where(
                    Project.tenant_id == actor.tenant.id,
                    Project.deleted_at.is_(None),
                    _readable_projects(session, actor),
                )
                .order_by(Project.updated_at.desc())
            )
            .scalars()
            .all()
        )
        return [
            _project_out(
                session,
                actor,
                p,
                policy.allowed_actions(session, actor, "project", p) | _project_extra(session, actor, p),
            )
            for p in rows
        ]


class ProjectIn(BaseModel):
    name: str = Field(max_length=80)
    description: str = Field(default="", max_length=500)
    color: str | None = Field(default=None, max_length=20)


@router.post("/tenants/{tenant_id}/projects", status_code=201, summary="Create a project")
def create_project(tenant_id: str, body: ProjectIn, principal: Authenticated, state: State) -> ProjectOut:
    with _scope(state, principal, tenant_id, write=True) as (session, actor):
        project = Project(
            id=ids.uuid7(),
            tenant_id=actor.tenant.id,
            name=clean_name(body.name, maximum=40),
            description=body.description.strip(),
            color=body.color,
            owner_membership_id=actor.membership.id,
        )
        session.add(project)
        session.flush()
        session.add(
            ProjectMember(
                tenant_id=actor.tenant.id, project_id=project.id, membership_id=actor.membership.id, project_role="lead"
            )
        )
        _audit(session, actor, "project.created", "project", project.id)
        events.publish(session, actor.tenant.id, "project.created", {"project_id": ids.encode("project", project.id)})
        session.flush()
        return _project_out(session, actor, project, set(policy.ACTIONS))


@router.get("/tenants/{tenant_id}/projects/{project_id}", summary="Project detail")
def get_project(tenant_id: str, project_id: str, principal: Authenticated, state: State) -> ProjectOut:
    with _scope(state, principal, tenant_id) as (session, actor):
        project = load(session, Project, actor, project_id, "project")
        return _project_out(
            session,
            actor,
            project,
            require(session, actor, "read", "project", project, _project_extra(session, actor, project)),
        )


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = None
    shared_context: str | None = Field(default=None, max_length=20_000)


@router.patch("/tenants/{tenant_id}/projects/{project_id}", summary="Edit a project or its shared context")
def patch_project(
    tenant_id: str, project_id: str, body: ProjectPatch, principal: Authenticated, state: State
) -> ProjectOut:
    with _scope(state, principal, tenant_id, write=True) as (session, actor):
        project = load(session, Project, actor, project_id, "project", lock=True)
        extra = _project_extra(session, actor, project)
        # Project members maintain the shared context together (prototype project workspace); other fields need edit.
        only_context = body.model_fields_set <= {"shared_context"}
        actions = require(session, actor, "comment" if only_context else "edit", "project", project, extra)
        if body.name is not None:
            project.name = clean_name(body.name, maximum=40)
        if body.description is not None:
            project.description = body.description.strip()
        if "color" in body.model_fields_set:
            project.color = body.color
        if body.shared_context is not None:
            project.context_md = body.shared_context
        project.row_version += 1
        _audit(session, actor, "project.updated", "project", project.id, fields=sorted(body.model_fields_set))
        events.publish(session, actor.tenant.id, "project.updated", {"project_id": project_id})
        session.flush()
        return _project_out(session, actor, project, actions)


class RosterIn(BaseModel):
    member_ids: list[str]
    agent_ids: list[str] = Field(default_factory=list)


@router.put("/tenants/{tenant_id}/projects/{project_id}/roster", summary="Set project members and workmates")
def set_roster(tenant_id: str, project_id: str, body: RosterIn, principal: Authenticated, state: State) -> ProjectOut:
    with _scope(state, principal, tenant_id, write=True) as (session, actor):
        project = load(session, Project, actor, project_id, "project", lock=True)
        actions = require(session, actor, "edit", "project", project, _project_extra(session, actor, project))
        members = {decode("membership", m) for m in body.member_ids} | {project.owner_membership_id}
        if not members <= active_member_ids(session, actor):
            raise validation(
                "Some members are not active in this workspace.",
                data={"field": "member_ids", "code": "project.rosterRequired"},
            )
        agents = {decode("agent", a) for a in body.agent_ids}
        known = (
            set(session.execute(select(Agent.id).where(Agent.id.in_(agents), Agent.deleted_at.is_(None))).scalars())
            if agents
            else set()
        )
        if agents != known:
            raise validation("Unknown workmate.", data={"field": "agent_ids"})
        existing = {
            m.membership_id: m
            for m in session.execute(select(ProjectMember).where(ProjectMember.project_id == project.id)).scalars()
        }
        for membership_id, row in existing.items():
            row.status = "active" if membership_id in members else "removed"
        for membership_id in members - set(existing):
            session.add(ProjectMember(tenant_id=actor.tenant.id, project_id=project.id, membership_id=membership_id))
        session.execute(delete(ProjectAgent).where(ProjectAgent.project_id == project.id))
        for agent_id in agents:
            session.add(ProjectAgent(tenant_id=actor.tenant.id, project_id=project.id, agent_id=agent_id))
        _audit(
            session, actor, "project.roster_changed", "project", project.id, members=len(members), agents=len(agents)
        )
        events.publish(session, actor.tenant.id, "project.updated", {"project_id": project_id})
        session.flush()
        return _project_out(session, actor, project, actions)


@router.delete("/tenants/{tenant_id}/projects/{project_id}", status_code=204, summary="Delete a project")
def delete_project(tenant_id: str, project_id: str, principal: Authenticated, state: State) -> Response:
    with _scope(state, principal, tenant_id, write=True) as (session, actor):
        project = load(session, Project, actor, project_id, "project", lock=True)
        require(session, actor, "delete", "project", project)
        project.deleted_at = utcnow()
        _audit(session, actor, "project.deleted", "project", project.id)
    return Response(status_code=204)


# ---------------------------------------------------------------- files (Library)


class FileOut(BaseModel):
    id: str
    name: str
    kind: str
    media_type: str
    project_id: str | None
    source_task_id: str | None
    content: str | None
    size_bytes: int
    version: int | None
    visibility: str
    resource_owner_id: str
    actions: list[str]
    updated_at: datetime


def _file_out(session: Session, file: File, actions: set[str], *, with_content: bool) -> FileOut:
    version = session.get(FileVersion, file.current_version_id) if file.current_version_id else None
    return FileOut(
        id=ids.encode("file", file.id),
        name=file.name,
        kind=file.kind,
        media_type=file.media_type,
        project_id=maybe("project", file.project_id),
        source_task_id=maybe("task", file.source_task_id),
        content=version.text_content if version and with_content else None,
        size_bytes=version.size_bytes if version else 0,
        version=version.version_no if version else None,
        visibility=file.visibility,
        resource_owner_id=ids.encode("membership", file.owner_membership_id),
        actions=sorted(actions),
        updated_at=file.updated_at,
    )


def _file_extra(session: Session, actor: Actor, file: File) -> set[str]:
    return {"read"} if file.project_id and file.project_id in project_ids_for(session, actor) else set()


@router.get("/tenants/{tenant_id}/files", summary="Library: files you can read")
def list_files(tenant_id: str, principal: Authenticated, state: State, include_content: bool = False) -> list[FileOut]:
    with _scope(state, principal, tenant_id) as (session, actor):
        mine = project_ids_for(session, actor)
        rows = (
            session.execute(
                select(File)
                .where(File.tenant_id == actor.tenant.id, File.deleted_at.is_(None))
                .where(
                    or_(
                        policy.readable(
                            actor, "file", id_column=File.id, owner_column=File.owner_membership_id, project_ids=mine
                        ),
                        File.project_id.in_(mine) if mine else false(),
                    )
                )
                .order_by(File.updated_at.desc())
            )
            .scalars()
            .all()
        )
        return [
            _file_out(
                session,
                f,
                policy.allowed_actions(session, actor, "file", f) | _file_extra(session, actor, f),
                with_content=include_content,
            )
            for f in rows
        ]


class FileIn(BaseModel):
    name: str = Field(max_length=200)
    kind: Literal["doc", "slides", "sheet", "pdf", "image", "other"] = "doc"
    media_type: str = "text/markdown"
    content: str = Field(default="", max_length=2_000_000)
    project_id: str | None = None


def store_text_file(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    owner_membership_id: uuid.UUID,
    name: str,
    kind: str,
    media_type: str,
    content: str,
    project_id: uuid.UUID | None = None,
    source_task_id: uuid.UUID | None = None,
) -> File:
    """Creates a file with one text version. Used by the API and by artifact ingestion."""
    import hashlib

    file = File(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        name=clean_name(name, maximum=200),
        kind=kind,
        media_type=media_type,
        project_id=project_id,
        source_task_id=source_task_id,
        owner_membership_id=owner_membership_id,
    )
    session.add(file)
    session.flush()
    data = content.encode()
    version = FileVersion(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        file_id=file.id,
        version_no=1,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).digest(),
        text_content=content,
        created_by_membership_id=owner_membership_id,
    )
    session.add(version)
    session.flush()
    file.current_version_id = version.id
    return file


def create_text_file(
    session: Session,
    actor: Actor,
    *,
    name: str,
    kind: str,
    media_type: str,
    content: str,
    project_id: uuid.UUID | None = None,
    source_task_id: uuid.UUID | None = None,
) -> File:
    return store_text_file(
        session,
        tenant_id=actor.tenant.id,
        owner_membership_id=actor.membership.id,
        name=name,
        kind=kind,
        media_type=media_type,
        content=content,
        project_id=project_id,
        source_task_id=source_task_id,
    )


@router.post("/tenants/{tenant_id}/files", status_code=201, summary="Create a text file in the Library")
def create_file(tenant_id: str, body: FileIn, principal: Authenticated, state: State) -> FileOut:
    with _scope(state, principal, tenant_id, write=True) as (session, actor):
        project = None
        if body.project_id:
            project = load(session, Project, actor, body.project_id, "project")
            require(session, actor, "read", "project", project, _project_extra(session, actor, project))
        file = create_text_file(
            session,
            actor,
            name=body.name,
            kind=body.kind,
            media_type=body.media_type,
            content=body.content,
            project_id=project.id if project else None,
        )
        _audit(session, actor, "file.created", "file", file.id)
        events.publish(session, actor.tenant.id, "file.created", {"file_id": ids.encode("file", file.id)})
        session.flush()
        return _file_out(session, file, set(policy.ACTIONS), with_content=True)


@router.get("/tenants/{tenant_id}/files/{file_id}", summary="File with its text content")
def get_file(tenant_id: str, file_id: str, principal: Authenticated, state: State) -> FileOut:
    with _scope(state, principal, tenant_id) as (session, actor):
        file = load(session, File, actor, file_id, "file")
        return _file_out(
            session,
            file,
            require(session, actor, "read", "file", file, _file_extra(session, actor, file)),
            with_content=True,
        )


class FilePatch(BaseModel):
    name: str = Field(max_length=200)


@router.patch("/tenants/{tenant_id}/files/{file_id}", summary="Rename a file")
def patch_file(tenant_id: str, file_id: str, body: FilePatch, principal: Authenticated, state: State) -> FileOut:
    with _scope(state, principal, tenant_id, write=True) as (session, actor):
        file = load(session, File, actor, file_id, "file", lock=True)
        actions = require(session, actor, "edit", "file", file, _file_extra(session, actor, file))
        file.name = clean_name(body.name, maximum=200)
        session.flush()
        return _file_out(session, file, actions, with_content=False)


@router.delete("/tenants/{tenant_id}/files/{file_id}", status_code=204, summary="Delete a file")
def delete_file(tenant_id: str, file_id: str, principal: Authenticated, state: State) -> Response:
    with _scope(state, principal, tenant_id, write=True) as (session, actor):
        file = load(session, File, actor, file_id, "file", lock=True)
        require(session, actor, "delete", "file", file)
        file.deleted_at = utcnow()
        _audit(session, actor, "file.deleted", "file", file.id)
    return Response(status_code=204)


# ---------------------------------------------------------------- automations


class AutomationOut(BaseModel):
    id: str
    name: str
    description: str
    schedule: str
    timezone: str
    agent_id: str | None
    prompt: str
    enabled: bool
    next_run_at: datetime | None
    last_run_at: datetime | None
    resource_owner_id: str


def _automation_out(a: Automation) -> AutomationOut:
    return AutomationOut(
        id=ids.encode("automation", a.id),
        name=a.name,
        description=a.description,
        schedule=a.schedule,
        timezone=a.timezone,
        agent_id=maybe("agent", a.agent_id),
        prompt=a.prompt,
        enabled=a.enabled,
        next_run_at=a.next_run_at,
        last_run_at=a.last_run_at,
        resource_owner_id=ids.encode("membership", a.owner_membership_id),
    )


@router.get("/tenants/{tenant_id}/automations", summary="Automations you can see")
def list_automations(tenant_id: str, principal: Authenticated, state: State) -> list[AutomationOut]:
    with _scope(state, principal, tenant_id) as (session, actor):
        rows = session.execute(
            select(Automation)
            .where(Automation.tenant_id == actor.tenant.id, Automation.deleted_at.is_(None))
            .where(
                policy.readable(
                    actor, "automation", id_column=Automation.id, owner_column=Automation.owner_membership_id
                )
            )
            .order_by(Automation.created_at)
        ).scalars()
        return [_automation_out(a) for a in rows]


class AutomationIn(BaseModel):
    name: str = Field(max_length=80)
    description: str = Field(default="", max_length=500)
    schedule: str = Field(min_length=1, max_length=120)
    timezone: str = Field(default="UTC", max_length=64)
    agent_id: str | None = None
    prompt: str = Field(default="", max_length=20_000)
    enabled: bool = True


def _check_agent(session: Session, actor: Actor, agent_id: str | None) -> uuid.UUID | None:
    if not agent_id:
        return None
    agent = load(session, Agent, actor, agent_id, "agent")
    require(session, actor, "use", "agent", agent)
    return agent.id


@router.post("/tenants/{tenant_id}/automations", status_code=201, summary="Create an automation")
def create_automation(tenant_id: str, body: AutomationIn, principal: Authenticated, state: State) -> AutomationOut:
    from workx.domains.resources.schedule import next_run

    with _scope(state, principal, tenant_id, write=True) as (session, actor):
        automation = Automation(
            id=ids.uuid7(),
            tenant_id=actor.tenant.id,
            name=clean_name(body.name, maximum=80),
            description=body.description,
            schedule=body.schedule.strip(),
            timezone=body.timezone,
            agent_id=_check_agent(session, actor, body.agent_id),
            prompt=body.prompt,
            enabled=body.enabled,
            owner_membership_id=actor.membership.id,
            next_run_at=next_run(body.schedule, body.timezone) if body.enabled else None,
        )
        session.add(automation)
        _audit(session, actor, "automation.created", "automation", automation.id)
        session.flush()
        return _automation_out(automation)


class AutomationPatch(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    schedule: str | None = Field(default=None, min_length=1, max_length=120)
    timezone: str | None = Field(default=None, max_length=64)
    agent_id: str | None = None
    prompt: str | None = Field(default=None, max_length=20_000)
    enabled: bool | None = None


@router.patch("/tenants/{tenant_id}/automations/{automation_id}", summary="Edit, pause or resume an automation")
def patch_automation(
    tenant_id: str, automation_id: str, body: AutomationPatch, principal: Authenticated, state: State
) -> AutomationOut:
    from workx.domains.resources.schedule import next_run

    with _scope(state, principal, tenant_id, write=True) as (session, actor):
        automation = load(session, Automation, actor, automation_id, "automation", lock=True)
        require(session, actor, "edit", "automation", automation)
        fields = body.model_dump(exclude_unset=True)
        if "name" in fields:
            automation.name = clean_name(fields["name"], maximum=80)
        for key in ("description", "schedule", "timezone", "prompt", "enabled"):
            if key in fields and fields[key] is not None:
                setattr(automation, key, fields[key])
        if "agent_id" in fields:
            automation.agent_id = _check_agent(session, actor, fields["agent_id"])
        automation.next_run_at = next_run(automation.schedule, automation.timezone) if automation.enabled else None
        _audit(session, actor, "automation.updated", "automation", automation.id, fields=sorted(fields))
        session.flush()
        return _automation_out(automation)


@router.delete("/tenants/{tenant_id}/automations/{automation_id}", status_code=204, summary="Delete an automation")
def delete_automation(tenant_id: str, automation_id: str, principal: Authenticated, state: State) -> Response:
    with _scope(state, principal, tenant_id, write=True) as (session, actor):
        automation = load(session, Automation, actor, automation_id, "automation", lock=True)
        require(session, actor, "delete", "automation", automation)
        automation.deleted_at = utcnow()
        automation.enabled = False
    return Response(status_code=204)


class AutomationRunOut(BaseModel):
    id: str
    slot_at: datetime
    status: str
    reason: str | None
    task_id: str | None


@router.get("/tenants/{tenant_id}/automations/{automation_id}/runs", summary="Scheduled runs of an automation")
def automation_runs(
    tenant_id: str, automation_id: str, principal: Authenticated, state: State
) -> list[AutomationRunOut]:
    from workx.domains.resources.models import AutomationRun

    with _scope(state, principal, tenant_id) as (session, actor):
        automation = load(session, Automation, actor, automation_id, "automation")
        require(session, actor, "read", "automation", automation)
        rows = session.execute(
            select(AutomationRun)
            .where(AutomationRun.automation_id == automation.id)
            .order_by(AutomationRun.slot_at.desc())
            .limit(50)
        ).scalars()
        return [
            AutomationRunOut(
                id=ids.encode("automation_run", r.id),
                slot_at=r.slot_at,
                status=r.status,
                reason=r.reason,
                task_id=ids.encode("task", r.task_id) if r.task_id else None,
            )
            for r in rows
        ]


# ---------------------------------------------------------------- scenarios (business scenario drafts)


class ScenarioOut(BaseModel):
    id: str
    name: str
    problem: str
    role: str
    input: str
    output: str
    ecosystems: list[str]
    updated_at: datetime


class ScenarioIn(BaseModel):
    name: str = Field(max_length=60)
    problem: str = Field(min_length=1, max_length=600)
    role: str = Field(default="", max_length=100)
    input: str = Field(default="", max_length=600)
    output: str = Field(default="", max_length=600)
    ecosystems: list[Literal["feishu", "wecom"]] = Field(default_factory=list)


def _scenario_out(s: Scenario) -> ScenarioOut:
    return ScenarioOut(
        id=ids.encode("scenario", s.id),
        name=s.name,
        problem=s.problem,
        role=s.role,
        input=s.input,
        output=s.output,
        ecosystems=list(s.ecosystems),
        updated_at=s.updated_at,
    )


@router.get("/tenants/{tenant_id}/scenarios", summary="Business scenario drafts")
def list_scenarios(tenant_id: str, principal: Authenticated, state: State) -> list[ScenarioOut]:
    with _scope(state, principal, tenant_id) as (session, actor):
        rows = session.execute(
            select(Scenario)
            .where(Scenario.tenant_id == actor.tenant.id, Scenario.deleted_at.is_(None))
            .where(policy.readable(actor, "scenario", id_column=Scenario.id, owner_column=Scenario.owner_membership_id))
            .order_by(Scenario.created_at.desc())
        ).scalars()
        return [_scenario_out(s) for s in rows]


@router.post("/tenants/{tenant_id}/scenarios", status_code=201, summary="Record a business scenario draft")
def create_scenario(tenant_id: str, body: ScenarioIn, principal: Authenticated, state: State) -> ScenarioOut:
    with _scope(state, principal, tenant_id, write=True) as (session, actor):
        scenario = Scenario(
            id=ids.uuid7(),
            tenant_id=actor.tenant.id,
            name=clean_name(body.name, maximum=60),
            problem=body.problem.strip(),
            role=body.role.strip(),
            input=body.input.strip(),
            output=body.output.strip(),
            ecosystems=list(body.ecosystems),
            owner_membership_id=actor.membership.id,
        )
        session.add(scenario)
        session.flush()
        return _scenario_out(scenario)


@router.patch("/tenants/{tenant_id}/scenarios/{scenario_id}", summary="Edit a scenario draft")
def patch_scenario(
    tenant_id: str, scenario_id: str, body: ScenarioIn, principal: Authenticated, state: State
) -> ScenarioOut:
    with _scope(state, principal, tenant_id, write=True) as (session, actor):
        scenario = load(session, Scenario, actor, scenario_id, "scenario", lock=True)
        require(session, actor, "edit", "scenario", scenario)
        scenario.name = clean_name(body.name, maximum=60)
        scenario.problem, scenario.role = body.problem.strip(), body.role.strip()
        scenario.input, scenario.output, scenario.ecosystems = (
            body.input.strip(),
            body.output.strip(),
            list(body.ecosystems),
        )
        session.flush()
        return _scenario_out(scenario)


@router.delete("/tenants/{tenant_id}/scenarios/{scenario_id}", status_code=204, summary="Delete a scenario draft")
def delete_scenario(tenant_id: str, scenario_id: str, principal: Authenticated, state: State) -> Response:
    with _scope(state, principal, tenant_id, write=True) as (session, actor):
        scenario = load(session, Scenario, actor, scenario_id, "scenario", lock=True)
        require(session, actor, "delete", "scenario", scenario)
        scenario.deleted_at = utcnow()
    return Response(status_code=204)


# ---------------------------------------------------------------- sharing

SHAREABLE: dict[str, tuple[type[Any], str]] = {
    "agents": (Agent, "agent"),
    "projects": (Project, "project"),
    "files": (File, "file"),
    "automations": (Automation, "automation"),
    "tasks": (Task, "task"),
}


class SharingIn(BaseModel):
    visibility: Literal["private", "selected", "project", "organization"]
    member_ids: list[str] = Field(default_factory=list)
    project_id: str | None = None
    actions: list[str] = Field(default_factory=list)


class SharingOut(BaseModel):
    visibility: str
    grants: list[dict[str, Any]]


def _shareable(collection: str) -> tuple[type[Any], str]:
    if collection not in SHAREABLE:
        raise not_found()
    return SHAREABLE[collection]


@router.get("/tenants/{tenant_id}/resources/{collection}/{resource_id}/sharing", summary="Who can access a resource")
def get_sharing(
    tenant_id: str, collection: str, resource_id: str, principal: Authenticated, state: State
) -> SharingOut:
    model, kind = _shareable(collection)
    with _scope(state, principal, tenant_id) as (session, actor):
        row = load(session, model, actor, resource_id, kind)
        require(session, actor, "read", kind, row)
        return SharingOut(**policy.current_sharing(session, actor, kind, row))


@router.put("/tenants/{tenant_id}/resources/{collection}/{resource_id}/sharing", summary="Change sharing (needs share)")
def put_sharing(
    tenant_id: str, collection: str, resource_id: str, body: SharingIn, principal: Authenticated, state: State
) -> SharingOut:
    model, kind = _shareable(collection)
    with _scope(state, principal, tenant_id, write=True) as (session, actor):
        row = load(session, model, actor, resource_id, kind, lock=True)
        project_id = None
        if body.project_id:
            project = load(session, Project, actor, body.project_id, "project")
            require(session, actor, "read", "project", project, _project_extra(session, actor, project))
            project_id = project.id
        row.visibility = policy.set_sharing(
            session,
            actor,
            kind,
            row,
            policy.Sharing(
                body.visibility,
                member_ids=tuple(decode("membership", m) for m in body.member_ids),
                project_id=project_id,
                actions=tuple(body.actions),
            ),
            active_member_ids=active_member_ids(session, actor),
        )
        session.flush()
        events.publish(session, actor.tenant.id, "resource.sharing_changed", {"type": kind, "id": resource_id})
        return SharingOut(**policy.current_sharing(session, actor, kind, row))
