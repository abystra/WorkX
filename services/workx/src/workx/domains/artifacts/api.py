"""File download, versions and upload (Library). Bytes only flow through the API after authorization."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Form, Response, UploadFile
from fastapi import File as FormFile
from pydantic import BaseModel
from sqlalchemy import select

from workx.core import ids
from workx.core.errors import ApiError, not_found, validation
from workx.domains.artifacts import service
from workx.domains.artifacts.validate import Rejected
from workx.domains.audit import service as audit
from workx.domains.identity.auth import Authenticated, State
from workx.domains.resources import events
from workx.domains.resources.api import FileOut, _file_extra, _file_out, _project_extra
from workx.domains.resources.common import load, require
from workx.domains.resources.models import File, FileVersion, Project
from workx.domains.tenancy.api import tenant_uuid
from workx.domains.tenancy.service import tenant_scope
from workx.platform import storage

router = APIRouter(tags=["files"])
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def objects(state: object) -> storage.ObjectStore:
    store: storage.ObjectStore = state.services["objects"]  # type: ignore[attr-defined]
    return store


@router.get(
    "/tenants/{tenant_id}/files/{file_id}/content",
    summary="Download a file (current or a given version)",
    response_class=Response,
)
def download(
    tenant_id: str, file_id: str, principal: Authenticated, state: State, version: int | None = None
) -> Response:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id)) as (session, actor):
        file = load(session, File, actor, file_id, "file")
        require(session, actor, "read", "file", file, _file_extra(session, actor, file))
        query = select(FileVersion).where(FileVersion.file_id == file.id)
        query = (
            query.where(FileVersion.version_no == version)
            if version
            else query.where(FileVersion.id == file.current_version_id)
        )
        row = session.execute(query).scalar_one_or_none()
        if row is None:
            raise not_found()
        audit.record(
            session,
            "file.downloaded",
            tenant_id=actor.tenant.id,
            actor_user_id=actor.user_id,
            actor_membership_id=actor.membership.id,
            target_type="file",
            target_id=file.id,
            data={"version": row.version_no},
        )
        name, media_type = file.name, row.media_type or file.media_type
    data = service.read(objects(state), row)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}",
        "X-Content-Type-Options": "nosniff",
        # Never let a downloaded document run script in the app's origin.
        "Content-Security-Policy": "sandbox; default-src 'none'",
        "Cache-Control": "private, no-store",
    }
    return Response(data, media_type=media_type, headers=headers)


class VersionOut(BaseModel):
    version: int
    size_bytes: int
    media_type: str | None
    completeness: str
    created_at: datetime


@router.get("/tenants/{tenant_id}/files/{file_id}/versions", summary="File versions")
def versions(tenant_id: str, file_id: str, principal: Authenticated, state: State) -> list[VersionOut]:
    with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id)) as (session, actor):
        file = load(session, File, actor, file_id, "file")
        require(session, actor, "read", "file", file, _file_extra(session, actor, file))
        rows = session.execute(
            select(FileVersion).where(FileVersion.file_id == file.id).order_by(FileVersion.version_no.desc())
        ).scalars()
        return [
            VersionOut(
                version=v.version_no,
                size_bytes=v.size_bytes,
                media_type=v.media_type,
                completeness=v.completeness,
                created_at=v.created_at,
            )
            for v in rows
        ]


@router.post(
    "/tenants/{tenant_id}/files/upload", status_code=201, summary="Upload a file to the Library (validated by content)"
)
async def upload(
    tenant_id: str,
    principal: Authenticated,
    state: State,
    file: Annotated[UploadFile, FormFile()],
    project_id: Annotated[str | None, Form()] = None,
) -> FileOut:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ApiError(413, "FILE_TOO_LARGE", "Files up to 25 MB can be uploaded here.")
    from starlette.concurrency import run_in_threadpool

    def save() -> FileOut:
        with tenant_scope(state.db, user_id=principal.user_id, tenant_id=tenant_uuid(tenant_id), write=True) as (
            session,
            actor,
        ):
            project = None
            if project_id:
                project = load(session, Project, actor, project_id, "project")
                require(session, actor, "use", "project", project, _project_extra(session, actor, project))
            try:
                stored = service.store(
                    session,
                    objects(state),
                    tenant_id=actor.tenant.id,
                    owner_membership_id=actor.membership.id,
                    name=file.filename or "upload",
                    data=data,
                    project_id=project.id if project else None,
                )
            except Rejected as exc:
                raise ApiError(
                    422,
                    "UNSUPPORTED_FILE_TYPE",
                    "This file type or content is not accepted.",
                    data={"reason": exc.reason},
                ) from exc
            audit.record(
                session,
                "file.uploaded",
                tenant_id=actor.tenant.id,
                actor_user_id=actor.user_id,
                actor_membership_id=actor.membership.id,
                target_type="file",
                target_id=stored.file.id,
                data={"kind": stored.accepted.kind, "size": len(data)},
            )
            events.publish(session, actor.tenant.id, "file.created", {"file_id": ids.encode("file", stored.file.id)})
            from workx.domains.authz import policy

            return _file_out(session, stored.file, set(policy.ACTIONS), with_content=True)

    if not data:
        raise validation("The file is empty.", data={"field": "file"})
    return await run_in_threadpool(save)
