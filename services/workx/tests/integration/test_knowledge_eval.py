"""Retrieval quality gate on the bundled bilingual labeled set (tests/fixtures/knowledge): 8 documents,
30 queries (exact terms, paraphrases, Chinese questions, table lookups). Uses the development hash embedder, so
the numbers measure the full-text + fusion pipeline; a semantic provider is measured with the same harness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from tests.integration.test_knowledge import drain, make_source, search, upload
from workx.core.db import Database
from workx.domains.knowledge.evaluate import evaluate

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "knowledge"
TYPES = {".md": "text/markdown", ".csv": "text/csv"}


def test_retrieval_quality_on_the_labeled_set(team: dict[str, Any], api_app: FastAPI, db: Database) -> None:
    alice, base = team["alice"], team["base"]
    for path in sorted((FIXTURES / "corpus").iterdir()):
        make_source(alice, base, upload(alice, base, path.name, path.read_bytes(), TYPES[path.suffix])["id"])
    drain(api_app, db)
    labeled = json.loads((FIXTURES / "queries.json").read_text(encoding="utf-8"))
    report = evaluate(labeled, lambda q: search(alice, base, q, k=10))
    print("\n" + "\n".join(report.lines()))
    assert report.recall[5] >= 0.95 and report.mrr >= 0.9 and report.section_precision >= 0.85, report.lines()
