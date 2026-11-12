# API Reference (v0.38.0)

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

- `GET /sessions` → array of `{session_id, message_count, last_active, preview, label, status, priority, tags, summary, resolution_notes}` ordered by most recent activity (`preview` is the truncated first question). Optional query params: `status` (one of `active`, `resolved`, `escalated`, `closed`), `tag` (case-insensitive), and `priority` (one of `urgent`, `high`, `medium`, `low`) to filter sessions.
- `GET /sessions/triage-analytics` → returns aggregated support operations KPIs: `{total_sessions, active_count, resolved_count, escalated_count, closed_count, resolution_rate, escalation_rate, avg_turns_per_session, top_tags: [{tag, count}]}`.
- `GET /sessions/{session_id}/history` → array of `{role, content}` pairs for that session (`400` for a blank id). The Streamlit sidebar uses these to list and reload past conversations.
- `POST /sessions/{session_id}/summarize` with `{"model": "gpt-4o-mini", "save_summary": true}` → generates conversation dialogue summary, key bullet points, detected sentiment (`positive`, `neutral`, `negative`), and suggested domain tags. When `save_summary` is true, persists the summary and merges suggested tags into session metadata. Returns `{session_id, summary, key_points, sentiment, suggested_tags, saved}` (`404` when session history is empty).
- `PATCH /sessions/{session_id}` with `{"label": "...", "status": "...", "priority": "urgent|high|medium|low|null", "tags": [...], "summary": "...", "resolution_notes": "..."}` → updates session metadata. `label` (1–80 chars), `status` (`active`, `resolved`, `escalated`, `closed`), `priority` (`urgent`, `high`, `medium`, `low`, or null/clear), `tags` (string or array), `summary` (max 2000 chars), `resolution_notes` (max 2000 chars). Returns updated session info (`404` when unknown, `422` for invalid input).
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
- `sla.approaching_breach`: Dispatched when an active session's response or resolution SLA enters the warning window (`approaching_breach`). Payload includes `session_id`, `priority`, `policy_id`, `policy_name`, `target_type` (`first_response` or `resolution`), `time_remaining_minutes`, `breach_deadline`, and `escalate_on_breach`.
- `sla.breached`: Dispatched when an active session's response or resolution SLA target deadline is missed. Payload includes `session_id`, `priority`, `policy_id`, `policy_name`, `target_type`, `breached_by_minutes`, `breach_deadline`, and `escalate_on_breach`.
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

## SLA Policies, Priority Triage & Escalation Engine

The agent features a configurable Service Level Agreement (SLA) policy manager, real-time deadline calculation, session priority triage, automated escalation alerting, and compliance analytics engine for support operations.

### Endpoints

- `GET /sla/policies`: List all configured SLA policies.
  - Returns array of `SLAPolicyResponse` objects (`id`, `name`, `priority`, `category`, `first_response_time_minutes`, `resolution_time_minutes`, `warning_threshold_percentage`, `escalate_on_breach`, `use_business_hours`, `is_active`, `created_at`, `updated_at`).
- `POST /sla/policies`: Create a new SLA policy.
  - Body: `{"name": "Emergency SLA", "priority": "urgent", "category": "Maintenance", "first_response_time_minutes": 15, "resolution_time_minutes": 120, "warning_threshold_percentage": 75, "escalate_on_breach": true, "use_business_hours": false, "is_active": true}`.
  - Returns `201` with created SLA policy record. Returns `400` on validation errors.
- `GET /sla/policies/{policy_id}`: Retrieve a specific SLA policy by ID.
  - Returns `SLAPolicyResponse` (`404` if not found).
- `PATCH /sla/policies/{policy_id}`: Partially update an SLA policy's name, priority, category, response time, resolution time, warning threshold, escalation flag, business hours flag, or active status.
  - Returns updated `SLAPolicyResponse` (`404` if not found).
- `DELETE /sla/policies/{policy_id}`: Delete an SLA policy by ID.
  - Returns `{"message": "SLA policy {policy_id} deleted.", "id": <int>}` (`404` if not found).
- `GET /sessions/{session_id}/sla`: Calculate and return the real-time SLA status and countdown for an active support session.
  - Resolves matching policy based on session priority (`urgent`, `high`, `medium`, `low`) and category.
  - Honors `use_business_hours` when computing first response and resolution deadlines across operating calendar windows.
  - Calculates status for first response and resolution targets: `met`, `healthy`, `approaching_breach`, or `breached`.
  - Returns `SessionSLAStatusResponse` (`session_id`, `priority`, `policy_id`, `policy_name`, `first_response_status`, `resolution_status`, `first_response_deadline`, `resolution_deadline`, `first_response_time_remaining_minutes`, `resolution_time_remaining_minutes`, `first_response_breached`, `resolution_breached`, `overall_status`, `escalation_triggered`). Returns `404` if session is not found.
- `POST /sla/evaluate-alerts`: Run proactive background evaluation of SLA compliance across all active sessions.
  - Identifies sessions entering the warning window (`approaching_breach`) or violating targets (`breached`).
  - Dispatches `sla.approaching_breach` and `sla.breached` webhook notifications to registered subscribers.
  - Automatically transitions breached sessions to `escalated` status when policy `escalate_on_breach` is true.
  - Returns `SLAAlertEvaluationResponse` (`evaluated_sessions`, `alerts_dispatched`, `breaches_detected`, `warnings_detected`, `escalations_triggered`, `dispatched_events: [...]`).
- `GET /sla/analytics`: Aggregated SLA compliance metrics across all historical and active sessions.
  - Returns `SLAComplianceAnalyticsResponse` (`total_tracked_sessions`, `response_compliant_count`, `resolution_compliant_count`, `response_breached_count`, `resolution_breached_count`, `response_compliance_rate`, `resolution_compliance_rate`, `overall_compliance_rate`, `breach_distribution_by_priority: {"urgent": 0, "high": 0, "medium": 0, "low": 0}`, `active_at_risk_count`).

## Support Agents, Tiered Escalation Routing & Business Hours Engine

The system provides agent directory management, tiered escalation routing (`tier_1`, `tier_2`, `tier_3`), assignment audit history, team workload analytics, and business hours schedule calculation.

### Endpoints

- `GET /agents?tier=...&department=...&is_active=...`: List support agents with optional tier, department, or active status filtering.
  - Returns `SupportAgentListResponse` containing `items` and `total`.
- `POST /agents`: Register a new support agent profile.
  - Body: `{"id": "agent_alex", "name": "Alex Smith", "email": "alex@example.com", "tier": "tier_1", "department": "leasing", "is_active": true}`.
  - Returns `201` with created `SupportAgentResponse`.
- `GET /agents/{agent_id}`: Retrieve agent details. Returns `404` if not found.
- `PATCH /agents/{agent_id}`: Partially update agent name, email, tier, department, or active status.
- `DELETE /agents/{agent_id}`: Remove an agent profile. Returns `404` if not found.
- `GET /agents/workload`: Comprehensive live workload distribution and capacity analytics across active support agents.
  - Returns `AgentWorkloadResponse` (`agents: [ { agent: ..., active_sessions_count: int, resolved_sessions_count: int, total_sessions_count: int } ]`, `total_active_sessions`, `unassigned_active_sessions`, `tier_distribution`).
- `POST /sessions/{session_id}/assign`: Manually assign or transfer a session to an agent or change its escalation tier.
  - Body: `{"agent_id": "agent_sarah", "tier": "tier_1", "assigned_by": "operator", "reason": "Customer requested lease specialist"}`.
  - Emits audit log to `session_assignment_history` and dispatches `session.assigned` or `session.tier_escalated` webhooks.
- `POST /sessions/{session_id}/auto-assign`: Automatically assign session to the least-loaded active agent matching tier and department criteria.
  - Body: `{"strategy": "least_busy", "target_tier": "tier_2", "department": "maintenance", "assigned_by": "auto_router"}`.
  - Returns updated session metadata and assignee.
- `GET /sessions/{session_id}/assignment-history`: Retrieve historical audit trail of agent assignments and tier escalations for a session.
  - Returns `SessionAssignmentHistoryResponse` (`session_id`, `items: [ { id, session_id, previous_agent, new_agent, previous_tier, new_tier, assigned_by, reason, assigned_at } ]`, `total`).
- `GET /business-hours/status`: Query operating business hours status for customer care.
  - Returns `BusinessHoursStatusResponse` (`is_open: bool`, `current_time: ISO-8601`, `next_open_at: ISO-8601 | null`, `timezone: "UTC"`, `schedule: {...}`, `day_name: "Monday"`).

## Multi-Criteria CSAT Feedback, Review Queues & Performance Analytics Engine

The agent provides a 1–5 star multi-criteria Customer Satisfaction (CSAT) survey system, an operator review & follow-up workflow queue, automated low-CSAT webhook alerting (`feedback.low_csat`), and per-agent / per-tier performance scorecards.

### Endpoints

- `POST /feedback/csat`: Submit a 1–5 star multi-criteria CSAT survey for a session.
  - Body: `{"session_id": "sess-123", "score": 5, "resolution_satisfaction": 4, "agent_helpfulness": 5, "response_speed": 4, "comment": "Very helpful!"}`.
  - Automatically links the active session's `assigned_agent` and `escalation_tier` at submission time.
  - Scores `<= 2` automatically set `review_status = "followup_required"` and dispatch a `feedback.low_csat` webhook alert.
  - Returns `201` with `FeedbackReviewItemResponse`.
- `GET /feedback/queue?review_status=...&assigned_agent=...&escalation_tier=...&min_score=...&max_score=...&limit=50`: List feedback items in the operator review queue with filtering.
  - `review_status` filter options: `pending_review`, `followup_required`, `reviewed`, `resolved`.
  - Returns `FeedbackReviewQueueResponse` (`items`, `total`).
- `PATCH /feedback/{feedback_id}/review`: Update operator review status and reviewer notes for a feedback item.
  - Body: `{"review_status": "reviewed", "reviewer_notes": "Contacted tenant and resolved concern.", "reviewed_by": "supervisor_1"}`.
  - Returns updated `FeedbackReviewItemResponse` (`404` if not found).
- `GET /feedback/csat-summary`: Retrieve aggregated multi-criteria CSAT KPIs and star distribution.
  - Returns `CSATSummaryResponse` (`total_feedback`, `total_scored_csat`, `avg_csat_score`, `avg_resolution_score`, `avg_helpfulness_score`, `avg_speed_score`, `positive_rate`, `low_csat_count`, `pending_review_count`, `followup_required_count`, `reviewed_count`, `resolved_count`, `star_distribution`).
