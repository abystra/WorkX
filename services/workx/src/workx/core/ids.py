"""Identifiers: UUIDv7 internally, prefixed Crockford base32 externally (Part 11 §3).

External form is ``<prefix>_<26 chars>``, e.g. ``tsk_01JC8ZK3V9Q2M6R7T8W9X0Y1Z2``. Decoding checks the
prefix, so an ID of the wrong kind is indistinguishable from a missing resource.
"""

from __future__ import annotations

import os
import time
import uuid

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_DECODE = {c: i for i, c in enumerate(_ALPHABET)}
_DECODE.update({c.lower(): i for c, i in list(_DECODE.items())})
_DECODE.update({"O": 0, "o": 0, "I": 1, "i": 1, "L": 1, "l": 1})

PREFIXES = {
    "user": "usr",
    "tenant": "ten",
    "membership": "mem",
    "invitation": "inv",
    "login_session": "lgs",
    "department": "dep",
    "agent": "agt",
    "agent_version": "agv",
    "project": "prj",
    "file": "fil",
    "session": "ses",
    "task": "tsk",
    "attempt": "att",
    "artifact": "art",
    "automation": "aut",
    "scenario": "scn",
    "connection": "con",
    "credential": "crd",
    "secret_version": "sev",
    "knowledge_source": "kns",
    "knowledge_revision": "knr",
    "channel_binding": "chb",
    "channel_run": "chr",
    "approval": "apr",
    "authorization_request": "arq",
    "job": "job",
    "event": "evt",
    "audit": "aud",
    "request": "req",
    "grant": "gra",
}


def uuid7() -> uuid.UUID:
    """RFC 9562 UUID version 7: 48-bit Unix milliseconds, then random bits. Sortable by creation time."""
    ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")
    value = (ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76  # version
    value |= ((rand >> 64) & 0xFFF) << 64  # rand_a (12 bits)
    value |= 0b10 << 62  # variant
    value |= rand & ((1 << 62) - 1)  # rand_b (62 bits)
    return uuid.UUID(int=value)


def _encode(value: int) -> str:
    chars = []
    for _ in range(26):
        chars.append(_ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def encode(kind: str, value: uuid.UUID) -> str:
    return f"{PREFIXES[kind]}_{_encode(value.int)}"


def decode(kind: str, external: str) -> uuid.UUID | None:
    """Returns None for anything that is not a well-formed ID of this kind."""
    prefix, sep, body = external.partition("_")
    if not sep or prefix != PREFIXES[kind] or len(body) != 26:
        return None
    value = 0
    for char in body:
        digit = _DECODE.get(char)
        if digit is None:
            return None
        value = (value << 5) | digit
    if value >> 128:
        return None
    return uuid.UUID(int=value)


def new(kind: str) -> tuple[uuid.UUID, str]:
    value = uuid7()
    return value, encode(kind, value)
