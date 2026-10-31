"""Text normalization shared by indexing and queries.

PostgreSQL's ``simple`` configuration splits on spaces and punctuation, which leaves Chinese text as one long
token. Instead of a segmentation extension (pg_jieba/zhparser, not available on every managed PostgreSQL), CJK
runs are indexed as overlapping character bigrams, the approach of Lucene's CJKAnalyzer; Latin text is
lowercased words. Indexing and querying use the same function, so matching is consistent.
"""

from __future__ import annotations

import re
import unicodedata

_CJK = r"㐀-䶿一-鿿豈-﫿぀-ヿ가-힯"
_TOKEN = re.compile(rf"[{_CJK}]+|[0-9a-z]+(?:[._-][0-9a-z]+)*")
_CJK_RUN = re.compile(rf"^[{_CJK}]+$")


def _singular(word: str) -> str:
    """Light English plural folding (policies → policy, boxes → box, passwords → password)."""
    if len(word) <= 3 or not word.isalpha():
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("ches", "shes", "sses", "xes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def tokens(text: str) -> list[str]:
    """Latin words and numbers (lowercased, NFKC, plurals folded) plus CJK bigrams (single characters kept)."""
    out: list[str] = []
    for match in _TOKEN.finditer(unicodedata.normalize("NFKC", text).lower()):
        token = match.group(0)
        if _CJK_RUN.match(token):
            out.extend([token] if len(token) == 1 else [token[i : i + 2] for i in range(len(token) - 1)])
        else:
            out.append(_singular(token))
    return out


def index_text(text: str) -> str:
    """The string given to ``to_tsvector('simple', …)``."""
    return " ".join(tokens(text))


def query_text(query: str) -> str:
    """An OR query over the query's tokens for ``to_tsquery('simple', …)``; ranking prefers chunks with more."""
    unique = list(dict.fromkeys(t.replace("'", "") for t in tokens(query)))
    return " | ".join(f"'{t}'" for t in unique if t)


def estimate_tokens(text: str) -> int:
    """Rough model-token count (CJK characters ≈ 1 token, Latin words ≈ 1.3) for chunk sizing."""
    cjk = len(re.findall(rf"[{_CJK}]", text))
    words = len(re.findall(r"[A-Za-z0-9]+", text))
    return cjk + int(words * 1.3)


INJECTION = re.compile(
    r"(ignore (all |any )?(previous|prior|above) instructions|disregard (the )?(system|previous)|you are now|"
    r"忽略(之前|以上|所有)的?(指令|说明)|系统提示词)",
    re.IGNORECASE,
)


def suspected_instructions(text: str) -> bool:
    """Heuristic prompt-injection flag (Part 7 §9): the chunk is still returned, marked as such."""
    return bool(INJECTION.search(text))