- `GET /feedback/agent-scorecards`: Retrieve per-agent and per-tier CSAT & operational performance scorecards.
  - Returns `AgentPerformanceScorecardsResponse` (`scorecards: [ { agent_id, tier, total_ratings, avg_csat_score, avg_resolution_score, avg_helpfulness_score, avg_speed_score, positive_count, negative_count, satisfaction_rate, followup_required_count } ]`, `tier_averages: {"tier_1": 4.5, ...}`, `overall_avg_csat`).

## Knowledge Base Gap Detection, FAQ Article Drafting & Self-Service Deflection

The agent provides an end-to-end knowledge loop connecting support sessions, escalations, and customer feedback directly back into the RAG vector knowledge base (`document_store`, `document_sources`, and Chroma). Unanswered queries, low-CSAT conversations, and escalated tickets are tracked as knowledge gaps, synthesized into structured Markdown articles, and published with 1 click directly into the searchable document library.

### Endpoints

- `POST /knowledge/gaps`: Record or update a knowledge gap.
  - Body: `{"query": "How do I set up autopay for monthly rent?", "category": "billing", "source_type": "manual", "session_id": "sess-123", "priority": "high", "notes": "Customer requested clear guide"}`.
  - Normalized query matching automatically deduplicates recurring inquiries and increments `frequency` (promoting to `high` priority at frequency >= 3).
  - Automatically dispatches `knowledge.gap_detected` webhook on creation or increment.
  - Returns `201` with `KnowledgeGapResponse`.
- `GET /knowledge/gaps`: List knowledge gaps with filtering.
  - Query parameters: `status` (`open`, `drafting`, `resolved`, `dismissed`), `category`, `priority`, `source_type`, `search`, `limit`, `offset`.
  - Returns `KnowledgeGapListResponse` (`items: [...]`, `total: int`).
- `GET /knowledge/gaps/{gap_id}`: Retrieve a knowledge gap by ID. Returns `404` if not found.
- `PATCH /knowledge/gaps/{gap_id}`: Partially update a knowledge gap's status, priority, category, linked article, or notes.
- `DELETE /knowledge/gaps/{gap_id}`: Delete a knowledge gap.
- `POST /knowledge/gaps/scan`: Automated scanner across resolved/escalated sessions and low-CSAT feedback to detect unanswered queries and extract knowledge gaps.
  - Returns `KnowledgeGapScanResponse` (`scanned_sessions_count`, `new_gaps_created`, `existing_gaps_incremented`, `total_gaps_identified`, `gaps: [...]`).
- `POST /knowledge/articles`: Create a new knowledge base / FAQ article draft.
  - Body: `{"title": "Online Rent Autopay Setup", "category": "billing", "content_markdown": "...", "tags": ["autopay", "billing"], "question_pattern": "how to set up autopay", "author": "agent_sarah"}`.
  - Returns `201` with `KnowledgeArticleResponse`.
- `POST /sessions/{session_id}/draft-article`: Synthesize a structured Markdown FAQ / KB article draft from a resolved customer support session's inquiry, assistant answers, summary, and resolution notes.
  - Body: `{"author": "agent_auto", "category": "billing", "link_gap_id": 12}`.
  - Automatically links associated knowledge gap and marks its status as `drafting`.
  - Returns `201` with `KnowledgeArticleResponse`.
- `GET /knowledge/articles`: List knowledge base articles with filtering.
  - Query parameters: `status` (`draft`, `published`, `archived`), `category`, `search`, `limit`, `offset`.
  - Returns `KnowledgeArticleListResponse` (`items: [...]`, `total: int`).
- `GET /knowledge/articles/{article_id}`: Retrieve a knowledge base article by ID. Returns `404` if not found.
- `PATCH /knowledge/articles/{article_id}`: Partially update a knowledge base article's title, category, content markdown, question pattern, tags, or status.
- `DELETE /knowledge/articles/{article_id}`: Delete an unpublished or archived knowledge base article.
- `POST /knowledge/articles/{article_id}/publish`: Publish an article directly into the RAG vector knowledge base (`document_store` and `document_sources`) and Chroma index.
  - Body: `{"collection": "default", "chunking_strategy": "markdown", "chunk_size": 1000, "chunk_overlap": 200}`.
  - Updates article `status = "published"` and links `published_file_id`.
  - Automatically transitions linked knowledge gap to `status = "resolved"`.
  - Dispatches `knowledge.article_published` webhook notification.
  - Returns `KnowledgeArticlePublishResponse`.
- `GET /knowledge/analytics`: Retrieve self-service coverage, knowledge gap, and deflection analytics.
  - Returns `KnowledgeBaseAnalyticsResponse` (`total_gaps`, `open_gaps`, `resolved_gaps`, `drafting_gaps`, `dismissed_gaps`, `total_articles`, `draft_articles_count`, `published_articles_count`, `archived_articles_count`, `gap_resolution_rate`, `recurring_gap_queries_count`, `estimated_deflected_queries`, `top_gap_categories`, `gaps_by_priority`).

## Tenant Profiles, Property Unit Directory & Context Grounding Engine

The agent supports resident context grounding, linking support sessions directly to tenant profiles and property units (`units`, `tenants`, `session_labels`). When a session is linked, chat queries (`/chat` and `/chat/stream`) are automatically augmented with verified lease terms, balance due, access codes, and amenities, and macro variables (`{customer_name}`, `{unit_id}`, `{monthly_rent}`, `{balance_due}`) are resolved without manual agent entry.

### Property Units Endpoints

- `POST /units`: Register a new property unit.
  - Body: `{"id": "unit_401", "property_name": "Sunset Heights", "unit_number": "401", "address": "123 Main St", "city": "Austin", "state": "TX", "zip_code": "78701", "building_name": "Tower A", "floor": 4, "monthly_rent": 1650.0, "parking_spot": "P-401", "gate_code": "#4011"}`.
  - Returns `201` with `UnitResponse`.
- `GET /units`: List property units with filtering and pagination.
  - Query parameters: `property_name`, `search`, `limit`, `offset`.
  - Returns `UnitListResponse` (`items: [...]`, `total: int`).
- `GET /units/{unit_id}`: Retrieve unit details. Returns `404` if not found.
- `PATCH /units/{unit_id}`: Partially update unit details (rent, parking, gate code, notes). Returns `UnitResponse`.
- `DELETE /units/{unit_id}`: Delete a unit record.

### Tenants Endpoints

- `POST /tenants`: Register a new tenant profile.
  - Body: `{"id": "tenant_10", "first_name": "Diana", "last_name": "Prince", "email": "diana@example.com", "phone": "+1 555-0144", "unit_id": "unit_401", "lease_start": "2026-01-01", "lease_end": "2026-12-31", "monthly_rent": 1650.0, "balance_due": 0.0, "status": "active"}`.
  - Returns `201` with `TenantResponse`.
- `GET /tenants`: List tenant profiles with filtering.
  - Query parameters: `unit_id`, `status` (`active`, `past_due`, `evicted`, `former`), `search`, `limit`, `offset`.
  - Returns `TenantListResponse` (`items: [...]`, `total: int`).
- `GET /tenants/{tenant_id}`: Retrieve tenant profile. Returns `404` if not found.
- `PATCH /tenants/{tenant_id}`: Update tenant fields (contact info, unit_id, rent, balance_due, status, notes).
- `DELETE /tenants/{tenant_id}`: Delete a tenant profile.

### Session Linking & Context Grounding Endpoints

- `POST /sessions/{session_id}/link-tenant`: Link a support session to a tenant and/or property unit.
  - Body: `{"tenant_id": "tenant_1", "unit_id": null}` (auto-resolves unit from tenant if not specified).
  - Returns `SessionTenantContextResponse`.
- `GET /sessions/{session_id}/tenant-context`: Retrieve grounded resident and property unit context for a support session.
  - Returns `SessionTenantContextResponse` (`session_id`, `tenant_id`, `unit_id`, `tenant: {...}`, `unit: {...}`).
- `GET /tenants/{tenant_id}/support-history`: Retrieve complete support session history for a resident.
  - Returns `TenantSupportHistoryResponse` (`tenant`, `total_sessions`, `sessions: [ { session_id, label, status, priority, message_count, preview, created_at, last_active, rating, feedback_score, feedback_comment } ]`).

## Maintenance Work Orders, Service Requests & Resident Dispatch

Persistent repair request engine linking support sessions, property units, and resident profiles (`work_orders`). Active open work orders are automatically injected into conversational RAG prompt context (`[ACTIVE MAINTENANCE WORK ORDERS]`), and macro variables auto-resolve (`{open_work_orders_count}`, `{latest_work_order_id}`).

### Work Order Endpoints

- `POST /work-orders`: Create a new maintenance work order.
  - Body: `{"id": "wo_201", "unit_id": "unit_101", "title": "Kitchen faucet leaking", "description": "Dripping faucet under sink", "category": "plumbing", "priority": "medium", "status": "submitted", "tenant_id": "tenant_1", "session_id": null, "entry_permission": "permission_granted", "assigned_to": "Plumber Bob", "scheduled_date": "2026-10-18", "estimated_cost": 150.0}`.
  - Categories: `plumbing`, `electrical`, `hvac`, `appliance`, `pest_control`, `structural`, `general`.
  - Priorities: `low`, `medium`, `high`, `emergency`.
  - Permissions: `permission_granted`, `call_first`, `resident_must_be_present`.
  - Returns `201` with `WorkOrderResponse`.
  - Triggers background webhook `work_order.created` (and `work_order.emergency_escalated` if priority is `emergency`).
- `GET /work-orders`: List maintenance work orders with filtering and pagination.
  - Query parameters: `unit_id`, `tenant_id`, `status` (`submitted`, `scheduled`, `in_progress`, `completed`, `cancelled`), `priority`, `category`, `search`, `limit`, `offset`.
  - Returns `WorkOrderListResponse` (`items: [...]`, `total: int`).
- `GET /work-orders/metrics`: Aggregate maintenance summary metrics and KPIs.
  - Returns `WorkOrderMetricsResponse` (`total_work_orders`, `open_work_orders`, `emergency_work_orders`, `in_progress_work_orders`, `completed_work_orders`, `by_status: {...}`, `by_priority: {...}`, `by_category: {...}`, `total_estimated_cost`, `total_actual_cost`).
