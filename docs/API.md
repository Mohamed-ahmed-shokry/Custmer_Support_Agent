# API Reference (v0.30.0)

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

`GET /collections/{name}/analytics` → `{collection, total_documents, total_chunks, avg_chunk_length, min_chunk_length, max_chunk_length, median_chunk_length, strategy_distribution, length_histogram}` providing detailed character length statistics, strategy breakdown, and length histogram buckets (`<200`, `200-500`, `500-1000`, `1000-2000`, `>2000`).

`POST /collections/{name}/rechunk` with `{"chunking_strategy": "recursive" | "markdown" | "semantic", "chunk_size": int, "chunk_overlap": int}` → batch re-chunks every document in the collection that has stored source text, updates their Chroma chunks and source metadata, and returns `{message, collection, strategy, chunk_size, chunk_overlap, total_documents, rechunked_documents, skipped_documents, failed_documents, total_chunks_created, items: [{file_id, filename, status, chunk_count, error_message}]}`. Documents lacking stored source text (ingested prior to v0.25.0) are safely skipped and reported.

`DELETE /collections/{name}` → removes every document and chunk in the
collection (the `default` collection is protected → `400`; unknown → `404`;
Chroma failure → `500`).

`PATCH /collections/{name}` with `{"collection": "new-name"}` → retags every
document and chunk (`409` when the target exists, `404` when the source is
empty, `422` for an invalid name).

`GET /docs/{file_id}` → `{id, filename, upload_timestamp, collection, sha256, chunk_count, chunks: [{chunk_index, page, preview, metadata}], chunking_strategy, chunk_size, chunk_overlap}` (`404` when unknown). Inspects document metadata, persistent chunking options, and chunk breakdown directly from SQLite and Chroma.

`POST /docs/{file_id}/rechunk` with `{"chunking_strategy": "recursive" | "markdown" | "semantic", "chunk_size": int, "chunk_overlap": int}` → re-splits the document's stored source text with the requested chunking strategy and sizes, replaces the Chroma vectorstore chunks, updates persistent document source options, and returns the refreshed `DocumentDetailResponse` (`400` if source text is unavailable or parameters are invalid, `404` if document not found, `500` on indexing failure).

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

- `GET /sessions` → array of `{session_id, message_count, last_active, preview, label, status, tags, summary, resolution_notes}` ordered by most recent activity (`preview` is the truncated first question). Optional query params: `status` (one of `active`, `resolved`, `escalated`, `closed`) and `tag` (case-insensitive) to filter sessions.
- `GET /sessions/triage-analytics` → returns aggregated support operations KPIs: `{total_sessions, active_count, resolved_count, escalated_count, closed_count, resolution_rate, escalation_rate, avg_turns_per_session, top_tags: [{tag, count}]}`.
- `GET /sessions/{session_id}/history` → array of `{role, content}` pairs for that session (`400` for a blank id). The Streamlit sidebar uses these to list and reload past conversations.
- `POST /sessions/{session_id}/summarize` with `{"model": "gpt-4o-mini", "save_summary": true}` → generates conversation dialogue summary, key bullet points, detected sentiment (`positive`, `neutral`, `negative`), and suggested domain tags. When `save_summary` is true, persists the summary and merges suggested tags into session metadata. Returns `{session_id, summary, key_points, sentiment, suggested_tags, saved}` (`404` when session history is empty).
- `PATCH /sessions/{session_id}` with `{"label": "...", "status": "...", "tags": [...], "summary": "...", "resolution_notes": "..."}` → updates session metadata. `label` (1–80 chars), `status` (`active`, `resolved`, `escalated`, `closed`), `tags` (string or array), `summary` (max 2000 chars), `resolution_notes` (max 2000 chars). Returns updated session info (`404` when unknown, `422` for invalid input).
- `DELETE /sessions/{session_id}` → removes the session history, label, and feedback (`400` for a blank id, `404` when unknown).
- `POST /delete-sessions` with `{"session_ids": ["s1", "s2"]}` (up to 50 sessions) deletes multiple sessions with cascading removal of chat history and feedback, returning `{results: [{session_id, status, error}], deleted: int, failed: int}`.
- `DELETE /sessions?before=<ISO datetime>` → prunes sessions inactive since the cutoff, including labels and feedback (`400` for a bad date).
- `GET /sessions/{session_id}/export?format=markdown|json|csv` → exports conversation transcript enriched with session metadata (`status`, `tags`, `summary`, `resolution_notes`) alongside turns in requested format (`text/markdown`, `application/json`, or `text/csv`). Default format is `markdown`. Invalid format → `400`. `404` when the session has no history.
- `GET /sessions/search?q=<query>&limit=20` → searches SQLite conversation history for matching questions and answers, returning an array of `{session_id, match_count, last_active, preview, label}`.

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

