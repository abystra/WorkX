"""Retrieval evaluation (Part 7 §9): Recall@k, MRR and nDCG@10 over a labeled query set. Used as a regression
gate for parser, chunker and embedding changes (tests/integration/test_knowledge_eval.py)."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Report:
    queries: int = 0
    recall: dict[int, float] = field(default_factory=dict)
    mrr: float = 0.0
    ndcg10: float = 0.0
    section_precision: float = 0.0
    misses: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        recall = ", ".join(f"Recall@{k} {v:.2f}" for k, v in sorted(self.recall.items()))
        return [
            f"queries {self.queries}: {recall}, MRR {self.mrr:.2f}, nDCG@10 {self.ndcg10:.2f}, "
            f"section match at rank 1 {self.section_precision:.2f}",
            *[f"  miss: {m}" for m in self.misses],
        ]


def evaluate(
    labeled: list[dict[str, Any]], search: Callable[[str], list[dict[str, Any]]], ks: tuple[int, ...] = (1, 3, 5)
) -> Report:
    """``search`` returns ranked passages with ``source`` and ``section``; one relevant document per query."""
    report = Report(queries=len(labeled), recall={k: 0.0 for k in ks})
    reciprocal, gains, sections = 0.0, 0.0, 0
    for item in labeled:
        results = search(item["q"])[:10]
        ranks = [i for i, r in enumerate(results, start=1) if r["source"] == item["doc"]]
        first = ranks[0] if ranks else None
        for k in ks:
            report.recall[k] += 1.0 if first is not None and first <= k else 0.0
        reciprocal += 1.0 / first if first else 0.0
        gains += 1.0 / math.log2(first + 1) if first else 0.0  # one relevant document: ideal DCG is 1
        if results and item.get("section") and results[0]["source"] == item["doc"]:
            sections += int(results[0]["section"].endswith(item["section"]))
        if first is None or first > 3:
            report.misses.append(f"{item['q']} → expected {item['doc']}, got {[r['source'] for r in results[:3]]}")
    n = max(len(labeled), 1)
    report.recall = {k: v / n for k, v in report.recall.items()}
    report.mrr, report.ndcg10 = reciprocal / n, gains / n
    with_section = sum(1 for item in labeled if item.get("section")) or 1
    report.section_precision = sections / with_section
    return report