- `GET /work-orders/{work_order_id}`: Retrieve details of a specific maintenance work order. Returns `404` if not found.
- `PATCH /work-orders/{work_order_id}`: Partially update a work order (status, priority, assignee, scheduled date, actual cost, resolution notes).
  - Returns `WorkOrderResponse`.
  - Triggers background webhook `work_order.status_changed` if status changed, and `work_order.emergency_escalated` if priority escalated to `emergency`.
- `DELETE /work-orders/{work_order_id}`: Delete a maintenance work order record.
- `POST /sessions/{session_id}/create-work-order`: 1-click convert an active support session into a maintenance work order.
  - Body: `{"title": "No heat in unit", "description": "Thermostat unresponsive", "category": "hvac", "priority": "emergency", "entry_permission": "permission_granted", "estimated_cost": 250.0}`.
  - Automatically resolves `unit_id` and `tenant_id` from the session's linked resident context if not explicitly provided.
  - Returns `201` with `WorkOrderResponse`.
- `GET /units/{unit_id}/work-orders`: List all maintenance work orders for a property unit.
  - Query parameter: `open_only=true` (filters out `completed` and `cancelled`).
  - Returns `WorkOrderListResponse`.
- `GET /tenants/{tenant_id}/work-orders`: List all maintenance work orders submitted by a resident.
  - Query parameter: `open_only=true`.
  - Returns `WorkOrderListResponse`.

## Resident Billing, Rent Ledgers, Invoices & Payment Operations Engine

Financial accounting ledger engine (`billing_transactions`) supporting itemized rent charges, utility assessments, late fees, security deposits, and resident payments. Tracks payments with atomic balance reconciliation, payment method tracking, and auto-generated receipts/reference numbers. RAG prompt grounding automatically injects resident ledger statements (`[RESIDENT BILLING & PAYMENT LEDGER]`) and resolves billing macro variables (`{balance_due}`, `{last_payment_amount}`, `{last_payment_date}`, `{overdue_balance}`).

### Billing & Payment Endpoints

- `POST /billing/transactions`: Create a new billing transaction (charge, fee, deposit, assessment, or manual adjustment).
  - Body: `{"tenant_id": "tenant_1", "unit_id": "unit_101", "transaction_type": "rent", "description": "November 2026 Monthly Rent", "amount": 1250.0, "status": "posted", "due_date": "2026-11-01", "notes": "Standard lease rent"}`.
  - Types: `rent`, `security_deposit`, `late_fee`, `utility`, `parking_fee`, `pet_rent`, `maintenance_charge`, `payment`, `credit_refund`.
  - Statuses: `posted`, `pending`, `paid`, `overdue`, `waived`, `cancelled`.
  - Returns `201` with `BillingTransactionResponse`.
  - Triggers background webhook `billing.charge_posted` (or `billing.late_fee_assessed` if type is `late_fee`).
- `GET /billing/transactions`: List billing transactions with filtering and pagination.
  - Query parameters: `tenant_id`, `unit_id`, `status`, `transaction_type`, `due_before`, `due_after`, `limit`, `offset`.
  - Returns `BillingTransactionListResponse` (`items: [...]`, `total: int`).
- `GET /billing/metrics`: Portfolio-wide financial metrics and billing health summary.
  - Returns `BillingSummaryMetricsResponse` (`total_transactions`, `total_charges_amount`, `total_payments_amount`, `outstanding_balance`, `overdue_balance`, `overdue_transactions_count`, `overdue_tenants_count`, `by_type: {...}`, `by_status: {...}`).
- `GET /billing/transactions/{transaction_id}`: Retrieve a specific billing transaction by ID. Returns `404` if not found.
- `PATCH /billing/transactions/{transaction_id}`: Partially update a billing transaction (status, due_date, notes, payment details).
  - Returns `BillingTransactionResponse`.
  - Triggers background webhook `billing.payment_received` if status transitioned to `paid`, or `billing.overdue_escalated` if marked `overdue`.
- `DELETE /billing/transactions/{transaction_id}`: Delete a billing transaction.
- `POST /tenants/{tenant_id}/payments`: Record a resident payment against a tenant's account with atomic balance reconciliation.
  - Body: `{"amount": 1250.0, "payment_method": "ach", "reference_number": "ACH-98214", "description": "Rent payment", "session_id": null}`.
  - Payment methods: `ach`, `credit_card`, `debit_card`, `check`, `cashier_check`, `money_order`, `online_portal`.
  - Automatically reconciles oldest pending/posted/overdue charges to `paid`, decrements tenant `balance_due`, creates a paid `payment` ledger record, and logs an audit trail.
  - Returns `200` with `TenantPaymentRecordResponse` (`transaction: {...}`, `previous_balance: float`, `new_balance: float`, `reconciled_charges_count: int`).
  - Triggers background webhook `billing.payment_received`.
- `GET /tenants/{tenant_id}/ledger`: Retrieve complete financial ledger and account statement for a resident.
  - Returns `TenantLedgerSummaryResponse` (`tenant_id`, `current_balance`, `monthly_rent`, `total_charges`, `total_payments`, `total_credits`, `overdue_balance`, `last_payment: {...}`, `recent_transactions: [...]`).
- `POST /sessions/{session_id}/record-payment`: 1-click record a resident payment directly from an active support session context.
  - Body: `{"amount": 1250.0, "payment_method": "ach", "reference_number": "ACH-98214", "description": "Rent payment"}`.
  - Auto-resolves `tenant_id` from the session's linked resident context.
  - Returns `200` with `TenantPaymentRecordResponse`.

## Lease Renewal Offers, Addenda, Digital Agreements & E-Sign Engine

Digital lease renewal and agreement execution engine (`lease_renewals`) managing renewal proposals, multi-term offers, rent adjustments, concession incentives, e-signatures with audit trails, and automatic agreement synthesis for RAG search. Active renewal offers are automatically injected into conversational RAG prompt context (`[ACTIVE LEASE RENEWAL OFFERS]`), and renewal macro variables auto-resolve (`{renewal_status}`, `{proposed_rent}`, `{renewal_term_months}`, `{renewal_concession}`, `{renewal_expires_at}`).

### Lease Renewal Endpoints

- `POST /lease-renewals`: Create a new lease renewal proposal.
  - Body: `{"tenant_id": "tenant_1", "unit_id": "unit_101", "proposed_rent": 1600.0, "current_rent": 1500.0, "term_months": 12, "start_date": "2027-01-01", "end_date": "2027-12-31", "concession_amount": 100.0, "security_deposit_change": 0.0, "concession_notes": "Early renewal credit", "notes": "Standard renewal offer", "status": "offered", "expires_at": "2026-12-15T00:00:00"}`.
  - Statuses: `draft`, `offered`, `negotiating`, `accepted`, `signed`, `declined`, `expired`.
  - Returns `201` with `LeaseRenewalResponse`.
  - Triggers background webhook `lease_renewal.created`.
- `GET /lease-renewals`: List lease renewal offers with multi-parameter filtering and pagination.
  - Query parameters: `tenant_id`, `unit_id`, `status`, `term_months`, `limit`, `offset`.
  - Returns `LeaseRenewalListResponse` (`items: [...]`, `total: int`).
- `GET /lease-renewals/metrics`: Aggregate portfolio lease renewal conversion KPIs.
  - Returns `LeaseRenewalMetricsResponse` (`total_renewals`, `signed_renewals`, `offered_renewals`, `negotiating_renewals`, `declined_renewals`, `expired_renewals`, `renewal_rate`, `avg_rent_increase_pct`, `total_concessions_amount`, `by_status: {...}`, `by_term: {...}`).
- `GET /lease-renewals/{renewal_id}`: Retrieve full details of a specific lease renewal proposal. Returns `404` if not found.
- `PATCH /lease-renewals/{renewal_id}`: Partially update a lease renewal offer (status, proposed rent, term, concessions, notes).
  - Returns `LeaseRenewalResponse`.
  - Triggers background webhook `lease_renewal.status_changed`.
- `DELETE /lease-renewals/{renewal_id}`: Delete a lease renewal offer.
- `POST /lease-renewals/{renewal_id}/sign`: Execute digital signature on lease renewal agreement.
  - Body: `{"signer_name": "Sarah Connor", "signer_email": "sarah@example.com", "signer_ip": "192.168.1.50", "notes": "E-signed via resident portal"}`.
  - Automatically records signature audit log (`signer_name`, `signed_at`, `signer_ip`, `signature_digest`), sets status to `signed`, and updates linked tenant's `monthly_rent`, `lease_start`, and `lease_end`.
  - Returns `200` with `LeaseRenewalSignResponse` (`renewal: {...}`, `audit_trail: {...}`).
  - Triggers background webhook `lease_renewal.signed`.
- `POST /lease-renewals/{renewal_id}/publish`: Synthesize legal markdown agreement and index directly into Chroma RAG collection (`leases-agreements`).
  - Synthesizes comprehensive markdown agreement containing parties, terms, rent schedule, concessions, signature blocks, and legal addenda clauses.
  - Returns `200` with `{"message": "Agreement published to RAG collection.", "file_id": int, "filename": str, "collection": "leases-agreements", "renewal_id": str}`.
- `POST /sessions/{session_id}/create-lease-renewal`: 1-click create a lease renewal offer directly from an active support session context.
  - Auto-resolves `tenant_id`, `unit_id`, and `current_rent` from linked resident context.
  - Returns `201` with `LeaseRenewalResponse`.
- `GET /tenants/{tenant_id}/lease-renewals`: Retrieve lease renewal history and active offers for a resident.
  - Query parameter: `active_only=true` (filters to `draft`, `offered`, `negotiating`).
  - Returns `LeaseRenewalListResponse`.

## Resident Move-In/Move-Out Inspections, Turnover Punchlists & Security Deposit Accounting Engine

Resident move-in/move-out and turnover management engine (`inspections`) tracking room-by-room condition checklists, itemized security deposit deductions, deficiency punchlist-to-work-order conversion, automated Markdown condition statement generation, and RAG knowledge store publication. Inspection context is automatically injected into resident chat prompt grounding (`[RESIDENT INSPECTIONS, MOVE-IN/OUT & DEPOSIT SETTLEMENT]`), and macro variables auto-resolve (`{inspection_type}`, `{inspection_status}`, `{inspection_date}`, `{total_estimated_deductions}`, `{net_deposit_refund}`, `{keys_returned}`).

### Inspection Endpoints

