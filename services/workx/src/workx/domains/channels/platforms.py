"""Platform events → one normalized inbound message (pure functions; the payloads are already verified)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree


@dataclass(frozen=True)
class Inbound:
    event_id: str
    message_id: str | None
    conversation: str
    kind: str  # direct | group
    external_tenant: str
    sender: str
    sender_name: str | None
    text: str
    mentioned: bool


def feishu(event: dict[str, Any], bot_open_id: str | None = None) -> Inbound | None:
    """``im.message.receive_v1`` text messages from users; anything else is not a request (None)."""
    header = event.get("header") or {}
    if header.get("event_type") != "im.message.receive_v1":
        return None
    body = event.get("event") or {}
    sender, message = body.get("sender") or {}, body.get("message") or {}
    if sender.get("sender_type") != "user" or message.get("message_type") != "text":
        return None
    try:
        text = str(json.loads(message.get("content") or "{}").get("text", ""))
    except ValueError:
        return None
    mentions = message.get("mentions") or []
    mentioned = any((bot_open_id is None or (m.get("id") or {}).get("open_id") == bot_open_id) for m in mentions)
    for m in mentions:  # "@_user_1 summarize" → "summarize"
        text = text.replace(str(m.get("key", "")), " ")
    return Inbound(
        event_id=str(header.get("event_id", "")),
        message_id=message.get("message_id"),
        conversation=str(message.get("chat_id", "")),
        kind="direct" if message.get("chat_type") == "p2p" else "group",
        external_tenant=str(header.get("tenant_key") or sender.get("tenant_key") or ""),
        sender=str((sender.get("sender_id") or {}).get("open_id", "")),
        sender_name=None,
        text=re.sub(r"\s+", " ", text).strip(),
        mentioned=mentioned,
    )


def wecom(xml: str, corp_id: str) -> Inbound | None:
    """Self-built app callback: text messages (direct only)."""
    root = ElementTree.fromstring(xml)  # noqa: S314 (decrypted payload of a verified callback; DTDs refused earlier)
    if root.findtext("MsgType") != "text":
        return None
    sender = root.findtext("FromUserName") or ""
    return Inbound(
        event_id=root.findtext("MsgId") or f"{sender}:{root.findtext('CreateTime')}",
        message_id=root.findtext("MsgId"),
        conversation=sender,
        kind="direct",
        external_tenant=corp_id,
        sender=sender,
        sender_name=None,
        text=(root.findtext("Content") or "").strip(),
        mentioned=False,
    )
