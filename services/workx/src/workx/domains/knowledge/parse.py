"""Parsing to a ``ParseResult``: ordered blocks with locators (Part 7 §1-§2).

Built-in parsers cover text formats, PDF text layers, DOCX, XLSX and PPTX. When ``WORKX_TIKA_URL`` is set,
Apache Tika parses the formats the built-in parsers do not (legacy Office, scanned PDFs and images with OCR).
"""

from __future__ import annotations

import csv
import html
import io
import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

LIMIT_CHARS = 2_000_000
LIMIT_PAGES = 2_000
LIMIT_SHEETS = 50
ROWS_PER_BLOCK = 25


class ParseFailure(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


@dataclass
class Block:
    kind: str  # heading | paragraph | table | list | slide
    text: str
    level: int = 0  # heading level
    locator: dict[str, Any] = field(default_factory=dict)
    locator_quality: str = "exact"


@dataclass
class ParseResult:
    blocks: list[Block]
    parser: str
    completeness: str = "complete"
    warnings: list[str] = field(default_factory=list)


def _markdown(text: str) -> list[Block]:
    blocks: list[Block] = []
    paragraph: list[str] = []
    line_no = 0

    def flush() -> None:
        if paragraph:
            body = "\n".join(paragraph).strip()
            if body:
                kind = (
                    "list" if all(re.match(r"\s*([-*+]|\d+\.)\s", p) for p in paragraph if p.strip()) else "paragraph"
                )
                blocks.append(Block(kind, body, locator={"line": line_no - len(paragraph) + 1}))
            paragraph.clear()

    for line_no, line in enumerate(text.splitlines(), start=1):
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            flush()
            blocks.append(
                Block("heading", heading.group(2).strip(), level=len(heading.group(1)), locator={"line": line_no})
            )
        elif not line.strip():
            flush()
        else:
            paragraph.append(line)
    line_no += 1
    flush()
    return blocks


def _csv(text: str) -> list[Block]:
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    header, body = rows[0], rows[1:]
    blocks = []
    for start in range(0, len(body), ROWS_PER_BLOCK):
        group = body[start : start + ROWS_PER_BLOCK]
        lines = [" | ".join(header)] + [" | ".join(r) for r in group]
        blocks.append(Block("table", "\n".join(lines), locator={"rows": f"{start + 2}-{start + 1 + len(group)}"}))
    return blocks


def _html(text: str) -> list[Block]:
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?i)<h([1-6])[^>]*>(.*?)</h\1>", lambda m: f"\n\n{'#' * int(m.group(1))} {m.group(2)}\n\n", text)
    text = re.sub(r"(?i)<(br|/p|/div|/li|/tr)[^>]*>", "\n", text)
    return _markdown(html.unescape(re.sub(r"<[^>]+>", " ", text)))


def _pdf(data: bytes) -> ParseResult:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise ParseFailure("ENCRYPTED", "Encrypted PDFs cannot be read.")
    pages = reader.pages[:LIMIT_PAGES]
    blocks, empty = [], 0
    for number, page in enumerate(pages, start=1):
        text = (page.extract_text() or "").strip()
        if not text:
            empty += 1
            continue
        for part in re.split(r"\n\s*\n", text):
            if part.strip():
                blocks.append(Block("paragraph", part.strip(), locator={"page": number}))
    warnings = []
    completeness = "complete"
    if pages and empty / len(pages) > 0.1:
        warnings.append(f"{empty} of {len(pages)} pages have no text layer (OCR needs the Tika parser)")
        if empty / len(pages) > 0.1:
            completeness = "partial"
    if not blocks:
        raise ParseFailure("NO_TEXT", "The PDF has no text layer; OCR needs the Tika parser.")
    return ParseResult(blocks, "pypdf", completeness, warnings)


def _docx(data: bytes) -> list[Block]:
    import docx

    document = docx.Document(io.BytesIO(data))
    blocks: list[Block] = []
    for index, paragraph in enumerate(document.paragraphs):
        text = paragraph.text.strip()
        if not text:
            continue
        style = (paragraph.style.name if paragraph.style is not None else "") or ""
        level = int(style.split()[-1]) if style.startswith("Heading") and style.split()[-1].isdigit() else 0
        if style == "Title":
            level = 1
        kind = "heading" if level else ("list" if "List" in style else "paragraph")
        blocks.append(Block(kind, text, level=level, locator={"paragraph": index + 1}, locator_quality="approximate"))
    for number, table in enumerate(document.tables, start=1):
        rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows]
        if rows:
            blocks.append(Block("table", "\n".join(rows), locator={"table": number}, locator_quality="approximate"))
    return blocks