## Webhooks & Alerts

The agent includes an automated webhook event dispatcher and alerting engine. Subscribed endpoints receive JSON HTTP POST requests when important support events occur (e.g., ticket escalation, ticket resolution, or negative CSAT ratings).

### Signature Verification

When a webhook is configured with a shared secret, every dispatched HTTP request includes an HMAC-SHA256 signature in the headers for authenticity verification:
- `X-Webhook-Event`: The event name (e.g., `session.escalated`, `session.resolved`, `feedback.negative`, `test.ping`).
- `X-Webhook-Timestamp`: Unix epoch timestamp string (seconds) when the request was prepared.
- `X-Webhook-Signature`: Lowercase hex-encoded HMAC-SHA256 digest computed over `f"{timestamp}.{raw_json_body}"` using the shared secret.

Receivers can verify authenticity by computing `hmac.new(secret.encode(), f"{timestamp}.{raw_body}".encode(), hashlib.sha256).hexdigest()` and comparing using constant-time comparison `hmac.compare_digest()`.

### Supported Events
- `session.escalated`: Dispatched when a session status transitions to `escalated`. Payload data includes `session_id`, `status`, `previous_status`, `tags`, `summary`, and `resolution_notes`.
- `session.resolved`: Dispatched when a session status transitions to `resolved`. Payload data includes `session_id`, `status`, `previous_status`, `tags`, `summary`, and `resolution_notes`.
- `feedback.negative`: Dispatched when a user submits negative feedback (`rating: -1`). Payload data includes `session_id`, `feedback_id`, `rating`, `comment`, and `created_at`.
- `test.ping`: Dispatched on manual ping to verify connectivity.
- `*`: Wildcard subscription receiving all events.

### Endpoints
- `POST /webhooks` with `{"url": "https://example.com/alerts", "events": "session.escalated,feedback.negative", "secret": "...", "is_active": true}`: Registers a new webhook subscription. Returns `201` with `{id, url, events, is_active, failure_count, created_at, updated_at}`.
- `GET /webhooks`: Lists all registered webhooks. Returns array of webhook records.
- `GET /webhooks/{webhook_id}`: Returns detailed information for a webhook, including recent delivery logs. Returns `404` if not found.
- `PATCH /webhooks/{webhook_id}` with `{"url": "...", "events": "...", "secret": "...", "is_active": bool}`: Partially updates a webhook configuration. Returns updated webhook record (`404` if not found).
- `DELETE /webhooks/{webhook_id}`: Deletes the webhook subscription and its delivery logs. Returns `{"message": "Webhook deleted.", "id": <int>}` (`404` if not found).
- `POST /webhooks/{webhook_id}/ping`: Dispatches a `test.ping` event to the webhook URL. Returns `{"success": bool, "status_code": int|null, "error": str|null}` (`404` if not found).
- `GET /webhooks/deliveries?limit=50&offset=0`: Returns paginated audit logs of webhook delivery attempts across all webhooks: `{items: [{id, webhook_id, event, url, status_code, success, error_message, delivered_at}], total, limit, offset}`.

