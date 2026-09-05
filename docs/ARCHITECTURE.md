# Architecture (v0.6.0)

```text
Streamlit UI --HTTP--> FastAPI API --invoke--> LangChain RAG chain
     |                      |                       |-- retriever: vector / filtered / hybrid (BM25+vector)
     |                      |                       |-- chat model: OpenAI (gpt-4o / gpt-4o-mini)
     |                      |-- SQLite (sessions, document records + collections)
     |                      |-- Chroma (persisted vector chunks + metadata)
     |                      |-- in-memory metrics / quota counters
```

## Request flow (chat)

1. Client posts `QueryInput` (question + optional `file_ids`,
   `source_filename`, `use_hybrid`, `collections`).
2. `X-Request-ID` middleware tags the request/response and enforces opt-in
   API-key auth plus per-IP rate limits.
3. The daily token quota is pre-checked against the question estimate.
4. Session history loads from SQLite; `select_retriever()` picks the
   retriever (hybrid only when requested/enabled, with vector fallback).
5. History-aware retriever + stuff-documents chain generate the answer;
   sources are de-duplicated from chunk metadata.
6. The interaction is logged to SQLite; token estimates feed both metrics
   and quota usage.

Streaming (`/chat/stream`) uses the same pipeline via `astream()` and emits
SSE events; the full answer is persisted after the stream completes.

## Retrieval modes

- **Vector (default):** Chroma similarity, `k = RETRIEVER_K`.
- **Filtered:** Chroma `where` filter on `file_id`, `filename`, and/or
  `collection`.
- **Hybrid:** BM25 over the current Chroma snapshot + vector search combined
  with `EnsembleRetriever`. BM25/ensemble imports are lazy because legacy
  `langchain.retrievers` modules break under Python 3.14 + pydantic; any
  failure falls back to vector search and is logged.

## Collections

Documents belong to a named collection (`default` unless specified).
Collection names live in both SQLite (`document_store.collection`) and
Chroma chunk metadata, so `GET /list-docs`, `GET /collections`, and chat
`collections[]` filters stay consistent. `migrate_document_store()` adds
the column to pre-v0.6.0 databases; naming rules live in
`api/collections.py` and are shared by the DB, schemas, and routes.

## Indexing

Uploads are staged to a temp file, validated (type, non-empty, size cap,
chunk params, collection name), recorded in SQLite, then chunked
(`ChunkingOptions`) and indexed with deterministic IDs
(`{file_id}:{chunk_index}`). Chroma writes retry up to 3 times with
exponential backoff; on permanent failure the SQLite record is rolled back.

## Configuration & compatibility notes

- Python 3.11/3.12 recommended; 3.14 supported via lazy `langchain` imports
  (`get_rag_chain_for_model`, hybrid helpers). Avoid top-level imports of
  `langchain.chains` / `langchain.retrievers` in request-serving modules.
- OpenAI SDK defaults handle chat/embedding retries; Chroma writes add an
  explicit retry wrapper.
- Metrics are process-local (no Prometheus dependency); scrape `/metrics`.
