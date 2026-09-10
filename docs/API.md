# API Reference (v0.6.0)

Base URL defaults to `http://localhost:8000` (`APP_API_BASE_URL` in the UI).

All responses carry an `X-Request-ID` header (echoed if the client sends one).

## Security (opt-in)

- When `API_KEY` is set, send `X-API-Key` on every request except
  `/health*`, `/metrics*`, and `/docs`/`/openapi.json`/`/redoc`.
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
  "rerank": true
}
```

- `file_ids` (max 50), `source_filename`, `use_hybrid`, `collections`
  (max 20), `expand_query`, and `rerank` are optional retrieval controls.
  Omit them for plain vector search over all documents.
- `expand_query` fans the question out into LLM reformulations and fuses the
  per-variant vector hits with reciprocal-rank fusion (takes precedence over
  `use_hybrid`; filters still apply to every variant).
- `rerank` reorders the retrieved candidates with a dependency-free
  term-overlap signal and trims back to `k` (extra candidates are fetched
  automatically; composes with filters, hybrid, and expansion).
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

Collection names are lowercase letters, numbers, `-`/`_` (max 64 chars).

`GET /list-docs` → array of `{id, filename, collection, upload_timestamp}`;
filter with `?collection=<name>`.

`GET /collections` → sorted array of known collection names.

`DELETE /collections/{name}` → removes every document and chunk in the
collection (the `default` collection is protected → `400`; unknown → `404`;
Chroma failure → `500`).

## Search

`POST /search` runs the retrieval pipeline without spending chat tokens:

```json
{
  "question": "How do I request maintenance?",
  "k": 5,
  "collections": ["clients-acme"],
  "use_hybrid": true,
  "expand_query": false,
  "rerank": true
}
```

- Accepts the same retrieval controls as `/chat` (`k` is 1–50).
- Success → `200` with `{hits: [{rank, preview, file_id, filename, page,
  chunk_index, collection}]}`; retrieval failure → `502`.

`POST /delete-doc` with `{"file_id": 42}` removes Chroma chunks and the
SQLite record (`404` when unknown).

## Sessions

- `GET /sessions` → array of `{session_id, message_count, last_active,
  preview, label}` ordered by most recent activity (`preview` is the
  truncated first question).
- `GET /sessions/{session_id}/history` → array of `{role, content}` pairs
  for that session (`400` for a blank id). The Streamlit sidebar uses these
  to list and reload past conversations.
- `PATCH /sessions/{session_id}` with `{"label": "..."}` → renames a session
  (1–80 chars; `404` when unknown, `422` for a blank/oversize label).
- `DELETE /sessions/{session_id}` → removes the session history and label
  (`400` for a blank id, `404` when unknown).
- `GET /sessions/{session_id}/export` → the conversation as a markdown
  transcript download (`404` when the session has no history).

## Quotas

- `GET /quota` → `{budget, used, remaining, unlimited}` for the caller IP
  against `TOKEN_DAILY_BUDGET_EST` (`remaining` is `null` when unlimited).