- `POST /inspections`: Create a new resident move-in/out or turnover inspection record.
  - Body: `{"tenant_id": "tenant_1", "unit_id": "unit_101", "inspection_type": "move_out", "scheduled_date": "2026-10-25", "inspector_name": "Property Operations Specialist", "security_deposit_base": 1500.0, "items": [{"id": "item_1", "room": "living_room", "item_name": "Walls", "condition": "good", "estimated_cost": 0.0, "actual_cost": 0.0, "has_damage": false}], "notes": "Pre-move-out walk", "status": "scheduled"}`.
  - Inspection types: `move_in`, `move_out`, `pre_move_out`, `annual`, `turnover_punchlist`.
  - Statuses: `scheduled`, `in_progress`, `completed`, `cancelled`.
  - Returns `201` with `InspectionResponse`.
  - Triggers background webhook `inspection.scheduled`.
- `GET /inspections`: List inspection records with multi-parameter filtering and pagination.
  - Query parameters: `tenant_id`, `unit_id`, `status`, `inspection_type`, `scheduled_before`, `scheduled_after`, `limit`, `offset`.
  - Returns `InspectionListResponse` (`items: [...]`, `total: int`).
- `GET /inspections/metrics`: Portfolio-wide turnover and inspection KPI metrics.
  - Returns `InspectionSummaryMetricsResponse` (`total_inspections`, `status_distribution: {...}`, `type_distribution: {...}`, `condition_distribution: {...}`, `deposit_accounting_summary: {...}`, `turnover_punchlist_summary: {...}`).
- `GET /inspections/{inspection_id}`: Retrieve complete inspection details, itemized room checklists, condition notes, and deposit deductions. Returns `404` if not found.
- `PATCH /inspections/{inspection_id}`: Partially update an inspection record (status, items checklist, condition ratings, notes, inspector name, scheduled date, keys returned).
  - Returns `InspectionResponse`.
  - Triggers background webhook `inspection.keys_returned` if `keys_returned` transitions to `true`.
- `DELETE /inspections/{inspection_id}`: Delete or cancel an inspection record.
- `POST /inspections/{inspection_id}/complete`: Finalize inspection, assess itemized deductions, calculate net deposit refund, and update status to `completed`.
  - Body: `{"security_deposit_base": 1500.0, "overall_condition": "good", "notes": "Final settlement calculated"}`.
  - Automatically tallies estimated and actual itemized damage deductions, calculates `net_deposit_refund = base - deductions`, records `completed_at` timestamp, and sets status to `completed`.
  - Returns `200` with `InspectionResponse`.
  - Triggers background webhooks `inspection.completed` and `inspection.deposit_deductions_assessed`.
- `POST /inspections/{inspection_id}/convert-to-work-order`: Convert a checklist deficiency/damage item directly into an active maintenance work order in `work_orders`.
  - Body: `{"item_id": "item_1", "priority": "medium", "category": "structural", "assigned_to": "Maintenance Lead"}`.
  - Creates linked work order with title `Turnover Repair: {room} - {item_name}` referencing inspection ID and room details.
  - Returns `200` with `InspectionItemWorkOrderResponse` (`work_order: {...}`, `inspection_id: str`, `item_id: str`).
- `POST /inspections/{inspection_id}/publish-document`: Synthesize structured Markdown inspection statement and publish to `document_store` and Chroma knowledge base.
  - Body (optional): `{"collection": "default", "chunking_strategy": "markdown", "chunk_size": 1000, "chunk_overlap": 200}`.
  - Synthesizes comprehensive condition statement with room checklists, damage notes, key tracking, and security deposit accounting ledger.
  - Returns `200` with `InspectionPublishDocumentResponse` (`status: "indexed"`, `inspection_id: str`, `file_id: int`, `collection: str`, `chunks_indexed: int`).
- `POST /sessions/{session_id}/create-inspection`: 1-click schedule an inspection directly from an active resident support session.
  - Auto-resolves `tenant_id` and `unit_id` from session's linked resident context.
  - Returns `201` with `InspectionResponse`.
- `GET /tenants/{tenant_id}/inspections`: Retrieve inspection history and turnover punchlists for a specific resident.
  - Returns `InspectionListResponse`.
- `GET /units/{unit_id}/inspections`: Retrieve unit turnover and condition inspection history.
  - Returns `InspectionListResponse`.

## Maintenance Vendor Directory, Work Order Dispatch & Vendor Performance Metrics

Self-contained vendor engine (`api/vendors.py`, tables `vendors` and `vendor_dispatches`) that dispatches maintenance work orders to vendors and tracks completion, ratings and spend. Vendor statuses: `active`, `inactive`, `blacklisted`. Dispatch statuses: `dispatched`, `completed`, `cancelled`. Sample vendors are seeded on first start.

### Vendor Endpoints

- `POST /vendors`: Register a vendor.
  - Body: `{"name": "Acme Plumbing", "trade": "plumbing", "contact_name": "Sam", "email": "sam@acme.test", "phone": "555-0100", "hourly_rate": 85.0, "status": "active", "notes": ""}` (optional `id`).
  - Returns `201` with `VendorResponse`; `422` on invalid input.
- `GET /vendors`: List vendors. Query parameters: `trade`, `status`, `search`, `limit`, `offset`. Returns `VendorListResponse`.
- `GET /vendors/metrics`: Vendor counts by trade, dispatch counts, `completion_rate`, `average_rating`, `total_spend`, plus per-vendor performance.
- `GET /vendors/{vendor_id}`: Retrieve a vendor (`404` if unknown).
- `PATCH /vendors/{vendor_id}`: Partially update a vendor (`404` if unknown, `422` on invalid input).
- `DELETE /vendors/{vendor_id}`: Delete a vendor (`404` if unknown).
- `GET /vendors/{vendor_id}/dispatches`: List a vendor's dispatches. Returns `VendorDispatchListResponse`.

### Dispatch Endpoints

- `POST /work-orders/{work_order_id}/dispatch-vendor`: Dispatch a vendor to a work order.
  - Body: `{"vendor_id": "vnd_...", "agreed_cost": 250.0, "scheduled_date": "2026-11-01"}` (`agreed_cost`, `scheduled_date` optional).
  - Rejects unknown/inactive vendors, unknown/closed work orders and duplicate active dispatches. Sets the work order `assigned_to` and moves a `submitted` work order to `scheduled`.
  - Returns `201` with `VendorDispatchResponse`; triggers webhook `vendor.dispatched`.
- `POST /vendor-dispatches/{dispatch_id}/complete`: Complete a dispatch.
  - Body: `{"final_cost": 240.0, "rating": 5, "feedback": "On time", "resolution_notes": "Fixed leak"}` (`rating` 1-5).
  - Completes the work order with `actual_cost`; double completion is rejected.
  - Returns `VendorDispatchResponse`; triggers webhook `vendor.job_completed`.
- `GET /work-orders/{work_order_id}/dispatches`: List dispatch history for a specific work order.
  - Returns `VendorDispatchListResponse`.

### Grounded Prompt Context & Macro Variables

- **RAG Context Grounding**: Active work orders assigned to contractors automatically inject vendor information into `[ACTIVE MAINTENANCE WORK ORDERS]`:
  `Vendor: {name} ({trade}) [Dispatch: {status}] | Vendor Phone: {phone}`
- **Macro Template Variables**:
  - `{vendor_name}`: Name of assigned contractor
  - `{vendor_trade}`: Trade specialty (e.g. plumbing, electrical)
  - `{vendor_phone}`: Contractor contact phone
  - `{vendor_hourly_rate}`: Standard hourly rate formatted as `$X.XX`
  - `{vendor_dispatch_status}`: Active dispatch status (`dispatched`, `completed`, or `none`)
  - `{vendor_agreed_cost}`: Agreed dispatch estimate formatted as `$X.XX`

---

## Resident Packages & Parcel Delivery Locker Management (v0.42.0)

End-to-end parcel intake, carrier tracking, secure pickup PIN verification, and turnaround analytics for resident package management.

### Endpoints

- `POST /packages`: Log an incoming package delivery into parcel locker management.
  - Body:
    ```json
    {
      "tenant_id": "tenant_1",
      "unit_id": "unit_101",
      "carrier": "Amazon",
      "tracking_number": "TBA309481029104",
      "pickup_pin": "482019",
      "location": "Locker Bay 1 - Slot 04",
      "notes": "Small parcel",
      "delivered_at": "2026-10-30T10:00:00Z"
    }
    ```
  - Validates tenant and unit existence. Generates cryptographically secure 6-digit numeric PIN if unspecified.
  - Returns `201` with `PackageResponse`; triggers webhook `package.delivered`.
- `GET /packages`: List and filter packages.
  - Query parameters: `tenant_id`, `unit_id`, `carrier`, `status` (`delivered`, `picked_up`, `returned`, `expired`), `search`, `limit`, `offset`.
  - Returns `PackageListResponse`.
- `GET /packages/metrics`: Retrieve portfolio package delivery, locker occupancy, and turnaround turnaround metrics.
  - Returns: `total_packages`, `delivered_packages` (pending pickup), `picked_up_packages`, `returned_packages`, `expired_packages`, `carrier_breakdown`, `average_pickup_hours`, `oldest_pending_hours`.
- `GET /packages/{package_id}`: Retrieve details for a specific parcel (`404` if unknown).
- `PATCH /packages/{package_id}`: Update location, notes, or status (`404` if unknown).
- `DELETE /packages/{package_id}`: Delete a parcel record (`404` if unknown).
- `POST /packages/{package_id}/pickup`: Verify resident pickup PIN and release parcel.
  - Body: `{"pickup_pin": "482019", "picked_up_at": "2026-10-30T12:00:00Z"}` (`picked_up_at` optional).
  - Validates PIN matches package record and status is `delivered`. Moves status to `picked_up` and records timestamp.
  - Returns `PackageResponse`; triggers webhook `package.picked_up`. Rejects invalid PIN (`400`) or double pickup (`400`).
- `GET /tenants/{tenant_id}/packages`: Retrieve packages for a resident.
  - Query parameter: `pending_only` (`true` filters to pending deliveries).
- `POST /sessions/{session_id}/intake-package`: Log package intake directly for the resident linked to an active support session.
  - Resolves linked resident and unit ID automatically from session context.
  - Returns `201` with `PackageResponse`; triggers webhook `package.delivered`.

### Grounded Prompt Context & Macro Variables

