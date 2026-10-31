"""Test chat platforms (``workx dev-channels``): the parts of the Feishu Open Platform and WeCom APIs the channel
worker calls (app tokens, send/reply), recording every message. Development and tests only.

``/_fail`` makes the next N sends fail with HTTP 500 (delivery retry tests); ``/_sent`` lists what was sent.
"""

from __future__ import annotations

import secrets
import threading
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from workx.core.settings import Environment


def create_dev_channels_app(
    *, environment: Environment = Environment.DEVELOPMENT, apps: dict[str, str] | None = None
) -> FastAPI:
    """``apps``: accepted credentials, ``{app_id or corp_id: secret}``."""
    if environment in (Environment.STAGING, Environment.PRODUCTION):
        raise RuntimeError("The test chat platforms must not run in staging or production.")
    app = FastAPI(title="WorkX test chat platforms", docs_url=None, redoc_url=None, openapi_url=None)
    lock = threading.Lock()
    credentials = dict(apps or {})
    tokens: dict[str, str] = {}
    sent: list[dict[str, Any]] = []
    seen_uuids: dict[str, str] = {}
    failures = {"remaining": 0}

    def token_for(app_id: str) -> str:
        token = "t-" + secrets.token_hex(12)
        tokens[token] = app_id
        return token

    @app.post("/_apps")
    def register(body: dict[str, str]) -> dict[str, int]:
        with lock:
            credentials.update(body)
            return {"apps": len(credentials)}

    @app.post("/_fail")
    def fail_next(body: dict[str, int]) -> dict[str, int]:
        with lock:
            failures["remaining"] = int(body.get("count", 1))
            return failures

    @app.get("/_sent")
    def list_sent() -> list[dict[str, Any]]:
        with lock:
            return list(sent)

    def failing() -> JSONResponse | None:
        with lock:
            if failures["remaining"] > 0:
                failures["remaining"] -= 1
                return JSONResponse({"error": "temporarily unavailable"}, status_code=500)
        return None

    # ---------------------------------------------------------------- Feishu
    @app.post("/open-apis/auth/v3/tenant_access_token/internal")
    def feishu_token(body: dict[str, str]) -> dict[str, Any]:
        with lock:
            if credentials.get(body.get("app_id", "")) != body.get("app_secret"):
                return {"code": 10014, "msg": "app secret invalid"}
            return {"code": 0, "msg": "ok", "tenant_access_token": token_for(body["app_id"]), "expire": 7200}

    async def feishu_message(request: Request, reply_to: str | None) -> Any:
        broken = failing()
        if broken is not None:
            return broken
        auth = request.headers.get("authorization", "")
        if auth[7:] not in tokens:
            return {"code": 99991663, "msg": "invalid access token"}
        body = await request.json()
        with lock:
            if body.get("uuid") in seen_uuids:  # Feishu dedupes sends with the same uuid
                return {"code": 0, "data": {"message_id": seen_uuids[body["uuid"]]}}
            message_id = "om_" + secrets.token_hex(8)
            seen_uuids[body.get("uuid") or message_id] = message_id
            sent.append(
                {
                    "platform": "feishu",
                    "reply_to": reply_to,
                    "chat_id": body.get("receive_id"),
                    "content": body.get("content"),
                    "uuid": body.get("uuid"),
                    "message_id": message_id,
                }
            )
        return {"code": 0, "msg": "success", "data": {"message_id": message_id}}

    @app.post("/open-apis/im/v1/messages/{message_id}/reply")
    async def feishu_reply(message_id: str, request: Request) -> Any:
        return await feishu_message(request, message_id)

    @app.post("/open-apis/im/v1/messages")
    async def feishu_send(request: Request) -> Any:
        return await feishu_message(request, None)

    # ----------------------------------------------------------------- WeCom
    @app.get("/cgi-bin/gettoken")
    def wecom_token(corpid: str = "", corpsecret: str = "") -> dict[str, Any]:
        with lock:
            if credentials.get(corpid) != corpsecret:
                return {"errcode": 40001, "errmsg": "invalid credential"}
            return {"errcode": 0, "errmsg": "ok", "access_token": token_for(corpid), "expires_in": 7200}

    @app.post("/cgi-bin/message/send")
    async def wecom_send(request: Request, access_token: str = "") -> Any:
        broken = failing()
        if broken is not None:
            return broken
        if access_token not in tokens:
            return {"errcode": 40014, "errmsg": "invalid access_token"}
        body = await request.json()
        with lock:
            msgid = "wx_" + secrets.token_hex(8)
            sent.append(
                {
                    "platform": "wecom",
                    "to": body.get("touser"),
                    "content": (body.get("text") or {}).get("content"),
                    "msgid": msgid,
                }
            )
        return {"errcode": 0, "errmsg": "ok", "msgid": msgid}

    return app
