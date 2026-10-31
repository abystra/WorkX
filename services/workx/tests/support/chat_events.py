"""Builds real platform callbacks (signed and encrypted exactly as Feishu and WeCom send them)."""

from __future__ import annotations

import json
import secrets
import time
from typing import Any

from workx.trusted.channels import crypto

FEISHU_SECRETS = {"app_secret": "fs-app-secret", "encrypt_key": "fs-encrypt-key", "verification_token": "fs-verify"}
WECOM_SECRETS = {"secret": "wc-secret", "token": "wc-token", "encoding_aes_key": "a" * 43}
BOT_OPEN_ID = "ou_bot"


def feishu_message(
    *,
    sender: str,
    text: str,
    chat_type: str = "p2p",
    chat_id: str = "oc_chat",
    event_id: str | None = None,
    mention_bot: bool = False,
    tenant_key: str = "tk_acme",
    token: str = FEISHU_SECRETS["verification_token"],
) -> dict[str, Any]:
    mentions = [{"key": "@_user_1", "id": {"open_id": BOT_OPEN_ID}, "name": "WorkX"}] if mention_bot else []
    return {
        "schema": "2.0",
        "header": {
            "event_id": event_id or secrets.token_hex(8),
            "event_type": "im.message.receive_v1",
            "create_time": str(int(time.time() * 1000)),
            "token": token,
            "app_id": "cli_app",
            "tenant_key": tenant_key,
        },
        "event": {
            "sender": {"sender_id": {"open_id": sender}, "sender_type": "user", "tenant_key": tenant_key},
            "message": {
                "message_id": "om_in_" + secrets.token_hex(6),
                "chat_id": chat_id,
                "chat_type": chat_type,
                "message_type": "text",
                "content": json.dumps({"text": ("@_user_1 " if mention_bot else "") + text}),
                "mentions": mentions,
            },
        },
    }


def feishu_request(
    event: dict[str, Any],
    *,
    encrypt_key: str = FEISHU_SECRETS["encrypt_key"],
    timestamp: int | None = None,
    sign_key: str | None = None,
) -> tuple[bytes, dict[str, str]]:
    body = json.dumps({"encrypt": crypto.feishu_encrypt(encrypt_key, event)}).encode()
    ts, nonce = str(timestamp or int(time.time())), secrets.token_hex(6)
    signature = crypto.feishu_signature(ts, nonce, sign_key if sign_key is not None else encrypt_key, body)
    return body, {
        "Content-Type": "application/json",
        "X-Lark-Request-Timestamp": ts,
        "X-Lark-Request-Nonce": nonce,
        "X-Lark-Signature": signature,
    }


def wecom_request(xml: str, corp_id: str, *, timestamp: int | None = None) -> tuple[bytes, dict[str, str]]:
    encrypted = crypto.wecom_encrypt(WECOM_SECRETS["encoding_aes_key"], xml, corp_id)
    ts, nonce = str(timestamp or int(time.time())), secrets.token_hex(6)
    signature = crypto.wecom_signature(WECOM_SECRETS["token"], ts, nonce, encrypted)
    body = f"<xml><ToUserName><![CDATA[{corp_id}]]></ToUserName><Encrypt><![CDATA[{encrypted}]]></Encrypt></xml>"
    return body.encode(), {"msg_signature": signature, "timestamp": ts, "nonce": nonce}


def wecom_text(sender: str, text: str, msg_id: str | None = None) -> str:
    return (
        f"<xml><ToUserName>corp</ToUserName><FromUserName>{sender}</FromUserName>"
        f"<CreateTime>{int(time.time())}</CreateTime>"
        f"<MsgType>text</MsgType><Content><![CDATA[{text}]]></Content>"
        f"<MsgId>{msg_id or secrets.randbelow(10**12)}</MsgId>"
        "<AgentID>1000002</AgentID></xml>"
    )