def _xlsx(data: bytes) -> list[Block]:
    from openpyxl import load_workbook

    book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    blocks: list[Block] = []
    for sheet in book.worksheets[:LIMIT_SHEETS]:
        rows = [[("" if v is None else str(v)) for v in row] for row in sheet.iter_rows(values_only=True)]
        rows = [r for r in rows if any(c.strip() for c in r)]
        if not rows:
            continue
        header, body = rows[0], rows[1:] or []
        for start in range(0, max(len(body), 1), ROWS_PER_BLOCK):
            group = body[start : start + ROWS_PER_BLOCK]
            lines = [" | ".join(header)] + [" | ".join(r) for r in group]
            last = start + 1 + len(group)
            blocks.append(
                Block("table", "\n".join(lines), locator={"sheet": sheet.title, "range": f"A{start + 1}:{last}"})
            )
    return blocks


def _pptx(data: bytes) -> list[Block]:
    from pptx import Presentation

    deck = Presentation(io.BytesIO(data))
    blocks: list[Block] = []
    for number, slide in enumerate(deck.slides, start=1):
        texts = [
            shape.text_frame.text.strip()
            for shape in slide.shapes
            if getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip()
        ]
        if texts:
            blocks.append(Block("slide", "\n".join(texts), locator={"slide": number}))
    return blocks


def _tika(url: str, data: bytes, media_type: str, http: httpx.Client) -> ParseResult:
    response = http.put(
        f"{url.rstrip('/')}/tika", content=data, headers={"Content-Type": media_type, "Accept": "text/plain"}
    )
    if response.status_code == 422:
        raise ParseFailure("UNSUPPORTED", "The parser cannot read this file.")
    if response.status_code >= 400:
        raise ParseFailure("PARSER_ERROR", f"Tika returned {response.status_code}")
    blocks = [
        Block("paragraph", p.strip(), locator_quality="none") for p in re.split(r"\n\s*\n", response.text) if p.strip()
    ]
    if not blocks:
        raise ParseFailure("NO_TEXT", "No text could be extracted.")
    return ParseResult(blocks, "tika")


BUILT_IN = {
    "text/plain": lambda d: _markdown(d.decode("utf-8")),
    "text/markdown": lambda d: _markdown(d.decode("utf-8")),
    "text/csv": lambda d: _csv(d.decode("utf-8")),
    "application/json": lambda d: _markdown(json.dumps(json.loads(d), ensure_ascii=False, indent=1)),
    "text/html": lambda d: _html(d.decode("utf-8")),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": _docx,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": _xlsx,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": _pptx,
}


def parse(data: bytes, media_type: str, *, tika_url: str = "", http: httpx.Client | None = None) -> ParseResult:
    media_type = (media_type or "").split(";")[0].strip().lower()
    try:
        if media_type == "application/pdf":
            result = _pdf(data)
            if result.completeness == "partial" and tika_url:
                result = _tika(tika_url, data, media_type, http or httpx.Client(timeout=600))
        elif media_type in BUILT_IN:
            result = ParseResult(BUILT_IN[media_type](data), "builtin")
        elif tika_url:
            result = _tika(tika_url, data, media_type, http or httpx.Client(timeout=600))
        else:
            raise ParseFailure("UNSUPPORTED", f"No parser for {media_type or 'this file type'} (Tika not configured).")
    except ParseFailure:
        raise
    except UnicodeDecodeError as exc:
        raise ParseFailure("ENCODING", "The text is not valid UTF-8.") from exc
    except Exception as exc:
        raise ParseFailure("PARSER_ERROR", type(exc).__name__) from exc
    total = sum(len(b.text) for b in result.blocks)
    if total > LIMIT_CHARS:
        kept, size = [], 0
        for block in result.blocks:
            if size + len(block.text) > LIMIT_CHARS:
                break
            kept.append(block)
            size += len(block.text)
        result.blocks, result.completeness = kept, "partial"
        result.warnings.append(f"Text truncated at {LIMIT_CHARS} characters")
    if not result.blocks:
        raise ParseFailure("NO_TEXT", "No text could be extracted.")
    return result
