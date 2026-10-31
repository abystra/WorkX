"""Object storage for file versions (Part 11; decision 23: no MinIO CE for new deployments).

Keys are tenant-prefixed (``t/{tenant}/files/{file}/{version}``) and never leave the server: clients download
through the API after authorization, so there is no object URL to share or guess.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import parse_qs, urlparse


class ObjectStore(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


def object_key(tenant_id: object, file_id: object, version_no: int) -> str:
    return f"t/{tenant_id}/files/{file_id}/{version_no}"


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


@dataclass
class FilesystemStore:
    root: Path

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("invalid object key")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".partial")
        temporary.write_bytes(data)
        os.replace(temporary, path)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


@dataclass
class S3Store:
    """S3-compatible store (SeaweedFS, Garage, cloud S3). Requires ``boto3`` (``pip install workx[s3]``)."""

    bucket: str
    endpoint: str | None

    def __post_init__(self) -> None:
        import boto3

        self.client = boto3.client("s3", endpoint_url=self.endpoint)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(
            Bucket=self.bucket, Key=key, Body=data, ContentType=content_type, ServerSideEncryption="AES256"
        )

    def get(self, key: str) -> bytes:
        body: bytes = self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        return body

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


def from_url(url: str) -> ObjectStore:
    if url.startswith("file:"):
        return FilesystemStore(Path(url.removeprefix("file:")))
    if url.startswith("s3://"):
        parsed = urlparse(url)
        endpoint = parse_qs(parsed.query).get("endpoint", [None])[0]
        return S3Store(parsed.netloc, endpoint)
    raise ValueError("WORKX_OBJECT_STORE_URL must start with file: or s3://")