- **RAG Context Grounding**: Active conversational turns automatically ground resident deliveries under:
  ```text
  [RESIDENT PACKAGES & PARCEL DELIVERIES]
  - Total Deliveries on Record: 2
  - Pending Locker Pickups: 1
    - [DELIVERED] Amazon (ID: pkg_1) | Tracking: TBA12345 | Location: Locker Bay 1 - Slot 04 | Pickup PIN: 482019 | Delivered: 2026-10-28T14:30:00Z
  [END RESIDENT PACKAGES & PARCEL DELIVERIES]
  ```
- **Macro Template Variables**:
  - `{pending_packages_count}`: Number of pending deliveries ready for pickup
  - `{package_id}`: ID of primary/latest pending package
  - `{package_carrier}`: Carrier name (e.g. Amazon, UPS, FedEx)
  - `{package_tracking_number}`: Tracking number
  - `{package_status}`: Delivery status (`delivered`, `picked_up`, or `none`)
  - `{package_pickup_pin}`: Secure numeric pickup verification PIN
  - `{package_location}`: Locker bay or storage location
  - `{package_delivered_at}`: ISO delivery timestamp

## Evaluation Harness

`scripts/eval_retrieval.py` evaluates retrieval accuracy against golden test sets:
- `--golden <path>`: path to golden question dataset (default `docs/eval/golden.json`).
- `--expand`: evaluate with query expansion (LLM reformulations fused via RRF).
- `--hybrid`: evaluate with hybrid BM25 + dense vector search.
- `--rerank`: evaluate with term-overlap lexical reranking.
- `--collection <name>`: scope retrieval evaluation to a specific collection.
- `--compare`: evaluate baseline vector search vs configured enhanced strategy side-by-side.
- `--json-output <path>`: write structured evaluation metrics and per-case results to JSON.




---

## Community Amenity Reservations & Common Area Bookings (v0.43.0)

Automated community amenity catalog, conflict-free booking reservations, fee calculations, and utilization analytics.

### Endpoints

- `POST /amenities`: Create a new community amenity.
  - Body:
    ```json
    {
      "name": "Skyline Rooftop Lounge",
      "category": "rooftop",
      "description": "Panoramic terrace with fire pits.",
      "capacity": 30,
      "hourly_rate": 35.0,
      "deposit_amount": 150.0,
      "opening_hour": 10,
      "closing_hour": 22,
      "is_active": true,
      "rules": "No glassware outdoors."
    }
    ```
  - Returns `201` with `AmenityResponse`.
- `GET /amenities`: List community amenities.
  - Query parameters: `category`, `is_active`, `limit`, `offset`.
  - Returns `AmenityListResponse`.
- `GET /amenities/{amenity_id}`: Retrieve details for a specific amenity (`404` if unknown).
- `PATCH /amenities/{amenity_id}`: Update amenity settings, rates, capacity, or operating hours.
- `GET /amenity-reservations/metrics`: Retrieve portfolio amenity booking KPIs and utilization breakdown.
  - Returns: `active_amenities_count`, `total_reservations`, `confirmed_count`, `pending_count`, `cancelled_count`, `completed_count`, `total_revenue`, `total_deposits_held`, `amenity_usage_breakdown`.
- `POST /amenity-reservations`: Book a community amenity with conflict validation.
  - Body:
    ```json
    {
      "amenity_id": "amenity_bbq",
      "tenant_id": "tenant_1",
      "unit_id": "unit_101",
      "start_time": "2026-11-20T17:00:00Z",
      "end_time": "2026-11-20T20:00:00Z",
      "attendees_count": 6,
      "notes": "Birthday cookout"
    }
    ```
  - Overlapping active bookings for the same amenity are strictly rejected with `409 Conflict`.
  - Calculates fees automatically based on hours and hourly rate.
  - Returns `201` with `ReservationResponse`; triggers webhook `amenity_reservation.created`.
- `GET /amenity-reservations`: List and filter bookings (`amenity_id`, `tenant_id`, `status`, `limit`, `offset`).
- `GET /amenity-reservations/{reservation_id}`: Retrieve details for a reservation.
- `PATCH /amenity-reservations/{reservation_id}`: Update status (`confirmed`, `cancelled`, `completed`) or notes.
  - Triggers webhook `amenity_reservation.confirmed` or `amenity_reservation.cancelled`.
- `DELETE /amenity-reservations/{reservation_id}`: Delete an amenity reservation record.
- `GET /tenants/{tenant_id}/amenity-reservations`: List all reservations for a resident.
- `POST /sessions/{session_id}/create-reservation`: Book an amenity directly for the resident linked to active chat session.

### Context Grounding & Prompt Macros

- **RAG Context Grounding**: Active conversational turns automatically ground resident bookings under:
  ```text
  [COMMUNITY AMENITY RESERVATIONS]
  - Total Reservations on Record: 1
  - Active/Upcoming Bookings: 1
    - [res_001] Grand Community Clubhouse | Status: CONFIRMED | Time: 2026-11-05T18:00:00Z to 2026-11-05T21:00:00Z | Attendees: 15 | Total Fee: $75.00
  [END COMMUNITY AMENITY RESERVATIONS]
  ```
- **Macro Template Variables**:
  - `{active_reservations_count}`: Number of active/pending bookings
  - `{amenity_name}`: Name of primary booked amenity
  - `{reservation_start}`: Booking start ISO timestamp
  - `{reservation_end}`: Booking end ISO timestamp
  - `{reservation_status}`: Reservation status (`confirmed`, `pending`, `cancelled`, or `none`)
  - `{reservation_fee}`: Formatted fee string (e.g. `$75.00`)
  - `{reservation_deposit}`: Formatted deposit string (e.g. `$100.00`)
  - `{reservation_attendees}`: Number of guests/attendees


## Parking Management, Permit Passes & Vehicle Directory Engine (v0.44.0)

Dedicated infrastructure managing parking stalls, household vehicle permits, visitor passes, infractions, and occupancy KPIs.

### Parking Spots & Stalls
- `POST /parking/spots`: Create a new parking stall.
  - Body:
    ```json
    {
      "spot_number": "P-105",
      "zone": "Garage Level 1",
      "spot_type": "assigned_resident",
      "unit_id": "unit_101",
      "tenant_id": "tenant_1",
      "status": "assigned",
      "notes": "Assigned stall"
    }
    ```
  - Returns `201` with `ParkingSpotResponse`.
- `GET /parking/spots`: List parking stalls with optional filters (`zone`, `spot_type`, `status`, `unit_id`, `tenant_id`, `search`, `limit`, `offset`).
  - Returns `ParkingSpotListResponse`.
- `GET /parking/spots/{spot_id}`: Retrieve details for a specific stall (`404` if not found).
- `PATCH /parking/spots/{spot_id}`: Update stall configuration, status, or reassign/unassign tenants (`clear_unit`, `clear_tenant`).

### Resident Vehicles & Decal Permits
- `POST /parking/vehicles`: Register a resident household vehicle.
  - Body:
    ```json
    {
      "tenant_id": "tenant_1",
      "unit_id": "unit_101",
      "license_plate": "7XYZ890",
      "make": "Toyota",
      "model": "RAV4",
      "color": "Silver",
      "year": 2022,
      "permit_number": "PERM-101A",
      "notes": "Resident primary vehicle"
    }
    ```
  - Returns `201` with `VehicleResponse`.
- `GET /parking/vehicles`: List registered resident vehicles with filters (`tenant_id`, `unit_id`, `is_active`, `search`, `limit`, `offset`).
  - Returns `VehicleListResponse`.
- `GET /parking/vehicles/{vehicle_id}`: Retrieve details for a registered vehicle.
- `PATCH /parking/vehicles/{vehicle_id}`: Update vehicle attributes, permit decal, or active status.
- `DELETE /parking/vehicles/{vehicle_id}`: Deactivate/remove vehicle; triggers webhook `parking_permit.revoked`.
- `GET /tenants/{tenant_id}/vehicles`: List registered vehicles for a specific resident.

### Visitor Parking Passes
- `POST /parking/visitor-passes`: Issue a temporary visitor parking permit.
  - Body:
    ```json
    {
      "unit_id": "unit_101",
      "tenant_id": "tenant_1",
      "visitor_name": "Jane Doe",
      "vehicle_plate": "GUEST123",
      "start_time": "2026-11-02T12:00:00Z",
      "end_time": "2026-11-03T12:00:00Z",
      "notes": "Weekend guest pass"
    }
    ```
  - Automatically generates unique pass code (e.g. `VP-88219`).
  - Returns `201` with `VisitorPassResponse`; triggers webhook `parking_pass.issued`.
- `GET /parking/visitor-passes`: List and filter visitor passes (`unit_id`, `tenant_id`, `status`, `limit`, `offset`).
  - Returns `VisitorPassListResponse`.
- `GET /parking/visitor-passes/{pass_id}`: Retrieve details for a visitor pass.
- `PATCH /parking/visitor-passes/{pass_id}`: Update pass status (`active`, `expired`, `revoked`) or expiration notes.
- `POST /sessions/{session_id}/issue-visitor-pass`: Issue a visitor pass directly grounded to the resident linked to current support session.

### Parking Violations & Towing Infractions
- `POST /parking/violations`: Record an unauthorized parking infraction or towing warning.
  - Body:
    ```json
    {
      "license_plate": "BADPARK1",
      "violation_type": "unauthorized_spot",
      "spot_id": "spot_101",
      "fine_amount": 50.0,
      "notes": "Parked in reserved stall without permit"
    }
    ```
  - Returns `201` with `ParkingViolationResponse`; triggers webhook `parking_violation.logged`.
- `GET /parking/violations`: List logged infractions with filters (`spot_id`, `status`, `violation_type`, `search`, `limit`, `offset`).
  - Returns `ParkingViolationListResponse`.
- `GET /parking/violations/{violation_id}`: Retrieve details for an infraction.
- `PATCH /parking/violations/{violation_id}`: Update violation status (`issued`, `paid`, `warning`, `towed`, `dismissed`).
- `GET /parking/metrics`: Retrieve portfolio parking KPIs (`total_spots`, `occupied_spots`, `vacant_spots`, `assigned_resident_spots`, `visitor_spots`, `ev_spots`, `handicap_spots`, `occupancy_rate_pct`, `total_registered_vehicles`, `active_visitor_passes`, `total_violations`, `outstanding_fines`, `towed_vehicles_count`).

