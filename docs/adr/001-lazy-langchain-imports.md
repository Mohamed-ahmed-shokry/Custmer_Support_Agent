# ADR-001: Lazy `langchain` imports with vector-search fallback

- Status: accepted
- Date: 2026-09-04
- Context: pinned `langchain 0.3.x` pulls legacy `Chain` models whose
  `Optional[dict[str, Any]]` annotations fail under Python 3.14 + pydantic
  at import time. The project supports 3.11/3.12 primarily but CI and
  contributors may run 3.14.
- Decision: request-serving modules (`api/main.py`, `api/chroma_utils.py`)
  must not import `langchain.chains` / `langchain.retrievers` at module
  level. `get_rag_chain_for_model()` and the hybrid-retriever helpers use
  function-level imports; hybrid/BM25 failures fall back to pure vector
  search and are logged.
- Consequences: tests can mock `get_rag_chain_for_model` without importing
  langchain; hybrid search is best-effort on 3.14. Revisit when langchain
  1.x is adopted (see ROADMAP Phase 2.3 reranking notes).
