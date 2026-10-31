"""Outbound messages with the bot's credentials (tokens cached per binding until shortly before expiry)."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


class SendFailure(Exception):
    """``retryable`` failures are retried by the delivery job; others end the delivery as failed."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass
class TokenCache:
    _tokens: dict[str, tuple[str, float]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def get(self, key: str) -> str | None:
        with self._lock:
            token, expires = self._tokens.get(key, ("", 0.0))
            return token if token and expires - 120 > time.time() else None

    def put(self, key: str, token: str, ttl: float) -> None:
        with self._lock:
            self._tokens[key] = (token, time.time() + ttl)

    def drop(self, key: str) -> None:
        with self._lock:
            self._tokens.pop(key, None)


def _json(response: httpx.Response) -> dict[str, Any]:
    if response.status_code >= 500:
        raise SendFailure(f"platform returned {response.status_code}", retryable=True)
    try:
        data: dict[str, Any] = response.json()
    except ValueError as exc:
        raise SendFailure("platform returned an unreadable response", retryable=True) from exc
    return data


def feishu_send(
    http: httpx.Client,
    cache: TokenCache,
    base_url: str,
    binding_key: str,
    config: dict[str, Any],
    secrets: dict[str, str],
    target: dict[str, Any],
    text: str,
    delivery_id: str,
) -> str:
    token = cache.get(binding_key)
    if token is None:
        data = _json(
            http.post(
                f"{base_url}/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": config.get("app_id", ""), "app_secret": secrets.get("app_secret", "")},
            )
        )
        if data.get("code") != 0:
            raise SendFailure(f"Feishu refused the app credentials ({data.get('code')})", retryable=False)
        token = str(data["tenant_access_token"])
        cache.put(binding_key, token, float(data.get("expire", 7200)))
    body = {"msg_type": "text", "content": json.dumps({"text": text}, ensure_ascii=False), "uuid": delivery_id[:50]}
    headers = {"Authorization": f"Bearer {token}"}
    if target.get("message_id"):
        response = http.post(
            f"{base_url}/open-apis/im/v1/messages/{target['message_id']}/reply", json=body, headers=headers
        )
    else:
        response = http.post(
            f"{base_url}/open-apis/im/v1/messages",
            params={"receive_id_type": "chat_id"},
            json={**body, "receive_id": target.get("chat_id", "")},
            headers=headers,
        )
    data = _json(response)
    if data.get("code") in (99991663, 99991668, 99991677):  # token expired or invalid: next attempt gets a new one
        cache.drop(binding_key)
        raise SendFailure("Feishu token expired", retryable=True)
    if data.get("code") != 0:
        raise SendFailure(
            f"Feishu refused the message ({data.get('code')}: {data.get('msg', '')})"[:300], retryable=False
        )
    return str((data.get("data") or {}).get("message_id", ""))


def wecom_send(
    http: httpx.Client,
    cache: TokenCache,
    base_url: str,
    binding_key: str,
    config: dict[str, Any],
    secrets: dict[str, str],
    target: dict[str, Any],
    text: str,
    delivery_id: str,
) -> str:
    token = cache.get(binding_key)
    if token is None:
        data = _json(
            http.get(
                f"{base_url}/cgi-bin/gettoken",
                params={"corpid": config.get("corp_id", ""), "corpsecret": secrets.get("secret", "")},
            )
        )
        if data.get("errcode") != 0:
            raise SendFailure(f"WeCom refused the app credentials ({data.get('errcode')})", retryable=False)
        token = str(data["access_token"])
        cache.put(binding_key, token, float(data.get("expires_in", 7200)))
    data = _json(
        http.post(
            f"{base_url}/cgi-bin/message/send",
            params={"access_token": token},
            json={
                "touser": target.get("user_id", ""),
                "msgtype": "text",
                "agentid": int(config.get("agent_id") or 0),
                "text": {"content": text},
                "enable_duplicate_check": 1,
                "duplicate_check_interval": 1800,
            },
        )
    )
    if data.get("errcode") in (40014, 42001):
        cache.drop(binding_key)
        raise SendFailure("WeCom token expired", retryable=True)
    if data.get("errcode") != 0:
        raise SendFailure(
            f"WeCom refused the message ({data.get('errcode')}: {data.get('errmsg', '')})"[:300], retryable=False
        )
    return str(data.get("msgid", ""))