### Context Grounding & Prompt Macros
- **RAG Context Grounding**: Conversational prompt turns automatically ground resident parking stalls, vehicles, and active passes under:
  ```text
  [RESIDENT VEHICLES & PARKING PASSES]
  - Assigned Parking Spot(s): P-12
    - Spot P-12: Zone Garage Level 1 | Status: ASSIGNED
  - Registered Household Vehicles: 1
    - [7XYZ890] Silver Toyota RAV4 | Permit Decal: PERM-101A
  - Active Visitor Passes: 1
    - [VP-88219] Jane Doe (Plate: GUEST123) | Valid until: 2026-11-03T12:00:00Z
  [END RESIDENT VEHICLES & PARKING PASSES]
  ```
- **Macro Template Variables**:
  - `{assigned_parking_spot}`: Primary assigned parking space (e.g. `P-12`)
  - `{parking_spot}`: Parking spot alias for backward compatibility
  - `{parking_zone}`: Parking zone / garage level
  - `{vehicle_plate}`: Primary registered vehicle license plate
  - `{vehicle_make_model}`: Registered vehicle make and model
  - `{permit_number}`: Resident parking permit decal code
  - `{registered_vehicles_count}`: Number of active vehicles registered to household
  - `{active_visitor_pass}`: `"true"` if active pass exists, otherwise `"false"`
  - `{visitor_pass_code}`: Pass code of active visitor permit (or `""`)

## Resident Pet Registry & Animal Policies (v0.45.0)

### Pet Directory & Registration
- `POST /pets`: Register a resident pet for a tenant and unit.
  - Body:
    ```json
    {
      "tenant_id": "tenant_1",
      "unit_id": "unit_101",
      "name": "Cooper",
      "pet_type": "dog",
      "breed": "Golden Retriever",
      "weight_lbs": 62.0,
      "color": "Golden",
      "age_years": 3,
      "is_service_animal": false,
      "is_esa": false,
      "rabies_tag": "RAB-2026-9999",
      "vaccination_expires": "2027-05-15",
      "notes": "Friendly, fully vaccinated"
    }
    ```
  - Returns `201` with `PetResponse`; triggers webhook `pet.registered`.
- `GET /pets`: List registered pets with filters (`tenant_id`, `unit_id`, `pet_type`, `status`, `search`, `limit`, `offset`).
  - Returns `PetListResponse`.
- `GET /pets/{pet_id}`: Retrieve details for a specific registered pet.
- `PATCH /pets/{pet_id}`: Update profile, weight, vaccination expiry, or status.
- `DELETE /pets/{pet_id}`: Remove pet registration (`{"status": "deleted", "pet_id": "..."}`).
- `GET /tenants/{tenant_id}/pets`: List all registered pets for a specific verified tenant.
- `POST /sessions/{session_id}/register-pet`: 1-click registration grounded in active support session tenant profile.
- `GET /pets/metrics`: Retrieve community pet demographics and revenue KPIs (`total_active_pets`, `total_dogs`, `total_cats`, `total_service_animals`, `pending_approvals`, `expiring_vaccinations`, `active_incidents`, `outstanding_fines`, `monthly_pet_revenue`).

### Community Animal Policies
- `POST /pet-policies`: Create property or building animal policy guidelines.
  - Body:
    ```json
    {
      "property_name": "Grand Community Apartments",
      "building": "Tower B",
      "max_weight_lbs": 65.0,
      "max_pets_per_unit": 2,
      "monthly_pet_rent": 35.0,
      "one_time_deposit": 300.0,
      "restricted_breeds": ["Pit Bull", "Rottweiler"],
      "rules_and_restrictions": "Leash required in common areas."
    }
    ```
  - Returns `201` with `PetPolicyResponse`; triggers webhook `pet_policy.updated`.
- `GET /pet-policies`: List active animal policies with optional `building` filter.
- `GET /pet-policies/{policy_id}`: Retrieve details for a specific policy.
- `PATCH /pet-policies/{policy_id}`: Update policy terms, rent, deposit, or breed restrictions. Triggers webhook `pet_policy.updated`.

### Animal Incidents & Complaints
- `POST /pet-incidents`: Log an animal rule violation or noise complaint.
  - Body:
    ```json
    {
      "incident_type": "noise_barking",
      "incident_date": "2026-11-04",
      "pet_id": "pet_101",
      "tenant_id": "tenant_1",
      "unit_id": "unit_101",
      "fine_amount": 50.0,
      "status": "warning_issued",
      "notes": "Excessive barking reported after 10 PM."
    }
    ```
  - Returns `201` with `PetIncidentResponse`; triggers webhook `pet_incident.logged`.
- `GET /pet-incidents`: List logged animal incidents with filters (`pet_id`, `tenant_id`, `incident_type`, `status`, `limit`, `offset`).
- `GET /pet-incidents/{incident_id}`: Retrieve details for an incident.
- `PATCH /pet-incidents/{incident_id}`: Update incident status (`reported`, `warning_issued`, `fine_assessed`, `resolved`) or fine amount.

### Context Grounding & Prompt Macros
- **RAG Context Grounding**: Conversational prompt turns automatically ground resident pets and animal policies under:
  ```text
  [RESIDENT PETS & ANIMAL POLICIES]
  - Registered Household Pets: 1
    - Barnaby (Dog - Golden Retriever Mix, 38.0 lbs) | Status: ACTIVE | Rabies Tag: RAB-2026-8812 | Vacc Expires: 2027-02-15
  - Community Animal Policy: Rent: $35.00/mo | Deposit: $300.00 | Max Weight: 65.0 lbs
  ```
- **Macro Template Variables**:
  - `{registered_pets_count}`: Number of registered pets for household (e.g. `1`)
  - `{pet_names}`: Comma-separated names of household pets (e.g. `Barnaby`)
  - `{pet_name}`: Primary pet name
  - `{pet_breed}`: Primary pet breed or species
  - `{primary_pet_breed}`: Alias for primary pet breed
  - `{pet_vaccination_status}`: Vaccination status (e.g. `expires 2027-02-15` or `current`)
  - `{pet_rent_monthly}`: Monthly pet rent amount (e.g. `$35.00`)
  - `{pet_deposit_amount}`: One-time pet deposit (e.g. `$300.00`)
  - `{service_animal_verified}`: `"true"` if service animal or ESA verified, otherwise `"false"`


## Smart Access Control, Key Fobs, Digital Mobile Keys, Intercom & Guest Passes Engine (v0.46.0)

Integrated residential security and access control infrastructure managing physical key fobs, NFC cards, digital smartphone mobile keys, time-bound visitor PIN passes, callbox intercom directory listings, lost fob deactivation with automated replacement billing, and conversational RAG grounding.

### Key Fobs & Digital Credentials
- `POST /access/credentials`: Register and issue a physical key fob, NFC access card, mobile key, or keypad PIN.
  - Body:
    ```json
    {
      "tenant_id": "tenant_1",
      "unit_id": "unit_101",
      "credential_type": "key_fob",
      "credential_number": "FOB-9042",
      "access_level": "all_access",
      "assigned_to_name": "Elena Rostova",
      "replacement_fee": 50.0
    }
    ```
  - Returns `201` with `AccessCredentialResponse`; triggers webhook `access.credential_issued`.
- `GET /access/credentials`: List registered credentials with filters (`tenant_id`, `unit_id`, `credential_type`, `status`, `search`, `limit`, `offset`).
  - Returns `AccessCredentialListResponse`.
- `GET /access/credentials/{credential_id}`: Retrieve details for a credential (`404` if not found).
- `PATCH /access/credentials/{credential_id}`: Update credential status (`active`, `suspended`, `lost`, `deactivated`), access level, or deactivation reason.
  - Triggers webhook `access.credential_deactivated` when deactivated or lost.
- `DELETE /access/credentials/{credential_id}`: Permanently delete credential record (`{"status": "deleted", "credential_id": "..."}`).
- `GET /tenants/{tenant_id}/credentials`: List all access credentials assigned to a verified resident.

### Visitor Guest Passes & Temporary PINs
- `POST /access/guest-passes`: Generate a time-bound visitor or vendor access PIN.
  - Body:
    ```json
    {
      "tenant_id": "tenant_1",
      "unit_id": "unit_101",
      "guest_name": "Metro Dog Walking Co.",
      "pass_type": "dog_walker",
      "valid_hours": 72,
      "max_uses": 10,
      "access_zones": ["building_exterior", "elevator_lobby", "dog_run"],
      "notes": "Daily dog walking pass"
    }
    ```
  - Automatically generates 6-digit numeric access PIN (e.g. `618902`) if omitted.
  - Returns `201` with `GuestPassResponse`; triggers webhook `access.guest_pass_generated`.
- `GET /access/guest-passes`: List guest passes with filters (`tenant_id`, `unit_id`, `pass_type`, `status`, `limit`, `offset`).
  - Returns `GuestPassListResponse`.
- `GET /access/guest-passes/{pass_id}`: Retrieve details for a visitor pass.
- `PATCH /access/guest-passes/{pass_id}`: Update pass status (`active`, `expired`, `revoked`, `max_uses_reached`) or record access usage.
- `DELETE /access/guest-passes/{pass_id}`: Remove guest pass record.
- `GET /tenants/{tenant_id}/guest-passes`: List visitor passes generated by a verified resident.
- `POST /sessions/{session_id}/generate-guest-pass`: 1-click issuance grounded in active session resident profile.

### Intercom & Building Callbox Directory
- `POST /access/intercom`: Add a callbox intercom directory listing.
  - Body:
    ```json
    {
      "tenant_id": "tenant_1",
      "unit_id": "unit_101",
      "display_name": "Rostova, E.",
      "directory_code": "PH1",
      "forwarding_phone": "+1-555-0199",
      "buzzer_enabled": true
    }
    ```
  - Returns `201` with `IntercomDirectoryResponse`.
- `GET /access/intercom`: List callbox entries with optional search and pagination.
  - Returns `IntercomDirectoryListResponse`.
- `GET /access/intercom/{entry_id}`: Retrieve callbox listing.
- `PATCH /access/intercom/{entry_id}`: Update forwarding phone number or toggle buzzer permission.
- `DELETE /access/intercom/{entry_id}`: Remove entry from directory.

### Lost Fob Reporting & Instant Deactivation
- `POST /sessions/{session_id}/report-lost-fob`: 1-click lost credential deactivation grounded in resident support session.
  - Body:
    ```json
    {
      "credential_id": "cred_elena_01",
      "deactivation_reason": "Lost at neighborhood park",
      "charge_replacement_fee": true
    }
    ```
  - Sets credential status to `lost`, timestamps deactivation, dispatches webhook `access.fob_reported_lost`, and automatically posts a `$50.00` fee to resident billing ledger if requested.

