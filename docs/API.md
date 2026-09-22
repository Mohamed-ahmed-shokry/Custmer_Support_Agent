# API Reference (v0.22.0)

Base URL defaults to `http://localhost:8000` (`APP_API_BASE_URL` in the UI).

All responses carry an `X-Request-ID` header (echoed if the client sends one).

## Security (opt-in)

- When `API_KEY` is set, send `X-API-Key` on every request except
  `/health*`, `/metrics*`, `/config`, and `/docs`/`/openapi.json`/`/redoc`.
  Missing/invalid key → `401`.
- When `RATE_LIMIT_PER_MIN` is positive, each client IP gets that many
  non-exempt requests per sliding 60-second window → `429` when exceeded.
- When `TOKEN_DAILY_BUDGET_EST` is positive, each client IP gets that many
  estimated tokens per day across chat/stream turns → `429` when the next
  turn would exceed it. Estimates are char-based, not billing figures.

## Health & observability

- `GET /health` → `{status, app, version}`.
- `GET /health/live` → `{"status": "ok"}` (Kubernetes liveness).
- `GET /health/ready` → `{"ready": bool, "checks": {"sqlite": ..., "chroma_dir": ...}}`
  with HTTP 200 when ready, 503 otherwise (Kubernetes readiness).
- `GET /metrics` → Prometheus-text counters (`rag_agent_*`) including
  `latency_avg_seconds_{chat,stream,upload,other}`.
- `GET /metrics.json` → same counters as JSON plus `uptime_seconds`.

## Configuration

- `GET /config` → `{supported_models, default_model, supported_export_formats, max_upload_size_bytes, max_bulk_upload_files, version}`. Dynamic runtime discovery endpoint allowing clients and frontends to align models, export formats, and upload limits.

## Chat

`POST /chat` accepts:

```json
{
  "question": "How do I request maintenance?",
  "session_id": null,
  "model": "gpt-4o-mini",
  "file_ids": [7],
  "source_filename": "tenant-handbook.pdf",
  "use_hybrid": true,
  "collections": ["clients-acme"],
  "expand_query": true,
  "rerank": true,
  "use_cross_encoder_rerank": true,
  "cross_encoder_model": "cross-encoder/ms-marco-MiniLM-L-6-v2"
}
```

- `file_ids` (max 50), `source_filename`, `use_hybrid`, `collections`
  (max 20), `expand_query`, `rerank`, `use_cross_encoder_rerank`, and
  `cross_encoder_model` are optional retrieval controls.
  Omit them for plain vector search over all documents.
- `expand_query` fans the question out into LLM reformulations and fuses the
  per-variant vector hits with reciprocal-rank fusion (takes precedence over
  `use_hybrid`; filters still apply to every variant).
- `rerank` reorders the retrieved candidates with a dependency-free
  term-overlap signal and trims back to `k` (extra candidates are fetched
  automatically; composes with filters, hybrid, and expansion).
- `use_cross_encoder_rerank` enables semantic reranking using a cross-encoder
  model (takes precedence over `rerank`). Configure the model via
  `cross_encoder_model` (default: `cross-encoder/ms-marco-MiniLM-L-6-v2`).
- Success → `200` with `{answer, session_id, model, sources[]}`.
- Retrieval failure → `502`; bad input → `422`.
- Each chat/stream turn adds approximate token usage (`~4 chars/token`)
  to the `prompt_tokens_est` / `completion_tokens_est` metrics.
- Only the most recent `MAX_HISTORY_TURNS` conversation turns are sent for
  context (default 10); full history stays in SQLite and `/sessions`.

`POST /chat/stream` accepts the same body and returns SSE:

- `data: <answer chunk>` events (concatenate for the full answer),
- `event: sources` with a JSON array of source metadata,
- `event: error` when generation fails.

## Documents

`POST /upload-doc` (multipart `file`, plus optional query params):

- `chunking_strategy`: `recursive` (default) or `markdown`.
- `chunk_size`: 100–4000 (default 1000).
- `chunk_overlap`: must be `>= 0` and `< chunk_size` (default 200).
- `collection`: target collection (default `default`; invalid names → `400`).
- Supported types: `.pdf`, `.docx`, `.html`, `.md`, `.txt`, `.csv`.
- Size cap: `MAX_UPLOAD_MB` (default 25 MB) → `413` when exceeded.
- Exact-duplicate content is rejected → `409` naming the existing file.

`POST /upload-docs` accepts up to `MAX_BULK_FILES` files (default 10) with
the same query params and returns per-file results:

```json
{"results": [{"filename": "a.pdf", "status": "indexed", "file_id": 7}], "uploaded": 1, "failed": 0}
```

Each result is `indexed` (with `file_id`) or `error` (with `detail`); the
endpoint itself returns `200` unless the request is malformed.

Collection names are lowercase letters, numbers, `-`/`_` (max 64 chars).

`GET /list-docs` → array of `{id, filename, collection, upload_timestamp}`;
filter with `?collection=<name>`.

`GET /collections` → sorted array of known collection names.

`GET /collections/details` → array of `{collection, document_count, chunk_count, file_formats, earliest_upload, latest_upload}` for each collection, providing document counts, chunk counts, file format distribution, and upload timestamps.

`DELETE /collections/{name}` → removes every document and chunk in the
collection (the `default` collection is protected → `400`; unknown → `404`;
Chroma failure → `500`).

`PATCH /collections/{name}` with `{"collection": "new-name"}` → retags every
document and chunk (`409` when the target exists, `404` when the source is
empty, `422` for an invalid name).

