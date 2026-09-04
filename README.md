# Customer Support RAG Agent (v0.3.0)

A local-first customer support assistant for real estate and property management workflows. The app combines a FastAPI backend, a Streamlit chat UI, SQLite chat/document metadata, and a local Chroma vector store backed by OpenAI embeddings.

## Features

- Conversational customer support over uploaded PDF, DOCX, HTML, MD, TXT, and CSV documents.
- Retrieval augmented generation with chat history awareness.
- Streaming answers over Server-Sent Events (`POST /chat/stream`) with a
  non-streaming fallback (`POST /chat`).
- Retrieval filters per request: `file_ids`, `source_filename`, `use_hybrid`
  (BM25 + vector hybrid with graceful vector-only fallback).
- Configurable chunking (recursive / markdown-aware) plus chunk-size/overlap
  validation and a configurable upload size cap.
- Source-aware answers with document metadata returned by the API.
- Streamlit document upload, listing, deletion, and chat controls.
- Local SQLite logging for sessions and document records.
- Observability: `X-Request-ID` tracing, `/health/live`, `/health/ready`,
  `/metrics` (Prometheus text) and `/metrics.json` with per-route latency
  averages, `LOG_FORMAT`/`LOG_LEVEL`.
- Opt-in security: `API_KEY` (`X-API-Key` header) and per-IP rate limiting
  (`RATE_LIMIT_PER_MIN`); health/metrics/docs paths stay public.
- Safe Git defaults that keep secrets, logs, databases, and vector stores out of commits.

## Architecture

```text
Streamlit UI -> FastAPI API -> LangChain RAG chain -> Chroma vector store
                            -> SQLite metadata/log store
                            -> OpenAI chat and embedding models
```

Important paths:

- `api/`: FastAPI app, schemas, database helpers, Chroma indexing, and RAG chain.
- `app/`: Streamlit UI and API client helpers.
- `docs/`: sample document corpus for local testing.
- `.env.example`: safe runtime configuration template.

## Setup

Use Python 3.11 or 3.12 for the smoothest dependency support.

1. Create and activate a virtual environment.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

2. Install dependencies.

```powershell
python -m pip install -r requirements.txt
```

3. Create a local `.env` from the example and add your own keys.

```powershell
Copy-Item .env.example .env
```

Required:

- `OPENAI_API_KEY`

Optional:

- `LANGCHAIN_TRACING_V2`
- `LANGCHAIN_API_KEY`
- `LANGCHAIN_PROJECT`
- `APP_API_BASE_URL`
- `CHROMA_PERSIST_DIR`
- `SQLITE_DB_PATH`
- `DEFAULT_MODEL`
- `RETRIEVER_K`
- `USE_HYBRID_RETRIEVER` (default `false`)
- `HYBRID_BM25_WEIGHT` / `HYBRID_VECTOR_WEIGHT` (default `0.5` each)
- `MAX_UPLOAD_MB` (default `25`)
- `LOG_FORMAT` (`text` or `json`, default `text`)
- `LOG_LEVEL` (default `INFO`)
- `API_KEY` (empty = auth disabled; when set, send `X-API-Key`)
- `RATE_LIMIT_PER_MIN` (default `0` = off)

## Run Locally

Start the API:

```powershell
uvicorn api.main:app --reload
```

Start the Streamlit app in another terminal:

```powershell
streamlit run app/streamlit_app.py
```

## Run with Docker

```powershell
Copy-Item .env.example .env
docker compose up --build
```

The API serves on `http://localhost:8000` and the UI on
`http://localhost:8501`. Data persists in the `rag-data` volume. See
`docs/RUNBOOK.md` for operations.

## API quick reference

- `GET /health` — basic liveness with app name/version.
- `GET /health/live` — process liveness probe.
- `GET /health/ready` — readiness probe (SQLite + Chroma dir checks).
- `GET /metrics` / `GET /metrics.json` — in-memory request counters.
- `POST /chat` — JSON answer with `sources`.
- `POST /chat/stream` — SSE stream (`data:` answer chunks,
  `event: sources` metadata, `event: error` on failure).
- `POST /upload-doc` — multipart upload with optional `chunking_strategy`,
  `chunk_size` (100–4000), `chunk_overlap` (< chunk size).
- `GET /list-docs`, `POST /delete-doc` — document metadata management.

Full details: `docs/API.md`. Architecture notes: `docs/ARCHITECTURE.md`.
Contributor workflow: `docs/CONTRIBUTING.md`. Roadmap: `ROADMAP.md`.

## Testing

```powershell
python -m pytest
python -m ruff check api/ app/ tests/
python -m mypy api/ app/
```
