"""Dependency-free lexical reranking (term-overlap signal).

This is a lightweight baseline, not a cross-encoder: it reorders already
retrieved chunks so keyword-dense matches surface first. Only
``langchain_core`` is imported (safe on Python 3.14, see ADR-001).
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

_TOKEN_RE = re.compile(r"[a-z0-9]+")
MIN_TOKEN_LENGTH = 3

STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "do",
        "does",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "the",
        "to",
        "what",
        "when",
        "where",
        "which",
        "who",
        "with",
    }
)


def tokenize(text: str) -> set[str]:
    """Lowercase alphanumeric tokens of length >= 3, minus stopwords."""
    return {
        token
        for token in _TOKEN_RE.findall(text.lower())
        if len(token) >= MIN_TOKEN_LENGTH and token not in STOPWORDS
    }


def overlap_score(query_terms: set[str], document: Document) -> tuple[int, int]:
    """Return (distinct-term coverage, total term hits) for a document."""
    if not query_terms:
        return (0, 0)
    content = document.page_content.lower()
    coverage = sum(1 for term in query_terms if term in content)
    hits = sum(content.count(term) for term in query_terms)
    return (coverage, hits)


def rerank_by_term_overlap(
    question: str, documents: list[Document], top_n: int
) -> list[Document]:
    """Reorder documents by lexical overlap; stable for ties and empties."""
    if top_n <= 0:
        return []
    query_terms = tokenize(question)
    if not query_terms:
        return list(documents[:top_n])
    # Python's sort is stable, so ties keep their retrieved order.
    ranked = sorted(documents, key=lambda doc: overlap_score(query_terms, doc), reverse=True)
    return ranked[:top_n]


class RerankingRetriever(BaseRetriever):
    """Wrap another retriever and reorder its hits by lexical overlap."""

    base: Any
    top_n: int = 5

    def _get_relevant_documents(self, query: str, *, run_manager: Any = None) -> list[Document]:
        documents = self.base.invoke(query)
        return rerank_by_term_overlap(query, list(documents), self.top_n)