### Portfolio Access Metrics
- `GET /access/metrics`: Returns portfolio-wide access metrics summary:
  - `total_credentials`: Total registered credentials across properties
  - `active_credentials`: Active fobs, mobile keys, and cards
  - `lost_credentials`: Fobs reported lost or stolen
  - `replacement_fees_assessed`: Total replacement fees charged ($)
  - `active_guest_passes`: Currently valid visitor PIN passes
  - `total_guest_entries`: Cumulative guest pass access events
  - `intercom_directory_count`: Active building callbox listings
  - `mobile_keys_count`: Digital mobile keys issued

### Context Grounding & Prompt Macros
- **RAG Context Grounding**: Conversational assistant prompts automatically ground resident credentials under:
  ```text
  [RESIDENTIAL ACCESS CREDENTIALS & GUEST PASSES]
  - Registered Access Credentials: 2 (Active: 2)
    - Key Fob #FOB-9042 | Level: ALL_ACCESS | Status: ACTIVE | Replacement Fee: $50.00
    - Mobile Key #MOB-3319 | Level: ALL_ACCESS | Status: ACTIVE | Replacement Fee: $0.00
  - Active Guest Passes: 1
    - Dog Walker (Metro Dog Walking Co.) | Code: 618902 | Expires: 2026-11-09T07:22:00Z | Uses: 0/10 | Status: ACTIVE
  - Callbox Intercom: Code #PH1 | Name: Rostova, E. | Buzzer: ACTIVE
  [END ACCESS CREDENTIALS]
  ```
- **Macro Template Variables**:
  - `{active_fob_count}`: Number of active physical fobs assigned (e.g. `1`)
  - `{primary_fob_number}`: Serial number of primary key fob (e.g. `FOB-9042`)
  - `{guest_pass_code}`: 6-digit visitor access PIN (e.g. `618902`)
  - `{guest_pass_expires}`: Guest pass expiration timestamp
  - `{access_zones}`: Authorized zones list (e.g. `building_exterior, elevator_lobby, dog_run`)
  - `{intercom_code}`: Resident callbox directory dial code (e.g. `PH1`)
  - `{fob_replacement_fee}`: Standard lost fob replacement fee (e.g. `$50.00`)


## Residential Incidents, Community Violations & Notice-to-Cure Engine (v0.47.0)

Endpoints for logging community incident reports (security patrols, noise complaints, common area damage), issuing tiered violation notices to cure (courtesy warning, 1st/2nd notice, fine assessment, notice to vacate), and managing resident appeal adjudication.

### Incident Management Endpoints
- `POST /incidents`: Log a new community incident report.
  - Body: `CommunityIncidentCreateRequest` (`incident_type`, `severity`, `unit_id`, `tenant_id`, `location`, `description`, `reported_by`, `patrol_officer`, `evidence_urls`).
- `GET /incidents`: List filtered community incidents (`status`, `severity`, `incident_type`, `unit_id`, `tenant_id`, `limit`, `offset`).
- `GET /incidents/{incident_id}`: Retrieve detailed record of an incident report.
- `PATCH /incidents/{incident_id}`: Update incident status, patrol notes, or resolution outcome.
- `DELETE /incidents/{incident_id}`: Remove an incident report.
- `GET /tenants/{tenant_id}/incidents`: List incident reports associated with a specific resident.

### Violation Notices Endpoints
- `POST /violations`: Issue a formal notice to cure or violation notice.
  - Body: `ViolationNoticeCreateRequest` (`tenant_id`, `unit_id`, `violation_type`, `notice_type`, `incident_id`, `remedy_instructions`, `cure_days`, `fine_amount`, `charge_to_ledger`, `issued_by`).
  - Automatically calculates cure deadline (`issued_at + cure_days`).
  - If `charge_to_ledger=true` and `fine_amount > 0`, immediately posts fine transaction to resident's billing ledger (`reason="violation_fine"`).
- `GET /violations`: List filtered violation notices (`tenant_id`, `unit_id`, `status`, `notice_type`, `violation_type`, `limit`, `offset`).
- `GET /violations/{notice_id}`: Retrieve violation notice details.
- `PATCH /violations/{notice_id}`: Update violation notice status, cure deadline, or notes.
- `DELETE /violations/{notice_id}`: Delete a violation notice record.
- `GET /tenants/{tenant_id}/violations`: List all violation notices issued to a resident.

### Violation Appeals & Adjudication Endpoints
- `POST /appeals`: Submit an appeal against an issued violation notice.
  - Body: `ViolationAppealCreateRequest` (`notice_id`, `tenant_id`, `reason`, `supporting_evidence_urls`).
- `GET /appeals`: List resident violation appeals (`status`, `tenant_id`, `notice_id`, `limit`, `offset`).
- `GET /appeals/{appeal_id}`: Retrieve appeal details and hearing outcome.
- `PATCH /appeals/{appeal_id}`: Adjudicate appeal outcome (`under_review`, `waived`, `upheld`, `reduced`).
  - Allows adjusting fine amount; updates parent violation notice status.
- `DELETE /appeals/{appeal_id}`: Delete an appeal record.
- `GET /tenants/{tenant_id}/appeals`: List appeals filed by a specific resident.

### Session 1-Click Operations
- `POST /sessions/{session_id}/issue-violation-notice`: Issue a formal notice to cure directly from the active resident chat session.
  - Body: `SessionIssueViolationNoticeRequest` (`violation_type`, `notice_type`, `remedy_instructions`, `cure_days`, `fine_amount`, `charge_to_ledger`).
- `POST /sessions/{session_id}/submit-violation-appeal`: Submit an appeal directly from the resident chat session.
  - Body: `SessionSubmitViolationAppealRequest` (`notice_id`, `reason`, `supporting_evidence_urls`).

### Community Compliance Metrics
- `GET /incidents/metrics`: Returns portfolio-wide incident & compliance metrics summary:
  - `total_incidents`: Total incident reports logged
  - `active_incidents`: Open/investigating/patrolling incidents
  - `total_violations`: Total violation notices issued
  - `open_violations`: Currently active, uncured violations
  - `cured_violations`: Successfully remediated violations
  - `total_fines_assessed`: Cumulative violation fines assessed ($)
  - `total_appeals`: Total appeals filed
  - `pending_appeals`: Appeals awaiting adjudication

### Context Grounding & Prompt Macros
- **RAG Context Grounding**: Conversational assistant prompts automatically ground community violations under:
  ```text
  [RESIDENTIAL INCIDENTS & COMMUNITY VIOLATIONS]
  - Active Community Violations: 1 (Total Fines: $25.00)
    - Courtesy Warning: Noise Complaint | Cure Deadline: 2026-11-09T00:00:00 | Status: ISSUED | Fine: $25.00 | Remedy: Cease amplified audio after 10 PM.
  - Pending Appeals: 1
    - Appeal #APL-2026-042 (Notice: VN-2026-089) | Status: SUBMITTED | Reason: Resident claims audio was from adjacent apartment.
  - Resident Incident History: 1 reports on file
    - #INC-2026-101 | Type: noise_complaint | Severity: low | Status: resolved
  [END INCIDENTS & VIOLATIONS]
  ```
- **Macro Template Variables**:
  - `{active_violations_count}`: Number of active notices issued to resident (e.g. `1`)
  - `{primary_violation_type}`: Most recent active violation category (e.g. `noise_complaint`)
  - `{notice_type}`: Notice tier (e.g. `courtesy_warning`, `first_notice_to_cure`)
  - `{cure_deadline}`: Expiration of cure window
  - `{fine_amount}` / `{violation_fine_amount}`: Assessed fine in currency format (e.g. `$25.00`)
  - `{violation_remedy}`: Actions required to resolve infraction
  - `{appeal_status}`: Status of active appeal (e.g. `submitted`)
  - `{active_incidents_count}`: Count of active community incidents involving resident


---

## 21. Community Announcements, Emergency Broadcast Alerts & Resident Concierge Requests API

Comprehensive residential broadcast and concierge services lifecycle engine connecting management notices, safety advisories, and resident concierge requests.

### Core Endpoints

#### Announcements & Emergency Broadcasts
- `POST /announcements`: Publish a new announcement or broadcast alert (`title`, `content`, `category`, `priority`, `target_scope`, `target_building`, `target_floor`, `target_unit_id`, `require_acknowledgment`, `action_instructions`, `author_id`, `starts_at`, `expires_at`). Dispatches `announcement.published` or `emergency_alert.broadcast` webhook.
- `GET /announcements`: List announcements with optional filtering by `category`, `priority`, `target_scope`, `target_building`, and `status`.
- `GET /announcements/{id}`: Retrieve detailed announcement record by ID.
- `PATCH /announcements/{id}`: Update announcement properties (e.g. status transition to `archived`).
- `DELETE /announcements/{id}`: Permanently delete an announcement.
- `GET /tenants/{tenant_id}/announcements`: Retrieve all active announcements and emergency advisories targeting the resident's portfolio, building, floor, or specific unit.
- `GET /announcements/metrics`: Aggregated broadcast analytics (total announcements, active notices, active emergency alerts, total acknowledgments, total concierge requests, pending concierge requests).

#### Safety Acknowledgments
- `POST /announcements/{id}/acknowledge`: Record resident safety acknowledgment for an advisory (`tenant_id`, `unit_id`, `acknowledgment_method`, `notes`). Dispatches `announcement.acknowledged` webhook.
- `GET /announcements/{id}/acknowledgments`: List all resident acknowledgments recorded for a specific announcement.
- `POST /sessions/{id}/acknowledge-alert`: 1-click safety acknowledgment from an active resident support session (`announcement_id`, `notes`).

#### Resident Concierge Requests
- `POST /concierge`: Create a resident concierge request ticket (`tenant_id`, `unit_id`, `request_type`, `priority`, `description`, `instructions`, `scheduled_time`, `metadata`). Dispatches `concierge.requested` webhook.
- `GET /concierge`: List concierge requests with optional filtering by `status`, `request_type`, and `priority`.
- `GET /concierge/{id}`: Retrieve detailed concierge request record by ID.
- `PATCH /concierge/{id}`: Update concierge request status (`pending`, `in_progress`, `completed`, `cancelled`) or staff assignment. Dispatches `concierge.fulfilled` on completion.
- `DELETE /concierge/{id}`: Cancel/delete concierge request.
- `GET /tenants/{tenant_id}/concierge`: List concierge requests submitted by a specific resident.
- `POST /sessions/{id}/request-concierge`: 1-click concierge request creation from an active resident support session (`request_type`, `priority`, `description`, `instructions`, `scheduled_time`).

