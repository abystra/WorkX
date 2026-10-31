"""Platform callback verification and decryption.

* Feishu (event subscription v2): ``X-Lark-Signature = sha256(timestamp + nonce + encrypt_key + body)``; with an
  encrypt key the body is ``{"encrypt": base64(iv || AES-256-CBC(sha256(encrypt_key), iv, json))}``; the
  verification token is checked inside the event (``header.token`` / ``token``).
* WeCom (企业微信 callback): ``msg_signature = sha1(sorted(token, timestamp, nonce, encrypted))``; the payload is
  AES-256-CBC with ``key = base64(EncodingAESKey + "=")`` and ``iv = key[:16]``, PKCS#7 padded to 32 bytes;
  plaintext = 16 random bytes || 4-byte length || message || receive id (the corp id, checked).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import struct
import time
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

WINDOW_SECONDS = 300


class Rejected(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fresh(timestamp: str, now: float | None = None) -> None:
    try:
        moment = int(timestamp)
    except ValueError as exc:
        raise Rejected("BAD_TIMESTAMP") from exc
    if abs((now or time.time()) - moment) > WINDOW_SECONDS:
        raise Rejected("STALE")


def _aes_cbc(key: bytes, iv: bytes, data: bytes, *, decrypt: bool) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    op = cipher.decryptor() if decrypt else cipher.encryptor()
    return op.update(data) + op.finalize()


def _unpad(data: bytes, block: int) -> bytes:
    if not data:
        raise Rejected("BAD_PADDING")
    pad = data[-1]
    if pad < 1 or pad > block or data[-pad:] != bytes([pad]) * pad:
        raise Rejected("BAD_PADDING")
    return data[:-pad]


def _pad(data: bytes, block: int) -> bytes:
    pad = block - len(data) % block
    return data + bytes([pad]) * pad


# ------------------------------------------------------------------------------------------------- Feishu


def feishu_signature(timestamp: str, nonce: str, encrypt_key: str, body: bytes) -> str:
    return hashlib.sha256(timestamp.encode() + nonce.encode() + encrypt_key.encode() + body).hexdigest()


def feishu_decrypt(encrypt_key: str, encrypted: str) -> dict[str, Any]:
    raw = base64.b64decode(encrypted)
    if len(raw) < 32 or len(raw) % 16:
        raise Rejected("BAD_CIPHERTEXT")
    key = hashlib.sha256(encrypt_key.encode()).digest()
    plain = _unpad(_aes_cbc(key, raw[:16], raw[16:], decrypt=True), 16)
    data: dict[str, Any] = json.loads(plain)
    return data


def feishu_encrypt(encrypt_key: str, payload: dict[str, Any]) -> str:
    """Used by the test platform to produce real encrypted callbacks."""
    key = hashlib.sha256(encrypt_key.encode()).digest()
    iv = os.urandom(16)
    return base64.b64encode(iv + _aes_cbc(key, iv, _pad(json.dumps(payload).encode(), 16), decrypt=False)).decode()


def feishu_open(
    secrets: dict[str, str], headers: dict[str, str], body: bytes, *, now: float | None = None
) -> dict[str, Any]:
    """Verifies and decrypts one callback; returns the event JSON (a url_verification challenge included)."""
    encrypt_key = secrets.get("encrypt_key", "")
    try:
        outer = json.loads(body or b"{}")
    except ValueError as exc:
        raise Rejected("BAD_JSON") from exc
    if encrypt_key:
        signature = headers.get("x-lark-signature", "")
        timestamp, nonce = headers.get("x-lark-request-timestamp", ""), headers.get("x-lark-request-nonce", "")
        event = feishu_decrypt(encrypt_key, str(outer.get("encrypt", ""))) if "encrypt" in outer else None
        challenge = event is not None and event.get("type") == "url_verification"
        if not challenge:  # URL verification requests are not signed
            if not signature or not hmac.compare_digest(
                signature, feishu_signature(timestamp, nonce, encrypt_key, body)
            ):
                raise Rejected("BAD_SIGNATURE")
            _fresh(timestamp, now)
        if event is None:
            raise Rejected("NOT_ENCRYPTED")
    else:
        event = outer
    token = (event.get("header") or {}).get("token") or event.get("token") or ""
    if not hmac.compare_digest(str(token), secrets.get("verification_token", "")):
        raise Rejected("BAD_TOKEN")
    return event


# -------------------------------------------------------------------------------------------------- WeCom


def wecom_signature(token: str, timestamp: str, nonce: str, encrypted: str) -> str:
    return hashlib.sha1("".join(sorted([token, timestamp, nonce, encrypted])).encode()).hexdigest()  # noqa: S324


def _wecom_key(encoding_aes_key: str) -> bytes:
    key = base64.b64decode(encoding_aes_key + "=")
    if len(key) != 32:
        raise Rejected("BAD_KEY")
    return key


def wecom_decrypt(encoding_aes_key: str, encrypted: str, receive_id: str) -> str:
    key = _wecom_key(encoding_aes_key)
    plain = _unpad(_aes_cbc(key, key[:16], base64.b64decode(encrypted), decrypt=True), 32)
    (length,) = struct.unpack(">I", plain[16:20])
    message, tail = plain[20 : 20 + length], plain[20 + length :]
    if tail.decode() != receive_id:
        raise Rejected("WRONG_RECEIVER")
    return message.decode()


def wecom_encrypt(encoding_aes_key: str, message: str, receive_id: str) -> str:
    key = _wecom_key(encoding_aes_key)
    body = message.encode()
    plain = os.urandom(16) + struct.pack(">I", len(body)) + body + receive_id.encode()
    return base64.b64encode(_aes_cbc(key, key[:16], _pad(plain, 32), decrypt=False)).decode()


def wecom_open(
    secrets: dict[str, str], corp_id: str, query: dict[str, str], body: bytes | None, *, now: float | None = None
) -> str:
    """GET (URL verification): returns the decrypted echostr. POST: returns the decrypted message XML."""
    timestamp, nonce, signature = query.get("timestamp", ""), query.get("nonce", ""), query.get("msg_signature", "")
    if body is None:
        encrypted = query.get("echostr", "")
    else:
        if len(body) > 64 * 1024 or b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
            raise Rejected("BAD_XML")
        from xml.etree import ElementTree

        try:
            encrypted = ElementTree.fromstring(body).findtext("Encrypt") or ""  # noqa: S314 (DTDs refused above)
        except ElementTree.ParseError as exc:
            raise Rejected("BAD_XML") from exc
    expected = wecom_signature(secrets.get("token", ""), timestamp, nonce, encrypted)
    if not signature or not hmac.compare_digest(signature, expected):
        raise Rejected("BAD_SIGNATURE")
    if body is not None:
        _fresh(timestamp, now)
    return wecom_decrypt(secrets.get("encoding_aes_key", ""), encrypted, corp_id)
