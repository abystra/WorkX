"""Client for the Embedding Gateway (``POST {model_gateway}/internal/embeddings``)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import httpx

from workx.core.errors import ApiError

BATCH = 64


@dataclass
class EmbeddingClient:
    base_url: str
    token: str
    http: httpx.Client

    def embed(self, texts: list[str], *, tenant_id: uuid.UUID | None = None) -> tuple[str, list[list[float]]]:
        profile, vectors = "", []
        for start in range(0, len(texts), BATCH):
            try:
                response = self.http.post(
                    f"{self.base_url.rstrip('/')}/internal/embeddings",
                    headers={"X-WorkX-Internal-Token": self.token},
                    json={"texts": texts[start : start + BATCH], "tenant_id": str(tenant_id) if tenant_id else None},
                    timeout=120,
                )
            except httpx.HTTPError as exc:
                raise ApiError(503, "UPSTREAM_UNAVAILABLE", "The embedding service is not reachable.") from exc
            if response.status_code != 200:
                raise ApiError(502, "UPSTREAM_UNAVAILABLE", f"The embedding service returned {response.status_code}.")
            data = response.json()
            profile = data["profile"]
            vectors.extend(data["vectors"])
        return profile, vectors