### Conversational RAG Grounding & Macro Templates
- **RAG Context Grounding**: Conversational assistant prompts automatically ground active advisories and open concierge tasks under:
  ```text
  [COMMUNITY ANNOUNCEMENTS & ACTIVE BUILDING ALERTS]
  - Active Community Announcements & Advisories: 2 active notices
    - [EMERGENCY] Severe Freeze Advisory: Protect Exposed Pipes (Target: portfolio_wide | Req Ack: True)
      Summary: Sub-freezing temperatures expected tonight through Thursday morning.
      Instructions: Keep faucets on a slow drip and cabinet doors open.
  - Active Resident Concierge Requests: 1 open requests
    - [STANDARD] dry_cleaning: Dry cleaning pickup: Eco Cleaners garment bag in lobby (Status: pending)
  [END ANNOUNCEMENTS & ALERTS]
  ```
- **Macro Template Variables**:
  - `{active_announcements_count}`: Number of active notices affecting resident (e.g. `2`)
  - `{active_emergency_alerts_count}`: Count of active urgent/emergency advisories (e.g. `1`)
  - `{latest_alert_headline}`: Headline of the most critical active alert
  - `{latest_alert_priority}`: Priority tier of most critical active alert (`EMERGENCY`, `URGENT`)
  - `{alert_acknowledgment_status}`: Whether resident acknowledged the alert (`ACKNOWLEDGED` or `PENDING_ACKNOWLEDGMENT`)
  - `{concierge_requests_count}`: Number of active concierge requests submitted by resident

---

## Resident Move-In / Move-Out Logistics & Freight Elevator Engine (v0.49.0)

### Overview
The Move-In / Move-Out Logistics Engine automates resident arrival, departure, and internal transfers with dedicated freight elevator booking collision detection, moving company Certificate of Insurance (COI) verification, loading dock access scheduling, and customizable onboarding/offboarding checklists.

### Core Endpoints

#### Move Logistics Events
- `POST /move-logistics`: Schedule a new resident move event (`tenant_id`, `unit_id`, `move_type`, `scheduled_date`, `time_slot`, `moving_company`, `coi_status`, `dock_required`, `notes`). Dispatches `move_logistics.scheduled` webhook.
- `GET /move-logistics`: List move logistics records with optional filtering by `tenant_id`, `unit_id`, `move_type`, `status`, `from_date`, and `to_date`.
- `GET /move-logistics/{id}`: Retrieve detailed move logistics event record with complete checklist status.
- `PATCH /move-logistics/{id}`: Update move properties (`status`, `scheduled_date`, `coi_status`, `moving_company`, `coi_policy_number`, `coi_expiry_date`, `keys_issued`, `fobs_issued`, `notes`). Dispatches `move_logistics.completed` or `move_logistics.cancelled` on status changes.
- `POST /move-logistics/{id}/checklist`: Toggle or update a specific move checklist item (`item_id`, `completed`, `notes`). Auto-recalculates overall checklist progress percentage.
- `GET /move-logistics/metrics`: Aggregated operational metrics (total moves, scheduled moves, completed moves, in-progress moves, active elevator bookings, pending COIs, verified COIs, average checklist progress percentage).

#### Freight Elevator Reservations
- `POST /elevator-bookings`: Reserve a freight elevator time window (`tenant_id`, `unit_id`, `building_name`, `elevator_id`, `booking_date`, `time_slot`, `move_event_id`, `deposit_collected`, `notes`). Validates slot availability to prevent double-booking. Dispatches `move_logistics.elevator_booked` webhook.
- `GET /elevator-bookings`: List elevator reservations with optional filtering by `building_name`, `booking_date`, `elevator_id`, and `status`.
- `GET /elevator-bookings/{id}`: Retrieve specific elevator booking record.
- `POST /elevator-bookings/{id}/cancel`: Cancel an elevator reservation with optional reason. Dispatches `move_logistics.elevator_cancelled` webhook.

#### Session Resident Actions (1-Click)
- `POST /sessions/{id}/schedule-move`: 1-click move event creation directly within an active tenant support session (`move_type`, `scheduled_date`, `time_slot`, `moving_company`, `dock_required`, `notes`).
- `POST /sessions/{id}/reserve-elevator`: 1-click freight elevator reservation directly within an active tenant support session (`booking_date`, `time_slot`, `building_name`, `elevator_id`, `deposit_collected`, `notes`).

### Conversational RAG Grounding & Macro Templates
- **RAG Context Grounding**: Grounded resident context injects active move logistics under:
  ```text
  [MOVE-IN / MOVE-OUT LOGISTICS & ELEVATOR RESERVATIONS]
  - Active Move-In / Move-Out Events: 1 active events
    - [MOVE_IN] Scheduled on 2026-11-20 (Status: scheduled | Checklist: 50.0% complete)
      Mover: Metropolis Relocations | COI: verified | Loading Dock: True
  - Upcoming Freight Elevator Reservations: 1 reservations
    - Reservation on 2026-11-20 (08:00-12:00) | Elevator: freight_elv_1 (Building: Horizon Tower | Status: confirmed)
  [END MOVE LOGISTICS]
  ```
- **Macro Template Variables**:
  - `{move_logistics_type}`: Active move type (`MOVE-IN`, `MOVE-OUT`, `INTERNAL TRANSFER`, `NONE`)
  - `{move_date}`: Scheduled move date (e.g. `2026-11-20` or `N/A`)
  - `{elevator_slot}`: Reserved elevator time slot (e.g. `08:00-12:00` or `NONE`)
  - `{loading_dock_status}`: Loading dock access status (`RESERVED` or `NOT_REQUESTED`)
  - `{move_checklist_progress}`: Percentage of completed checklist items (`50.0%`)
  - `{move_status}`: Current move status (`SCHEDULED`, `IN PROGRESS`, `COMPLETED`, `NONE`)

---

## Resident Utility Submetering, Energy & Water Consumption & Billing Splits Engine (v0.50.0)

### Overview
The Resident Utility Submetering & RUBS Engine automates property submeter telemetry, continuous usage tracking, automatic leak/spike anomaly detection, ratio utility billing split calculations, and direct ledger integration for electricity (`kWh`), water (`gallons`), gas (`therms`), sewer, and trash services.

### Core Endpoints

#### Submeters & Readings
- `POST /utilities/meters`: Provision a new property unit submeter (`unit_id`, `meter_type`, `serial_number`, `unit_of_measure`, `rate_per_unit`, `installation_date`, `notes`). Dispatches `utility.meter_created` webhook.
- `GET /utilities/meters`: List registered submeters with optional filtering by `unit_id`, `meter_type`, and `status`.
- `GET /utilities/meters/{id}`: Retrieve detailed submeter configuration and last recorded reading.
- `PATCH /utilities/meters/{id}`: Update submeter metadata, operational status, or tariff rate (`rate_per_unit`, `status`, `notes`).
- `POST /utilities/readings`: Record a utility meter reading (`meter_id`, `reading_value`, `reading_date`, `reading_source`, `notes`). Automatically evaluates consumption against rolling baseline and flags spikes >50% as anomalies. Dispatches `utility.reading_recorded` and `utility.anomaly_detected` webhooks.
- `GET /utilities/readings`: List meter reading logs with optional filtering by `meter_id`, `unit_id`, `meter_type`, and `anomalies_only`.
- `GET /utilities/readings/{id}`: Retrieve specific meter reading event details.

#### Statements & RUBS Billing
- `POST /utilities/invoices`: Generate a utility statement (`unit_id`, `tenant_id`, `billing_period_start`, `billing_period_end`, `electric_amount`, `water_amount`, `gas_amount`, `trash_amount`, `total_amount`, `notes`). Dispatches `utility.invoice_created` webhook.
- `GET /utilities/invoices`: List utility statements with optional filtering by `tenant_id`, `unit_id`, and `status`.
- `GET /utilities/invoices/{id}`: Retrieve detailed utility invoice breakdown and payment status.
- `PATCH /utilities/invoices/{id}`: Update utility statement status or dispute notes.
- `POST /utilities/invoices/{id}/post-to-ledger`: Post approved utility statement directly to tenant billing ledger transactions. Dispatches `utility.invoice_posted` webhook.

#### Summaries & Metrics
- `GET /utilities/metrics`: Retrieve portfolio-wide submetering KPIs (total submeters, total consumption, invoiced amounts, collection rates, active anomalies).
- `GET /units/{id}/utilities/summary`: Aggregated submeter telemetry, active anomalies, and current billing statement for a unit.
- `GET /tenants/{id}/utilities/summary`: Resident-linked submeter telemetry, recent readings, and statement history.

#### Support Session 1-Click Actions
- `POST /sessions/{id}/record-meter-reading`: 1-click meter reading submission directly within resident support chat (`meter_id`, `meter_type`, `reading_value`, `reading_date`, `notes`).
- `POST /sessions/{id}/report-utility-leak`: 1-click emergency utility leak reporting directly from support session. Auto-generates an urgent maintenance work order dispatched to property management.

### Conversational RAG Grounding & Macro Templates
- **RAG Context Grounding**: Verified resident context automatically includes:
  ```text
  [RESIDENT UTILITY METERS, USAGE & SUBMETERING]
  - Active Utility Meters: 1
    - Electricity (SN: EL-101-301) [ACTIVE] - Last Reading: 310.0 kWh
  - Recent Consumption: Electricity: 310.0 kWh
  - Current Utility Statement: #INV-202611-001 [DRAFT] $95.50 (2026-10-01 to 2026-10-31)
  [END RESIDENT UTILITY METERS, USAGE & SUBMETERING]
  ```
- **Macro Template Variables**:
  - `{primary_meter_status}`: Status of primary meter (`active`, `inactive`, `none`)
  - `{latest_electric_kwh}`: Latest electricity consumption reading (e.g. `310.0 kWh`)
  - `{latest_water_gallons}`: Latest water consumption reading (e.g. `1200.0 gal`)
  - `{latest_utility_total}`: Total amount on current utility invoice (e.g. `$95.50`)
  - `{utility_anomaly_alert}`: Active spike/leak alert or `none`
  - `{utility_invoice_status}`: Current invoice status (`draft`, `posted`, `paid`, `none`)
