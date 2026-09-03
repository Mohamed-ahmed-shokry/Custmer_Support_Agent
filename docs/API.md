# API Reference (v0.3.0)

Base URL defaults to `http://localhost:8000` (`APP_API_BASE_URL` in the UI).

All responses carry an `X-Request-ID` header (echoed if the client sends one).

## Health & observability

- `GET /health` → `{status, app, version}`.
- `GET /health/live` → `{"status": "ok"}` (Kubernetes liveness).
- `GET /health/ready` → `{"ready": bool, "checks": {"sqlite": ..., "chroma_dir": ...}}`
  with HTTP 200 when ready, 503 otherwise (Kubernetes readiness).
- `GET /metrics` → Prometheus-text counters (`rag_agent_*`).
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
  "use_hybrid": true
}
```

- `file_ids` (max 50), `source_filename`, and `use_hybrid` are optional
  retrieval filters. Omit them for plain vector search over all documents.
- Success → `200` with `{answer, session_id, model, sources[]}`.
- Retrieval failure → `502`; bad input → `422`.

`POST /chat/stream` accepts the same body and returns SSE:

- `data: <answer chunk>` events (concatenate for the full answer),
- `event: sources` with a JSON array of source metadata,
- `event: error` when generation fails.

## Documents

`POST /upload-doc` (multipart `file`, plus optional query params):

- `chunking_strategy`: `recursive` (default) or `markdown`.
- `chunk_size`: 100–4000 (default 1000).
- `chunk_overlap`: must be `>= 0` and `< chunk_size` (default 200).
- Supported types: `.pdf`, `.docx`, `.html`, `.md`, `.txt`, `.csv`.
- Size cap: `MAX_UPLOAD_MB` (default 25 MB) → `413` when exceeded.

`GET /list-docs` → array of `{id, filename, upload_timestamp}`.

`POST /delete-doc` with `{"file_id": 42}` removes Chroma chunks and the
SQLite record (`404` when unknown).
