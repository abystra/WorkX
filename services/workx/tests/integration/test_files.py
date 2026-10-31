"""Library files on the real API: upload validated by content, authorized download, versions, ingestion."""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.integration.test_tenancy import create_org
from tests.support.auth import idem, sign_in
from tests.unit.test_artifact_validation import xlsx
from workx.core import ids
from workx.core.db import Database
from workx.domains.resources.models import FileVersion
from workx.domains.runtime.orchestrator import Orchestrator
from workx.domains.runtime.sandbox import OutputFile, Paths
from workx.domains.tasks.models import Task
from workx.platform.storage import FilesystemStore


def test_upload_download_versions_and_isolation(
    new_client: Callable[[], TestClient], oidc: TestClient, owner_db: Database, objects_dir: Path
) -> None:
    owner, stranger = new_client(), new_client()
    sign_in(owner, oidc)
    sign_in(stranger, oidc)
    org = create_org(owner)
    base = f"/api/v1/tenants/{org['id']}/files"
    data = xlsx()
    uploaded = owner.post(f"{base}/upload", files={"file": ("../Q3 accounts.xlsx", data, "application/octet-stream")})
    assert uploaded.status_code == 201, uploaded.text
    body = uploaded.json()
    assert body["name"] == "Q3 accounts.xlsx" and body["kind"] == "sheet" and "Northwind Traders" in body["content"]
    download = owner.get(f"{base}/{body['id']}/content")
    assert download.status_code == 200 and download.content == data
    assert download.headers["x-content-type-options"] == "nosniff"
    assert download.headers["content-disposition"].startswith("attachment; filename*=UTF-8''Q3%20accounts.xlsx")
    assert "sandbox" in download.headers["content-security-policy"]
    assert owner.get(f"{base}/{body['id']}/versions").json()[0]["version"] == 1
    # Another workspace's user cannot list, read or download it.
    for path in (f"{base}/{body['id']}", f"{base}/{body['id']}/content", f"{base}/{body['id']}/versions"):
        assert stranger.get(path).status_code == 404
    # The object is stored under the tenant's prefix, not at a guessable public location.
    with owner_db.transaction() as session:
        key = session.execute(
            select(FileVersion.storage_key).where(FileVersion.file_id == ids.decode("file", body["id"]))
        ).scalar_one()
    assert key.startswith(f"t/{ids.decode('tenant', org['id'])}/files/") and (objects_dir / key).exists()
    rejected = owner.post(f"{base}/upload", files={"file": ("macro.xlsm", data, "application/octet-stream")})
    assert rejected.status_code == 422 and rejected.json()["data"]["reason"] == "macros_not_allowed"


@dataclass
class FakeSandbox:
    root: Path

    @property
    def paths(self) -> Paths:
        return Paths(str(self.root), str(self.root / "ws"), str(self.root / "out"), str(self.root / "run"))

    def list_outputs(self) -> list[OutputFile]:
        out = []
        for entry in sorted((self.root / "out").iterdir()):
            out.append(
                OutputFile(
                    entry.name, entry.lstat().st_size, entry.is_symlink(), entry.is_file() and not entry.is_symlink()
                )
            )
        return out

    def read_file(self, path: str, limit: int) -> bytes:
        with open(path, "rb") as handle:
            return handle.read(limit + 1)


def test_ingestion_rejects_unsafe_outputs_and_dedupes_retries(
    new_client: Callable[[], TestClient], oidc: TestClient, db: Database, tmp_path: Path, objects_dir: Path
) -> None:
    client = new_client()
    sign_in(client, oidc)
    org = create_org(client)
    agent = client.get(f"/api/v1/tenants/{org['id']}/agents").json()[0]["id"]
    task_ext = client.post(
        f"/api/v1/tenants/{org['id']}/tasks", json={"agent_id": agent, "prompt": "x"}, headers=idem()
    ).json()["id"]
    out = tmp_path / "out"
    out.mkdir()
    (out / "accounts.xlsx").write_bytes(xlsx())
    (out / "notes.md").write_text("# Notes")
    (out / "trick.md").write_bytes(b"MZ\x90binary")
    secret = tmp_path / "secret.txt"
    secret.write_text("host secret")
    os.symlink(secret, out / "link.md")
    from workx.core.settings import Environment, OrchestratorSettings

    orchestrator = Orchestrator(
        db, OrchestratorSettings(environment=Environment.TEST, object_store_url=f"file:{objects_dir}"), None, "t"
    )  # type: ignore[arg-type]
    tenant, task_id = ids.decode("tenant", org["id"]), ids.decode("task", task_ext)
    for attempt in range(2):
        with db.transaction(tenant_id=tenant) as session:
            task = session.get(Task, task_id)
            assert task is not None
            stored = orchestrator._ingest(session, task, FakeSandbox(tmp_path), uuid.uuid4(), complete=attempt == 0)  # type: ignore[arg-type]
            assert len(stored) == 2
    events = client.get(f"/api/v1/tenants/{org['id']}/tasks/{task_ext}/events").json()
    rejected = {e["payload"]["name"]: e["payload"]["reason"] for e in events if e["type"] == "artifact.rejected"}
    assert rejected == {"link.md": "not_a_regular_file", "trick.md": "content_does_not_match_name"}
    available = [e["payload"] for e in events if e["type"] == "artifact.available"]
    assert [a["new_version"] for a in available] == [True, True, False, False]  # the retry reused both versions
    files = [f for f in client.get(f"/api/v1/tenants/{org['id']}/files").json() if f["source_task_id"] == task_ext]
    assert sorted(f["name"] for f in files) == ["accounts.xlsx", "notes.md"] and all(f["version"] == 1 for f in files)
    assert FilesystemStore(objects_dir)  # store root exists
