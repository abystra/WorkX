"""The API's client for the broker service. Secret values pass through API memory only on their way here."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from workx.core.errors import ApiError


@dataclass
class BrokerClient:
    base_url: str
    token: str
    http: httpx.Client

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.http.post(
                f"{self.base_url.rstrip('/')}{path}",
                json=body,
                headers={"X-WorkX-Internal-Token": self.token},
                timeout=15,
            )
        except httpx.HTTPError as exc:
            raise ApiError(503, "UPSTREAM_UNAVAILABLE", "The credential service is not reachable.") from exc
        if response.status_code >= 400:
            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            raise ApiError(
                response.status_code if response.status_code < 500 else 502,
                data.get("code", "BROKER_ERROR"),
                data.get("detail", "Credential service error."),
            )
        result: dict[str, Any] = response.json()
        return result

    def put_secret(
        self,
        *,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        actor_membership_id: uuid.UUID,
        value: str,
        kind: str = "api_key",
    ) -> dict[str, Any]:
        return self._post(
            "/internal/secrets",
            {
                "tenant_id": str(tenant_id),
                "connection_id": str(connection_id),
                "actor_membership_id": str(actor_membership_id),
                "kind": kind,
                "value": value,
            },
        )

    def destroy_secrets(self, *, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> dict[str, Any]:
        return self._post(
            "/internal/connections/destroy", {"tenant_id": str(tenant_id), "connection_id": str(connection_id)}
        )

    def put_installation_secret(
        self, *, tenant_id: uuid.UUID, connector_id: str, actor_membership_id: uuid.UUID, value: str
    ) -> dict[str, Any]:
        return self._post(
            "/internal/installations/secret",
            {
                "tenant_id": str(tenant_id),
                "connector_id": connector_id,
                "actor_membership_id": str(actor_membership_id),
                "value": value,
            },
        )

    def oauth_start(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._post("/internal/oauth/start", body)

    def oauth_complete(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._post("/internal/oauth/complete", body)

    def channel_secrets(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._post("/internal/channels/secrets", body)

    def channel_open(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._post("/internal/channels/open", body)

    def channel_send(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._post("/internal/channels/send", body)