`GET /docs/{file_id}` → `{id, filename, upload_timestamp, collection, sha256, chunk_count, chunks: [{chunk_index, page, preview, metadata}]}` (`404` when unknown). Inspects document metadata and chunk breakdown directly from SQLite and Chroma.

`POST /delete-docs` with `{"file_ids": [1, 2, 3]}` accepts up to 50 document IDs for bulk deletion and returns `{results: [{file_id, status, error}], deleted: int, failed: int}` where status is `deleted`, `not_found`, or `error`.

`GET /stats` → `{documents, collections, sessions, messages}` library totals
computed with `COUNT` queries.

## Search

`POST /search` runs the retrieval pipeline without spending chat tokens:

```json
{
  "question": "How do I request maintenance?",
  "k": 5,
  "collections": ["clients-acme"],
  "use_hybrid": true,
  "expand_query": false,
  "rerank": true,
  "use_cross_encoder_rerank": true,
  "cross_encoder_model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
  "score_threshold": 0.7
}
```

- Accepts the same retrieval controls as `/chat` (`k` is 1–50).
- `use_cross_encoder_rerank` enables semantic reranking using a cross-encoder
  model (takes precedence over `rerank`). Configure the model via
  `cross_encoder_model` (default: `cross-encoder/ms-marco-MiniLM-L-6-v2`).
- `score_threshold` (optional, 0.0–1.0): filter out hits below the given relevance confidence score.
- Success → `200` with `{hits: [{rank, preview, file_id, filename, page,
  chunk_index, collection, score}]}`; retrieval failure → `502`. Each hit includes a `score` field (0.0–1.0 relevance confidence) when available from the retriever.

`POST /delete-doc` with `{"file_id": 42}` removes Chroma chunks and the
SQLite record (`404` when unknown).

## Sessions

- `GET /sessions` → array of `{session_id, message_count, last_active,
  preview, label, status, tags}` ordered by most recent activity (`preview` is the
  truncated first question). Optional query params: `status` (one of `active`, `resolved`, `escalated`, `closed`) and `tag` (case-insensitive) to filter sessions.
- `GET /sessions/{session_id}/history` → array of `{role, content}` pairs
  for that session (`400` for a blank id). The Streamlit sidebar uses these
  to list and reload past conversations.
- `PATCH /sessions/{session_id}` with `{"label": "...", "status": "...", "tags": [...]}` → updates session metadata. `label` (1–80 chars), `status` (one of `active`, `resolved`, `escalated`, `closed`), `tags` (array of strings). Returns updated session info (`404` when unknown, `422` for invalid input).
- `DELETE /sessions/{session_id}` → removes the session history, label,
  and feedback (`400` for a blank id, `404` when unknown).
- `POST /delete-sessions` with `{"session_ids": ["s1", "s2"]}` (up to 50 sessions) deletes multiple sessions with cascading removal of chat history and feedback, returning `{results: [{session_id, status, error}], deleted: int, failed: int}`.
- `DELETE /sessions?before=<ISO datetime>` → prunes sessions inactive since
  the cutoff, including labels and feedback (`400` for a bad date).
- `GET /sessions/{session_id}/export?format=markdown|json|csv` → exports the conversation transcript in the requested format (`text/markdown`, `application/json`, or `text/csv`). Default format is `markdown`. Invalid format → `400`. `404` when the session has no history.
- `GET /sessions/search?q=<query>&limit=20` → searches SQLite conversation history
  for matching questions and answers, returning an array of `{session_id, match_count, last_active, preview, label}`.

## Quotas

- `GET /quota` → `{budget, used, remaining, unlimited}` for the caller IP
  against `TOKEN_DAILY_BUDGET_EST` (`remaining` is `null` when unlimited).

## Feedback

- `POST /feedback` with `{"session_id": "...", "rating": 1, "comment": "Optional notes"}` records a
  thumbs up (`1`) or down (`-1`) with an optional comment (max 1000 characters); invalid rating → `422`.
  Returns `{"message": "Feedback recorded.", "feedback_id": <int>}`. Totals surface as
  the `feedback_up` / `feedback_down` metrics.
- `GET /feedback?rating=1|-1&session_id=...&limit=50&offset=0` → `{items: [{id, session_id, rating, comment, created_at}], total, limit, offset}`.
  Returns paginated feedback records with optional filtering by rating and session ID (`limit` 1–100).
- `GET /sessions/{session_id}/feedback` → array of `{id, session_id, rating, comment, created_at}` feedback
  entries recorded for the specified session (`404` when session is unknown).
- `GET /feedback/analytics?recent_comments_limit=5` → `{total_feedback, positive_feedback, negative_feedback, satisfaction_rate, total_comments, comment_rate, recent_comments: [...]}`.
  Returns aggregated CSAT analytics: satisfaction rate (%), positive/negative counts, total comments, comment rate (%), and recent comments with ratings. `recent_comments_limit` (0–50, default 5) controls how many recent commented entries to include.

## Evaluation Harness

`scripts/eval_retrieval.py` evaluates retrieval accuracy against golden test sets:
- `--golden <path>`: path to golden question dataset (default `docs/eval/golden.json`).
- `--expand`: evaluate with query expansion (LLM reformulations fused via RRF).
- `--hybrid`: evaluate with hybrid BM25 + dense vector search.
- `--rerank`: evaluate with term-overlap lexical reranking.
- `--collection <name>`: scope retrieval evaluation to a specific collection.
- `--compare`: evaluate baseline vector search vs configured enhanced strategy side-by-side.
- `--json-output <path>`: write structured evaluation metrics and per-case results to JSON.

