"""Structure-aware chunking (Part 7 §3): chunks follow headings, keep tables and slides whole when they fit,
and carry the heading path and the locator of their first block."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from workx.domains.knowledge.parse import Block
from workx.domains.knowledge.text import estimate_tokens, suspected_instructions

TARGET_TOKENS = 500
MAX_TOKENS = 800


@dataclass
class Chunk:
    ordinal: int
    text: str
    heading_path: str
    locator: dict[str, Any]
    locator_quality: str
    flags: list[str] = field(default_factory=list)

    def key(self, source_id: object) -> str:
        """Stable across revisions for unchanged content: unchanged chunks reuse their embeddings."""
        normalized = re.sub(r"\s+", " ", self.text).strip()
        return hashlib.sha256(f"{source_id}|{self.heading_path}|{normalized}".encode()).hexdigest()


def _split_long(text: str) -> list[str]:
    """Splits an oversized block at sentence ends (CJK and Latin), keeping one sentence of overlap."""
    sentences = [s for s in re.split(r"(?<=[。！？.!?])\s*", text) if s.strip()]
    parts: list[str] = []
    current: list[str] = []
    for sentence in sentences:
        if current and estimate_tokens(" ".join([*current, sentence])) > TARGET_TOKENS:
            parts.append(" ".join(current))
            current = current[-1:]  # overlap across a split inside a paragraph
        current.append(sentence)
    if current:
        parts.append(" ".join(current))
    return parts or [text]


def _unit(block: Block) -> tuple[object, ...]:
    """Chunks never span pages, sheets, slides or synced documents, so a citation's locator is exact."""
    return tuple(block.locator.get(k) for k in ("page", "sheet", "slide", "document"))


def chunk(blocks: list[Block]) -> list[Chunk]:
    chunks: list[Chunk] = []
    headings: list[tuple[int, str]] = []
    pending: list[Block] = []

    def path() -> str:
        return " > ".join(h for _, h in headings)

    def emit(texts: list[str], first: Block, kind: str) -> None:
        for text in texts:
            flags = [kind] if kind in ("table", "slide") else []
            if suspected_instructions(text):
                flags.append("suspected_instructions")
            chunks.append(Chunk(len(chunks), text, path(), first.locator, first.locator_quality, flags))

    def flush() -> None:
        if not pending:
            return
        text = "\n\n".join(b.text for b in pending)
        emit([text] if estimate_tokens(text) <= MAX_TOKENS else _split_long(text), pending[0], "paragraph")
        pending.clear()

    for block in blocks:
        if block.kind == "heading":
            flush()
            while headings and headings[-1][0] >= block.level:
                headings.pop()
            headings.append((block.level, block.text))
            continue
        if block.kind in ("table", "slide"):
            flush()
            emit(
                [block.text] if estimate_tokens(block.text) <= MAX_TOKENS else _split_long(block.text),
                block,
                block.kind,
            )
            continue
        if pending and (
            _unit(pending[0]) != _unit(block)
            or estimate_tokens("\n\n".join(b.text for b in [*pending, block])) > TARGET_TOKENS
        ):
            flush()
        pending.append(block)
    flush()
    return chunks
