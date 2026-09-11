# Customer Support RAG Agent (v0.13.0)

A local-first customer support assistant for real estate and property management workflows. The app combines a FastAPI backend, a Streamlit chat UI, SQLite chat/document metadata, and a local Chroma vector store backed by OpenAI embeddings.

## Features

- Conversational customer support over uploaded PDF, DOCX, HTML, MD, TXT, and CSV documents.
- Exact-duplicate uploads rejected (`409`) via content hashing.
- Retrieval augmented generation with bounded chat history awareness
  (`MAX_HISTORY_TURNS`).
- Streaming answers over Server-Sent Events (`POST /chat/stream`) with a
  non-streaming fallback (`POST /chat`).
- Retrieval filters per request: `file_ids`, `source_filename`, `use_hybrid`
  (BM25 + vector hybrid with graceful vector-only fallback), and
  `collections` to scope answers to document collections.
- Opt-in query expansion (`expand_query`): LLM reformulations fused with
  reciprocal-rank fusion; enable via the sidebar toggle or
  `USE_QUERY_EXPANSION`.
- Opt-in lexical rerank (`rerank`): term-overlap reordering that composes
  with filters, hybrid, and expansion; sidebar toggle or `USE_RERANK`.
- Session export to markdown (`GET /sessions/{id}/export`, UI download).
- Document collections group uploads, retrieval, and the UI picker, with
  automatic migration for pre-v0.6.0 databases; whole collections can be
  removed (`DELETE /collections/{name}`, `default` protected).
- Retrieval inspection without chat cost (`POST /search` returns ranked
  chunks with metadata).
- Configurable chunking (recursive / markdown-aware) plus chunk-size/overlap
  validation and a configurable upload size cap.
- Source-aware answers with document metadata returned by the API.
- Streamlit document upload, listing, deletion, chat controls, and a past-sessions switcher with previews, rename, session deletion, and quota display.
- Dark-mode UI theme (`.streamlit/config.toml`, shipped in the image).
- File logs redact emails, phone numbers, and SSN-like patterns.
- Local SQLite logging for sessions and document records.
- Observability: `X-Request-ID` tracing, `/health/live`, `/health/ready`,
  `/metrics` (Prometheus text) and `/metrics.json` with per-route latency
  averages and approximate token-usage counters, `LOG_FORMAT`/`LOG_LEVEL`.
  The Streamlit sidebar shows a backend metrics panel.
- Releases: pushing a `v*` tag runs the full verification suite and creates
  a GitHub release.
- Opt-in security: `API_KEY` (`X-API-Key` header), per-IP rate limiting
  (`RATE_LIMIT_PER_MIN`), and daily token quotas (`TOKEN_DAILY_BUDGET_EST`);
  health/metrics/docs paths stay public.
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
- `MAX_HISTORY_TURNS` (default `10`)
- `USE_HYBRID_RETRIEVER` (default `false`)
- `HYBRID_BM25_WEIGHT` / `HYBRID_VECTOR_WEIGHT` (default `0.5` each)
- `USE_QUERY_EXPANSION` (default `false`)
- `USE_RERANK` (default `false`)
- `EXPANSION_COUNT` (default `3`)
- `MAX_UPLOAD_MB` (default `25`)
- `LOG_FORMAT` (`text` or `json`, default `text`)
- `LOG_LEVEL` (default `INFO`)
- `API_KEY` (empty = auth disabled; when set, send `X-API-Key`)
- `RATE_LIMIT_PER_MIN` (default `0` = off)
- `TOKEN_DAILY_BUDGET_EST` (default `0` = off)

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
`docs/RUNBOOK.md` for operations. For production-like defaults (2 workers,
JSON logs, resource limits, restarts), overlay the prod file:

```powershell
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

For a staging setup (single worker, debug logs, generous rate limit), swap
in the staging overlay instead:

```powershell
docker compose -f docker-compose.yml -f docker-compose.staging.yml up --build -d
```

## API quick reference

- `GET /health` — basic liveness with app name/version.
- `GET /health/live` — process liveness probe.
- `GET /health/ready` — readiness probe (SQLite + Chroma dir checks).
- `GET /metrics` / `GET /metrics.json` — in-memory request counters,
  latency averages, and estimated token usage.
- `POST /chat` — JSON answer with `sources`.
- `POST /chat/stream` — SSE stream (`data:` answer chunks,
  `event: sources` metadata, `event: error` on failure).
- `POST /upload-doc` — multipart upload with optional `chunking_strategy`,
  `chunk_size` (100–4000), `chunk_overlap` (< chunk size).
- `GET /list-docs`, `POST /delete-doc` — document metadata management.
- `GET /collections`, `PATCH`/`DELETE /collections/{name}` — collection lifecycle.
- `GET /stats` — library totals (documents, collections, sessions, messages).
- `POST /search` — ranked retrieval hits without chat cost.
- `GET /sessions`, `GET /sessions/{id}/history`, `DELETE /sessions/{id}` — past conversations.
- `GET /quota` — daily token budget usage for the caller.

Full details: `docs/API.md`. Architecture notes: `docs/ARCHITECTURE.md`.
Contributor workflow: `docs/CONTRIBUTING.md`. Roadmap: `ROADMAP.md`.
Operations: `docs/RUNBOOK.md`. Deployment: `docs/DEPLOYMENT.md`.
Kubernetes: `k8s/deployment.yaml`.

## Manual retrieval eval

Upload the `docs/` corpus, then run:

```powershell
python scripts/eval_retrieval.py
```

It checks each `docs/eval/golden.json` question against the live vector
store (needs `OPENAI_API_KEY`; not run in CI). Compare expansion against
the baseline with:

```powershell
python scripts/eval_retrieval.py --compare
```

## Testing

```powershell
python -m pytest
python -m ruff check api/ app/ tests/ scripts/
python -m mypy api/ app/ scripts/
```
