"""Store a validated file as a new version (or reuse an identical one)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from workx.core import ids
from workx.core.orm import utcnow
from workx.domains.artifacts.validate import Accepted, safe_name, validate
from workx.domains.resources.models import File, FileVersion
from workx.platform.storage import ObjectStore, object_key, sha256


@dataclass(frozen=True)
class Stored:
    file: File
    version: FileVersion
    created: bool
    accepted: Accepted


def store(
    session: Session,
    objects: ObjectStore,
    *,
    tenant_id: uuid.UUID,
    owner_membership_id: uuid.UUID,
    name: str,
    data: bytes,
    project_id: uuid.UUID | None = None,
    source_task_id: uuid.UUID | None = None,
    source_attempt_id: uuid.UUID | None = None,
    completeness: str = "complete",
) -> Stored:
    """Raises ``validate.Rejected``. Task outputs keep one file per (task, name); uploads are always new files."""
    name = safe_name(name)
    accepted = validate(name, data)
    digest = sha256(data)
    file = None
    if source_task_id is not None:
        file = session.execute(
            select(File).where(
                File.tenant_id == tenant_id,
                File.source_task_id == source_task_id,
                File.name == name,
                File.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
    if file is None:
        file = File(
            id=ids.uuid7(),
            tenant_id=tenant_id,
            name=name,
            kind=accepted.kind,
            media_type=accepted.media_type,
            project_id=project_id,
            source_task_id=source_task_id,
            owner_membership_id=owner_membership_id,
        )
        session.add(file)
        session.flush()
    else:
        same = session.execute(
            select(FileVersion).where(FileVersion.file_id == file.id, FileVersion.sha256 == digest)
        ).scalar_one_or_none()
        if same is not None:
            return Stored(file, same, False, accepted)
    number = (
        session.execute(
            select(func.coalesce(func.max(FileVersion.version_no), 0)).where(FileVersion.file_id == file.id)
        ).scalar_one()
        + 1
    )
    key = object_key(tenant_id, file.id, number)
    # The object is written before the row commits, so a visible version always has its bytes.
    objects.put(key, data, accepted.media_type)
    version = FileVersion(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        file_id=file.id,
        version_no=number,
        size_bytes=len(data),
        sha256=digest,
        storage_key=key,
        text_content=accepted.preview,
        media_type=accepted.media_type,
        completeness=completeness,
        source_attempt_id=source_attempt_id,
        validation=accepted.checks,
        created_by_membership_id=owner_membership_id,
        created_at=utcnow(),
    )
    session.add(version)
    session.flush()
    file.current_version_id = version.id
    file.kind, file.media_type, file.updated_at = accepted.kind, accepted.media_type, utcnow()
    return Stored(file, version, True, accepted)


def read(objects: ObjectStore, version: FileVersion) -> bytes:
    if version.storage_key:
        return objects.get(version.storage_key)
    return (version.text_content or "").encode()
