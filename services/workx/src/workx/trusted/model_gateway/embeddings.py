"""Embedding providers behind the Embedding Gateway (Part 7 §8). The profile string pins provider, model and
dimensions; vectors from different profiles are never compared."""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

import httpx

from workx.core.errors import ApiError
from workx.core.settings import ModelGatewaySettings
from workx.domains.knowledge.text import tokens


class Embedder(Protocol):
    @property
    def profile(self) -> str: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass
class HashEmbedder:
    """Feature hashing of the same tokens the full-text index uses (log-scaled counts, L2-normalized).

    Deterministic, offline, and good enough to exercise ranking in development and tests. Not a semantic model:
    refused in staging and production.
    """

    dimensions: int = 256

    @property
    def profile(self) -> str:
        return f"hash:v1:{self.dimensions}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vector = [0.0] * self.dimensions
            for token, count in Counter(tokens(text)).items():
                digest = hashlib.sha256(token.encode()).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimensions
                vector[index] += (1.0 if digest[4] & 1 else -1.0) * (1.0 + math.log(count))
            norm = math.sqrt(sum(v * v for v in vector)) or 1.0
            out.append([round(v / norm, 6) for v in vector])
        return out


@dataclass
class OpenAICompatibleEmbedder:
    """Any service implementing ``POST {base}/v1/embeddings`` (OpenAI, DashScope compatible mode, vLLM/TEI)."""

    base_url: str
    api_key: str
    model: str
    dimensions: int
    http: httpx.Client

    @property
    def profile(self) -> str:
        return f"openai:{self.model}:{self.dimensions}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self.http.post(
            f"{self.base_url.rstrip('/')}/v1/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "input": texts, "dimensions": self.dimensions, "encoding_format": "float"},
        )
        if response.status_code != 200:
            raise ApiError(502, "UPSTREAM_UNAVAILABLE", f"The embedding service returned {response.status_code}.")
        data = sorted(response.json()["data"], key=lambda d: d["index"])
        vectors = [list(map(float, d["embedding"])) for d in data]
        if len(vectors) != len(texts) or any(len(v) != self.dimensions for v in vectors):
            raise ApiError(502, "UPSTREAM_UNAVAILABLE", "The embedding service returned unexpected vectors.")
        return vectors


def from_settings(settings: ModelGatewaySettings, http: httpx.Client | None = None) -> Embedder:
    if settings.embedding_provider == "hash":
        return HashEmbedder(settings.embedding_dimensions)
    if settings.embedding_provider == "openai":
        if not (settings.embedding_base_url and settings.embedding_model):
            raise ValueError("WORKX_EMBEDDING_BASE_URL and WORKX_EMBEDDING_MODEL are required for the openai provider")
        return OpenAICompatibleEmbedder(
            settings.embedding_base_url,
            settings.embedding_api_key.get_secret_value(),
            settings.embedding_model,
            settings.embedding_dimensions,
            http or httpx.Client(timeout=60),
        )
    raise ValueError("WORKX_EMBEDDING_PROVIDER must be hash or openai")
