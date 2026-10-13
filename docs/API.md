# API Reference (v0.32.0)

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

## Evaluation Harness

`scripts/eval_retrieval.py` evaluates retrieval accuracy against golden test sets:
- `--golden <path>`: path to golden question dataset (default `docs/eval/golden.json`).
- `--expand`: evaluate with query expansion (LLM reformulations fused via RRF).
- `--hybrid`: evaluate with hybrid BM25 + dense vector search.
- `--rerank`: evaluate with term-overlap lexical reranking.
- `--collection <name>`: scope retrieval evaluation to a specific collection.
- `--compare`: evaluate baseline vector search vs configured enhanced strategy side-by-side.
- `--json-output <path>`: write structured evaluation metrics and per-case results to JSON.
