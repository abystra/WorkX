"""Content validation for files produced by agents or uploaded by people (Part 4 §12, Part 13).

The type comes from the bytes, not the name. Office files are ZIP containers and get structural checks
(no absolute or parent paths, bounded entry count and expansion ratio, no macros) before any parser sees
them; PDFs must parse and must not be encrypted; text must be UTF-8. Each accepted file gets a text preview
for the Library.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_PREVIEW_CHARS = 200_000
MAX_ZIP_ENTRIES = 10_000
MAX_ZIP_UNCOMPRESSED = 300 * 1024 * 1024
MAX_ZIP_RATIO = 100

OFFICE = {
    ".xlsx": ("sheet", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xl/workbook.xml"),
    ".docx": ("doc", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "word/document.xml"),
    ".pptx": (
        "slides",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "ppt/presentation.xml",
    ),
}
TEXT = {
    ".md": ("doc", "text/markdown"),
    ".txt": ("doc", "text/plain"),
    ".csv": ("sheet", "text/csv"),
    ".json": ("doc", "application/json"),
    ".html": ("doc", "text/html"),
}
IMAGES = {b"\x89PNG\r\n\x1a\n": ("image", "image/png"), b"\xff\xd8\xff": ("image", "image/jpeg")}


class Rejected(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class Accepted:
    kind: str
    media_type: str
    preview: str
    checks: dict[str, Any] = field(default_factory=dict)


def safe_name(name: str) -> str:
    base = PurePosixPath(name.replace("\\", "/")).name.strip()
    if not base or base.startswith(".") or len(base) > 200 or any(ord(c) < 32 for c in base):
        raise Rejected("invalid_name")
    return base


def _check_zip(data: bytes, required: str) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise Rejected("not_a_valid_office_file") from exc
    entries = archive.infolist()
    if len(entries) > MAX_ZIP_ENTRIES:
        raise Rejected("too_many_entries")
    total = 0
    for entry in entries:
        name = entry.filename
        if name.startswith("/") or ".." in PurePosixPath(name).parts or "\\" in name:
            raise Rejected("unsafe_entry_path")
        if entry.flag_bits & 0x1:
            raise Rejected("encrypted")
        total += entry.file_size
        if entry.compress_size and entry.file_size / max(entry.compress_size, 1) > MAX_ZIP_RATIO:
            raise Rejected("compression_ratio")
    if total > MAX_ZIP_UNCOMPRESSED:
        raise Rejected("expands_too_much")
    names = {e.filename for e in entries}
    if "[Content_Types].xml" not in names or required not in names:
        raise Rejected("not_a_valid_office_file")
    if any(n.lower().endswith("vbaproject.bin") for n in names):
        raise Rejected("macros_not_allowed")
    return archive


def _preview_xlsx(data: bytes) -> str:
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out = io.StringIO()
    writer = csv.writer(out)
    for sheet in workbook.worksheets[:3]:
        out.write(f"# {sheet.title}\n")
        for i, row in enumerate(sheet.iter_rows(values_only=True)):
            if i >= 200:
                break
            writer.writerow(["" if v is None else v for v in row])
    workbook.close()
    return out.getvalue()


def _preview_docx(data: bytes) -> str:
    from docx import Document

    return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)


def _preview_pptx(data: bytes) -> str:
    from pptx import Presentation

    slides = []
    for number, slide in enumerate(Presentation(io.BytesIO(data)).slides, start=1):
        texts = [shape.text_frame.text for shape in slide.shapes if getattr(shape, "has_text_frame", False)]
        slides.append(f"## Slide {number}\n" + "\n".join(t for t in texts if t))
    return "\n\n".join(slides)


def _preview_pdf(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise Rejected("encrypted")
        return "\n\n".join((page.extract_text() or "") for page in reader.pages[:50])
    except PdfReadError as exc:
        raise Rejected("not_a_valid_pdf") from exc


def validate(name: str, data: bytes) -> Accepted:
    name = safe_name(name)
    if len(data) > MAX_FILE_BYTES:
        raise Rejected("too_large")
    suffix = PurePosixPath(name).suffix.lower()
    if suffix in (".xlsm", ".docm", ".pptm"):
        raise Rejected("macros_not_allowed")
    if suffix in OFFICE:
        kind, media_type, required = OFFICE[suffix]
        _check_zip(data, required)
        try:
            preview = {"sheet": _preview_xlsx, "doc": _preview_docx, "slides": _preview_pptx}[kind](data)
        except Rejected:
            raise
        except Exception as exc:
            raise Rejected("not_a_valid_office_file") from exc
        return Accepted(kind, media_type, preview[:MAX_PREVIEW_CHARS], {"container": "ooxml"})
    if suffix == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise Rejected("not_a_valid_pdf")
        return Accepted("pdf", "application/pdf", _preview_pdf(data)[:MAX_PREVIEW_CHARS])
    for magic, (kind, media_type) in IMAGES.items():
        if data.startswith(magic):
            return Accepted(kind, media_type, "")
    if suffix in TEXT:
        if data.startswith((b"PK\x03\x04", b"%PDF-", b"\x7fELF", b"MZ")):
            raise Rejected("content_does_not_match_name")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise Rejected("not_utf8_text") from exc
        if suffix == ".json":
            try:
                json.loads(text)
            except ValueError as exc:
                raise Rejected("invalid_json") from exc
        kind, media_type = TEXT[suffix]
        return Accepted(kind, media_type, text[:MAX_PREVIEW_CHARS])
    raise Rejected("unsupported_type")