## Canned Responses & Action Macros Engine

The agent provides a pre-approved canned responses and action macro templates engine for real estate customer support operations. Templates support category classification, shortcut triggers (e.g., `/rent-pay`, `/emerg-maint`), dynamic variable substitution (`{customer_name}`, `{session_id}`, `{unit_id}`, `{agent_name}`, `{date}`, `{support_contact}`), and automated session actions (status transitions to `resolved` or `escalated` triggering webhooks, tag assignment, conversation injection).

### Endpoints

- `POST /macros`: Create a new macro template.
  - Body: `{"title": "...", "shortcut": "/shortcut", "category": "General", "content": "...", "tags": ["tag1"], "status_action": "resolved|escalated|active|closed|null"}`.
  - Returns `201` with created macro record. Returns `400` if shortcut is already registered.
- `GET /macros?category=...&tag=...&search=...`: List macro templates with optional category, tag, or keyword search filtering.
  - Returns array of macro records.
- `GET /macros/categories`: Returns distinct categories across all templates.
  - Returns `{"categories": ["General", "Billing", "Leasing", "Maintenance"]}`.
- `GET /macros/{macro_id}`: Returns a macro by ID. Returns `404` if not found.
- `PATCH /macros/{macro_id}`: Partially update a macro's title, shortcut, category, content, tags, or status_action. Returns `404` if not found.
- `DELETE /macros/{macro_id}`: Delete a macro by ID. Returns `{"message": "Macro {macro_id} deleted."}` (`404` if not found).
- `POST /macros/{macro_id}/render`: Preview a rendered template with provided variables without applying to session.
  - Body: `{"variables": {"customer_name": "Alice"}, "fallback_defaults": true}`.
  - Returns `{"macro_id": <int>, "rendered_content": "...", "unresolved_variables": [], "status_action": "..."}`.
- `POST /sessions/{session_id}/apply-macro`: Apply a macro directly to an active session.
  - Body: `{"macro_id": <int>, "shortcut": "/...", "variables": {...}, "update_status": true, "append_tags": true, "fallback_defaults": true}`.
  - Automatically renders variables, logs the message into session chat history, updates session status and tags in SQLite, dispatches real-time webhooks (`session.resolved` or `session.escalated`), and returns the applied summary.
- `POST /macros/suggest`: Suggest matching macros for an arbitrary customer query or message.
  - Body: `{"query": "Help, pipe leaking in Unit 402", "session_id": "optional-session", "category": null, "top_k": 3, "min_score": 0.3}`.
  - Returns `{"query": "...", "detected_intent": "maintenance_emergency", "intent_confidence": 0.95, "extracted_variables": {"unit_id": "Unit 402"}, "suggestions": [...], "total_matches": 1}`.
- `GET /sessions/{session_id}/macro-suggestions?top_k=3&min_score=0.3&category=...`: Real-time macro suggestions tailored to an active chat session's latest tenant inquiry.
  - Automatically detects query intent, extracts entities (unit IDs, names), binds active `session_id`, and returns ranked recommendations with rendered previews. Returns `404` if session is not found.

## Evaluation Harness

`scripts/eval_retrieval.py` evaluates retrieval accuracy against golden test sets:
- `--golden <path>`: path to golden question dataset (default `docs/eval/golden.json`).
- `--expand`: evaluate with query expansion (LLM reformulations fused via RRF).
- `--hybrid`: evaluate with hybrid BM25 + dense vector search.
- `--rerank`: evaluate with term-overlap lexical reranking.
- `--collection <name>`: scope retrieval evaluation to a specific collection.
- `--compare`: evaluate baseline vector search vs configured enhanced strategy side-by-side.
- `--json-output <path>`: write structured evaluation metrics and per-case results to JSON.

