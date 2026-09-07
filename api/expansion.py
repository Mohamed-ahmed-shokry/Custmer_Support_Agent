"""Opt-in query expansion: LLM reformulations fused with reciprocal-rank fusion.

Only ``langchain_core`` is imported at module level (safe on Python 3.14);
``langchain_openai`` is imported lazily inside the LLM factory.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

logger = logging.getLogger(__name__)

RRF_CONSTANT = 60
DEFAULT_EXPANSION_COUNT = 3

EXPANSION_SYSTEM_PROMPT = (
    "Rewrite the user's support question into distinct alternative phrasings "
    "that would match different wordings of the same answer in a document store. "
    "Output one phrasing per line, with no numbering, bullets, or commentary."
)


def _default_llm(model: str = "gpt-4o-mini"):
    from langchain_openai import ChatOpenAI  # noqa: PLC0415 - lazy, see ADR-001

    return ChatOpenAI(model=model)


def rewrite_queries(question: str, llm=None, count: int = DEFAULT_EXPANSION_COUNT) -> list[str]:
    """Return ``[question, *reformulations]``; falls back to ``[question]``."""
    cleaned = (question or "").strip()
    if not cleaned or count <= 1:
        return [cleaned] if cleaned else []
    try:
        response = (llm or _default_llm()).invoke(
            f"{EXPANSION_SYSTEM_PROMPT}\n\nQuestion: {cleaned}\n"
            f"Provide {count - 1} alternative phrasings."
        )
        content = getattr(response, "content", "") or ""
        variants = [line.strip(" -•\t") for line in str(content).splitlines()]
        seen = {cleaned.lower()}
        reformulations = []
        for variant in variants:
            if variant and variant.lower() not in seen:
                seen.add(variant.lower())
                reformulations.append(variant)
            if len(reformulations) >= count - 1:
                break
        return [cleaned, *reformulations]
    except Exception:
        logger.exception("Query expansion failed, using the original question")
        return [cleaned]


def _document_key(document: Document) -> tuple[Any, ...]:
    metadata = document.metadata or {}
    return (
        metadata.get("file_id"),
        metadata.get("filename") or metadata.get("source"),
        metadata.get("page"),
        metadata.get("chunk_index"),
        document.page_content,
    )


def reciprocal_rank_fuse(ranked_lists: list[list[Document]], k: int) -> list[Document]:
    """Merge ranked doc lists with RRF, preserving first-seen order on ties."""
    scores: dict[tuple[Any, ...], float] = {}
    documents: dict[tuple[Any, ...], Document] = {}
    for ranked in ranked_lists:
        for rank, document in enumerate(ranked, start=1):
            key = _document_key(document)
            documents.setdefault(key, document)
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_CONSTANT + rank)
    ordered = sorted(scores, key=lambda key: scores[key], reverse=True)
    return [documents[key] for key in ordered[:k]]


class ExpandedVectorRetriever(BaseRetriever):
    """Fan out a query into reformulations, then RRF-merge vector results."""

    vectorstore: Any
    k: int = 5
    llm: Any = None
    expansion_count: int = DEFAULT_EXPANSION_COUNT
    search_kwargs: dict[str, Any] | None = None

    def _get_relevant_documents(self, query: str, *, run_manager: Any = None) -> list[Document]:
        variants = rewrite_queries(query, llm=self.llm, count=self.expansion_count)
        ranked = [
            self.vectorstore.similarity_search(variant, k=self.k, **(self.search_kwargs or {}))
            for variant in variants
        ]
        return reciprocal_rank_fuse(ranked, self.k)
