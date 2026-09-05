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
  "collections": ["clients-acme"]
}
```

- `file_ids` (max 50), `source_filename`, `use_hybrid`, and `collections`
  (max 20) are optional retrieval filters. Omit them for plain vector search
  over all documents.
- Success → `200` with `{answer, session_id, model, sources[]}`.
- Retrieval failure → `502`; bad input → `422`.
- Each chat/stream turn adds approximate token usage (`~4 chars/token`)
  to the `prompt_tokens_est` / `completion_tokens_est` metrics.

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

Collection names are lowercase letters, numbers, `-`/`_` (max 64 chars).

`GET /list-docs` → array of `{id, filename, collection, upload_timestamp}`;
filter with `?collection=<name>`.

`GET /collections` → sorted array of known collection names.

`POST /delete-doc` with `{"file_id": 42}` removes Chroma chunks and the
SQLite record (`404` when unknown).

## Sessions

- `GET /sessions` → array of `{session_id, message_count, last_active}`
  ordered by most recent activity.
- `GET /sessions/{session_id}/history` → array of `{role, content}` pairs
  for that session (`400` for a blank id). The Streamlit sidebar uses these
  to list and reload past conversations.
