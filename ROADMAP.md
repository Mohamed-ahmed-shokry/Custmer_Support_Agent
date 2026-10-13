# Customer Support RAG Agent - Roadmap

## Current State (v0.34.0, 2026-10-13)
- FastAPI backend: chat, streaming chat (SSE), upload/list/delete, sessions
  + history, metrics with per-route latency averages and approximate token
  usage, live/ready probes; retrieval filters (file_ids, source_filename,
  use_hybrid)
- Knowledge Base Gap Detection, FAQ Article Drafting & Self-Service Deflection Engine (`/knowledge/gaps*`, `/knowledge/articles*`, `/sessions/{id}/draft-article`, `/knowledge/analytics`) with recurring query deduplication and frequency tracking, automated session/CSAT gap scanner, structured Markdown article synthesis, 1-click publishing to RAG vector knowledge base with gap resolution, and `knowledge.gap_detected` & `knowledge.article_published` webhook notifications
- Streamlit Knowledge Gaps & Article Studio sidebar expander (coverage KPIs, gap scanner, gap triage queue with dismissal, article drafting & RAG publisher) and 1-click session FAQ article drafting button
- Multi-Criteria CSAT Feedback, Review Queues & Agent Performance Scorecards Engine (`POST /feedback/csat`, `GET /feedback/queue`, `PATCH /feedback/{id}/review`, `GET /feedback/csat-summary`, `GET /feedback/agent-scorecards`) with 1-5 star multi-criteria ratings, low-CSAT (`<= 2`) auto-triage and `feedback.low_csat` webhook alerting, operator review workflow, and per-agent / per-tier scorecards
- Streamlit 5-Star CSAT Survey Widget in chat interface & CSAT Queue / Agent Scorecards dashboard in sidebar
- Customer support agent assignment, tiered escalation routing (`tier_1`, `tier_2`, `tier_3`), assignment audit history, and team workload analytics (`/agents`, `/agents/workload`, `/sessions/{id}/assign`, `/sessions/{id}/auto-assign`, `/sessions/{id}/assignment-history`)
- Operating business hours calendar calculation engine (`/business-hours/status`) with business-minute SLA deadline advancement
- Streamlit Support Agents & Workload management panel, queue filtering (Unassigned, Escalated), and manual / auto-routing controls
- Customer support SLA policies & priority triage engine (`/sla/policies`, `/sessions/{id}/sla`, `/sla/evaluate-alerts`, `/sla/analytics`) with automated breach detection, approaching deadlines, and real-time escalation webhook alerting
- Priority triage badges, active session SLA countdown card, and SLA policy manager & compliance analytics panel in Streamlit sidebar
- Automated AI macro suggestions & query intent classification engine (`POST /macros/suggest`, `GET /sessions/{id}/macro-suggestions`) with domain entity extraction and multi-factor ranking
- Streamlit Smart Suggestions card & Query Match Tester widget in sidebar
- Support canned responses & action macros engine (`POST /macros`, `GET /macros`, `GET /macros/categories`, `GET /macros/{id}`, `PATCH /macros/{id}`, `DELETE /macros/{id}`, `POST /macros/{id}/render`, `POST /sessions/{id}/apply-macro`)
- Streamlit Quick Responses & Macros panel in sidebar with pre-seeded property management templates, variable auto-fill, and 1-click execution
- Webhook dispatch & escalation alerting engine with HMAC signatures and audit logging
- Support conversation summarization & sentiment classification engine
- Support triage analytics & operations dashboard
- Streamlit frontend with streaming toggle, chat interface, document
  management, past-sessions switcher, and backend metrics panel
- SQLite for session history, document metadata, feedback, and webhooks
- Chroma vector store with OpenAI embeddings; configurable chunking
  (recursive/markdown/semantic) and file types: pdf, docx, html, md, txt, csv;
  indexing retries with exponential backoff; resilient loader fallbacks
- Resilience: X-Request-ID middleware, chunk-param validation, upload cap
- Security (opt-in): API_KEY auth across backend and Streamlit client, per-IP sliding-window rate limiting
- Data protection: PII redaction in file logs
- Observability: LOG_LEVEL / LOG_FORMAT=json, in-memory metrics, probes
- Containerization: multi-stage Dockerfile, compose stack (local/staging/prod), k8s manifests
- Releases: tag-triggered workflow (verify + GitHub release)
- Docs: API reference, architecture, contributing, ADR-001, ADR-002, runbook, eval set
- Sessions support previews, deletion, and quota visibility in API + UI
- Opt-in query expansion with RRF fusion across API, chain, and UI
- Eval `--compare` mode plus unit-tested harness; session labels with
  rename/delete across API and UI; dark-mode theme
- Session markdown export across API and UI; lexical rerank composing with
  all retrievers; production compose overlay
- Retrieval inspection (`POST /search`), collection deletion (API + UI),
  deployment guide
- Upload dedup via content hash, bounded history window, shared preview helper
- Library stats endpoint, collection rename (API + UI), staging overlay
- Bulk upload endpoint with per-file results, presenters module, Retry-After
- Human feedback loop: ratings store, endpoint, metrics, UI widget
- Session retention pruning, hardened security helpers, ADR-002
- Client reliability: SSE parsing fixed on the wire format, error/source
  events surfaced correctly in the UI
- Full client security: X-API-Key forwarding across all Streamlit client endpoints
- Document inspection: `GET /docs/{file_id}` and Chroma chunk inspector in UI
- Bulk document deletion: `POST /delete-docs` and batch deletion mode in UI
- Session discovery: `GET /sessions/search` endpoint and keyword search filter in UI
- Multi-strategy retrieval eval harness: hybrid, rerank, collection filters, and JSON export
- Dynamic runtime config discovery: `GET /config` endpoint and UI model/upload limit discovery
- Bulk session deletion: `POST /delete-sessions` with cascade deletion and UI batch delete mode
- Multi-format session export: Markdown, JSON, CSV export presenters, API endpoint, and UI download selector
- Feedback quality review: feedback comments schema & migration, `GET /feedback` with filters/pagination, `GET /sessions/{session_id}/feedback`, and UI feedback review panel with session deep-linking
- **v0.22.0 additions**:
  - Session lifecycle management: status (active/resolved/escalated/closed) and tags with API + UI
  - Quality Analytics card: satisfaction rate (%), positive/negative counts, comment rate
  - Collection Insights widget: document count, chunk count, file formats, upload timestamps
  - Retrieval confidence scoring: score badges in chunk inspector and search results
- **v0.23.0 additions**:
  - Cross-encoder semantic reranking: sentence-transformers integration with `cross-encoder/ms-marco-MiniLM-L-6-v2` model
  - Cross-encoder rerank takes precedence over lexical rerank in `/chat`, `/chat/stream`, `/search`
  - Configurable via `USE_CROSS_ENCODER_RERANK` and `CROSS_ENCODER_MODEL` settings
  - Streamlit UI toggle for cross-encoder rerank in Retrieval Filters
  - Unit tests for CrossEncoderReranker with mock model
- **v0.24.0 additions**:
  - Playwright e2e suite (`tests/e2e`, opt-in `-m e2e`): chat flow (incl. LLM round-trip), document upload/management, session panel, UI smoke; page objects in `pages.py`
  - Dedicated CI `e2e` job booting the API + Streamlit against a throwaway DB and running the suite headless; `make test-e2e`
  - e2e self-skip guards: LLM round-trip tests skip when the model is unreachable, upload tests skip when embeddings are; session tests skip on an empty store
  - Pydantic >= 2.12 compatibility: RAG chain rebuilt in pure LCEL (`api/langchain_utils.py`) so fresh installs no longer crash in `langchain.chains`
  - Fixed a real upload bug the e2e suite surfaced: the Streamlit client forced `Content-Type: application/json` on multipart uploads, so every upload 422'd (`_upload_headers`)
- **v0.25.0 additions**:
  - Offline sentence-aware semantic chunking strategy: paragraph-honoring, sentence-boundary-preserving text splitter respecting chunk size and overlap without requiring LLM or embedding credits
  - Persistent source text and chunking options: `document_sources` table and SQLite migration, saving extracted document text and options at upload, and cleaning up on document or collection deletion
  - Re-chunk endpoint: `POST /docs/{file_id}/rechunk` accepting chunking options, validating chunk bounds, re-splitting preserved source text, deterministically replacing Chroma chunks, and returning refreshed document details
  - Document inspector chunking visualization and Re-chunk form: displays persistent chunking options (strategy, size, overlap) and allows in-place re-chunking directly from the Streamlit sidebar
  - Document detail response: `GET /docs/{file_id}` enriched with persistent chunking metadata
- **v0.26.0 additions**:
  - Batch collection re-chunking: `POST /collections/{collection}/rechunk` iterating through collection documents with stored sources, re-splitting, replacing chunks, and reporting summary metrics
  - Collection chunk distribution analytics: `GET /collections/{collection}/analytics` computing chunk counts, length distributions (mean, min, max, median), histograms, and strategy breakdowns
  - Client & Streamlit UI integration: `rechunk_collection` and `get_collection_analytics` helpers, interactive batch re-chunk expander form, and chunk analytics card in the sidebar
- **v0.27.0 additions**:
  - Conversation summarization engine & sentiment classification: automated dialogue summarization (`POST /sessions/{id}/summarize`) with key bullet points, sentiment classification, and suggested domain tags running offline with LLM fallback
  - Support triage analytics & operations dashboard: `GET /sessions/triage-analytics` and Streamlit card computing status counts, resolution rate (%), escalation rate (%), average turns, and top tags
  - Session resolution lifecycle management: `summary` and `resolution_notes` SQLite columns and migration, API route updating, and Streamlit session resolution panel
  - Enriched multi-format export: Markdown, JSON, and CSV exports embed session status, tags, summary, and resolution notes alongside conversation transcripts
- **v0.28.0 additions**:
  - Webhook dispatch & escalation alerting engine: HMAC-SHA256 signature verification (`X-Webhook-Signature`, `X-Webhook-Timestamp`, `X-Webhook-Event`), structured event envelopes, delivery audit logs, and test pinging
  - Database schema & CRUD: `webhooks` and `webhook_delivery_logs` tables with full registration, querying, and delivery logging
  - Real-time event triggers: automatic webhook dispatch on session escalation (`session.escalated`), resolution (`session.resolved`), and negative feedback (`feedback.negative`)
  - Streamlit Webhooks & Alerts management panel: register endpoints, custom event filtering, secret config, connectivity test pings, and delivery audit log viewer
- **v0.29.0 additions**:
  - Support canned responses & action macro templates engine (`api/macros.py`, `api/db_utils.py`, `api/pydantic_models.py`, `api/main.py`): pre-approved templates with category organization, shortcut triggers (`/rent-pay`, `/emerg-maint`, `/lease-renew`, `/move-out`), dynamic variable substitution (`{customer_name}`, `{session_id}`, `{unit_id}`, `{agent_name}`, `{date}`, `{support_contact}`), and automated session actions (status transitions to `resolved` or `escalated` with webhook triggers, tag assignment, conversation injection)
  - Dedicated FastAPI endpoints: `POST /macros`, `GET /macros`, `GET /macros/categories`, `GET /macros/{id}`, `PATCH /macros/{id}`, `DELETE /macros/{id}`, `POST /macros/{id}/render`, `POST /sessions/{id}/apply-macro`
  - Client integration & Streamlit UI: `app/api_utils.py` helpers and Quick Responses & Macros expander panel in `app/sidebar.py` with category filter, template selector, dynamic variable inputs, preview, 1-click application to active session, and custom template creation form
- **v0.30.0 additions**:
  - Automated AI macro suggestions & query intent classification engine (`api/macro_suggestions.py`): domain intent taxonomy detection (`maintenance_emergency`, `maintenance_routine`, `rent_payment`, `lease_renewal`, `move_out`, `general_inquiry`), entity extraction (`unit_id`, `customer_name`), and multi-factor ranking matching queries to canned responses
  - Dedicated FastAPI endpoints: `POST /macros/suggest` and `GET /sessions/{session_id}/macro-suggestions`
  - Client & Streamlit UI integration: `app/api_utils.py` helpers, proactive Smart Suggestions card with confidence scores, match reasons, and 1-click apply, plus interactive Query Match Tester widget
- Full test suite passing; total coverage floor >= 80% enforced in CI; ruff + mypy clean

## v0.7.0 plan — Conversation management ✅ COMPLETED

Finish the sessions story and make quotas visible (no new deps).

- [x] Session previews (first question) in `GET /sessions`
- [x] `DELETE /sessions/{id}` endpoint + UI delete button
- [x] `GET /quota` visibility endpoint (budget/used/remaining for caller IP)
- [x] UI: preview labels in picker, delete + quota display

## v0.8.0 plan — Retrieval quality via query expansion ✅ COMPLETED

Opt-in multi-query fan-out with reciprocal-rank fusion, no new deps
(`langchain_core` + `langchain_openai` only — 3.14-safe).

- [x] `api/expansion.py`: LLM reformulations + RRF merge + expanded retriever
- [x] `expand_query` flag on chat (per-request) and `USE_QUERY_EXPANSION` default
- [x] Streamlit "expand query" toggle
- [x] Eval guidance for measuring expansion against the golden set

## v0.9.0 plan — Eval comparison + session labels ✅ COMPLETED

Make expansion measurable and conversations nameable (no new deps).

- [x] Eval `--compare` mode: baseline vs expansion recall per golden case
- [x] Session labels: `session_labels` table, `PATCH /sessions/{id}`, UI rename
- [x] Dark-mode Streamlit theme

## v0.10.0 plan — Export, rerank & prod parity ✅ COMPLETED

Portability plus dependency-free relevance tuning (no new deps).

- [x] Session export: `GET /sessions/{id}/export` (markdown) + UI download
- [x] Lexical rerank retriever (term-overlap signal, wraps any retriever)
- [x] `docker-compose.prod.yml` override + deployment docs

## v0.11.0 plan — Inspection & lifecycle ✅ COMPLETED

See and manage what's inside retrieval (no new deps).

- [x] `POST /search`: inspect ranked chunks without spending chat tokens
- [x] `DELETE /collections/{name}`: remove a whole collection (API + UI)
- [x] Deployment guide (`docs/DEPLOYMENT.md`)

## v0.12.0 plan — Efficiency & robustness ✅ COMPLETED

Cut waste and bound growth (no new deps).

- [x] Upload dedup via SHA-256 (`409` on exact duplicates)
- [x] History window cap (`MAX_HISTORY_TURNS`, bounds prompt growth)
- [x] Shared preview helper (remove duplicated truncation)
- [x] Deployment environments matrix (local / staging / production)

## v0.13.0 plan — Operations & consistency ✅ COMPLETED

Run the library with confidence (no new deps).

- [x] Library stats endpoint (`GET /stats`) + sidebar totals
- [x] Collection rename (`PATCH /collections/{name}`, API + UI)
- [x] Staging compose overlay + environment docs
- [x] Quality: upload staging helper, shared quota pre-check

## v0.14.0 plan — Bulk ops & code health ✅ COMPLETED

Onboard corpora faster with cleaner internals (no new deps).

- [x] Bulk upload endpoint (`POST /upload-docs`) + multi-file UI
- [x] Extract `api/presenters.py` (preview/sources/hits/markdown) with unit tests
- [x] `Retry-After` header on rate-limit responses

## v0.15.0 plan — Human feedback loop ✅ COMPLETED

Collect answer ratings to ground future eval (no new deps).

- [x] Feedback store (`POST /feedback`, thumbs up/down + metrics)
- [x] Streamlit feedback widget under assistant answers
- [x] Quality: consistent route naming (`*_route` suffix)

## v0.16.0 plan — Retention & maintenance ✅ COMPLETED

Keep a growing library healthy (no new deps).

- [x] Feedback totals in `GET /stats`
- [x] Session retention prune (`DELETE /sessions?before=...`)
- [x] Quality: shared collection/session param normalization
- [x] Security hardening: constant-time keys, bounded limiter state,
  feedback orphans removed, lightweight readiness probe
- [x] ADR-002 (per-process limits) + packaging version sync

## v0.17.0 plan — Client reliability & test coverage ✅ COMPLETED

The API is ~90% covered but the entire Streamlit client (`app/`) has no
unit tests and contains a true SSE wiring bug (no new deps).

- [x] Fix SSE events on the client: parse `event: sources` / `event: error`
      frames correctly instead of concatenating JSON into the answer
- [x] Unit-test `app/api_utils.py` (~100%: every endpoint helper: success,
      error, network-exception, non-JSON payload paths)
- [x] Smoke/wiring tests for `app/chat_interface.py`, `app/sidebar.py`,
      and the `streamlit_app` entry against a fake Streamlit
- [x] Quality: coverage artifacts gitignored; pytest config consolidated
      in pyproject with an 80% coverage floor (was split across `pytest.ini`)
- [x] `app/` coverage from 0% → 86%; total suite coverage 88.6%

## v0.18.0 plan — Production Hardening & Operational Readiness ✅ COMPLETED

- [x] Compose environment overlays: local development, staging, and production configurations
- [x] Session retention pruning and lightweight readiness probes
- [x] Security helper consolidation and packaging version synchronization

## v0.19.0 plan — End-to-End Client Security & Core Pipeline Test Hardening ✅ COMPLETED

- [x] Client Security: Propagate `X-API-Key` header across all 17 Streamlit client calls in `app/api_utils.py`
- [x] Python 3.14 Compatibility: Lazy chain import resolution in `api/langchain_utils.py` per ADR-001
- [x] Resilient Chroma Loaders: HTML and Markdown document loader fallbacks (`BSHTMLLoader`, `TextLoader`) in `api/chroma_utils.py`
- [x] Test Coverage Hardening:
  - Unit tests for `api/langchain_utils.py` (prompts, RAG chain creation, lazy imports: 100%)
  - Unit tests for `api/chroma_utils.py` (chunking options, loader fallbacks, delete exception handling, retriever options: 88.63%)
  - Unit tests for `app/sidebar.py` (sessions, collection management, bulk uploads, ops metrics: 99.49%)
  - Unit tests for `app/streamlit_app.py` (entry point execution and session state initialization: 100%)
- [x] Quality Gates: 287 tests passing, 95.59% total coverage, ruff & mypy clean

## v0.20.0 plan — Document Inspection, Batch Operations, Session Discovery & Multi-Strategy Eval ✅ COMPLETED

Deliver operational visibility, batch maintenance, conversational history search, and extended retrieval evaluation.

- [x] Document Inspection: `GET /docs/{file_id}` endpoint + Chroma chunk retrieval (`get_doc_chunks_from_chroma`) exposing chunk count, chunk text, previews, and metadata
- [x] Bulk Document Deletion: `POST /delete-docs` endpoint accepting `file_ids` with per-file status reports (`deleted`, `not_found`, `error`)
- [x] Session Discovery: `GET /sessions/search?q=...` endpoint + SQLite search across queries and responses (`search_sessions`)
- [x] Client Integration: `app/api_utils.py` methods for document inspection, bulk delete, and session search with `X-API-Key` forwarding
- [x] Streamlit UI: Document inspector widget, batch document delete mode, and session keyword filter in `app/sidebar.py`
- [x] Multi-Strategy Retrieval Eval: Extend `scripts/eval_retrieval.py` with `--hybrid`, `--rerank`, `--collection`, and `--json-output` flags
- [x] Test Coverage & Quality Gates: Unit tests for all new endpoints, utilities, and UI widgets; 0 ruff errors, 0 mypy errors, 309 tests passing, 95.87% test coverage

## v0.21.0 plan — Feedback Quality Review, Bulk Session Management, Multi-Format Conversation Export & Dynamic Config Discovery ✅ COMPLETED

Deliver a closed-loop feedback review system, bulk session operations, flexible conversation exports (Markdown/JSON/CSV), and dynamic runtime configuration discovery.

### Scope & Objectives
- **Dynamic Config Discovery**: Enable clients to inspect non-sensitive runtime parameters dynamically (`GET /config`) without hardcoded assumptions.
- **Bulk Session Deletion**: Enable batch session deletion (`POST /delete-sessions`) with SQLite cascade deletion across logs, labels, and feedback, returning per-session status reports.
- **Multi-Format Conversation Export**: Extend `GET /sessions/{session_id}/export?format=markdown|json|csv` with structured JSON and CSV presenters alongside Markdown.
- **Feedback Comments & Quality Review**: Upgrade feedback table with `comment` column, support comments on submission, add `GET /feedback` with filters/pagination, and `GET /sessions/{session_id}/feedback`.
- **Streamlit UI Integration**:
  - Dynamic runtime configuration loading for upload limits and model defaults.
  - Bulk session deletion mode in sidebar.
  - Multi-format session export selector (Markdown / JSON / CSV).
  - Feedback review panel with rating filtering, comments display, and session deep-linking.
- **Quality Gates**: Zero ruff/mypy errors, >=95% test coverage, comprehensive unit tests.

### Explicit Exclusions (Deferred to v0.22.0+)
- Cross-encoder reranker models requiring new heavy dependencies.
- Browser-based automated UI testing via Playwright.
- User authentication and role-based multi-tenant access control.

### Granular Task Breakdown
- [x] Task 1: Dynamic Config Discovery endpoint `GET /config`, client `get_config()`, and unit tests
- [x] Task 2: Bulk Session Deletion SQLite function `delete_sessions` with cascade deletion, unit tests
- [x] Task 3: Bulk Session Deletion endpoint `POST /delete-sessions`, models, client helper, and unit tests
- [x] Task 4: Multi-format session export presenters (`render_session_json`, `render_session_csv`) and unit tests
- [x] Task 5: Multi-format export endpoint `GET /sessions/{session_id}/export?format=...`, client helper, and unit tests
- [x] Task 6: Feedback schema migration (`comment` column), `insert_feedback` update, `list_feedback`, and `get_session_feedback` queries with unit tests
- [x] Task 7: Feedback API routes (`POST /feedback` with comment, `GET /feedback`, `GET /sessions/{session_id}/feedback`), models, client methods, and unit tests
- [x] Task 8: Streamlit UI dynamic config discovery & model/upload limit integration
- [x] Task 9: Streamlit UI bulk session deletion mode in sidebar
- [x] Task 10: Streamlit UI multi-format session export selector
- [x] Task 11: Streamlit UI feedback review panel with session deep-linking
- [x] Task 12: Streamlit UI test suite updates and widget coverage
- [x] Task 13: Documentation updates (`docs/API.md`, `README.md`) and version bump to 0.21.0

## v0.22.0 plan — Session Lifecycle Management, Quality Analytics, Collection Insights, Retrieval Confidence Scoring & Cross-Encoder Reranking ✅ COMPLETED

Deliver ticket/session lifecycle states, quantitative quality/CSAT analytics, collection-level operational insights, retrieval confidence score visibility with thresholding, and semantic cross-encoder reranking.

### Scope & Objectives
- **Session Lifecycle & Categorization**: Support conversation lifecycle states (`active`, `resolved`, `escalated`, `closed`) and custom tags in SQLite (`session_labels` table migration), API routes (`PATCH /sessions/{session_id}` accepting status and tags, `GET /sessions` with `status` and `tag` query filters), and Streamlit UI controls.
- **Operational Quality & CSAT Analytics**: Aggregate feedback metrics into structured analytics (`GET /feedback/analytics`), returning satisfaction rate (`%`), positive/negative distribution, comment count, and ratings over time, surfaced in an interactive analytics card in the Streamlit UI.
- **Collection Metadata & Insights**: Provide detailed statistics per collection (`GET /collections/details`), including document count, chunk count, file format distribution, total size, and last updated timestamps, surfaced in the Streamlit collection picker widget.
- **Retrieval Confidence Scoring & Thresholding**: Enhance `POST /search` and presenters to expose relevance confidence scores (0.0 to 1.0) and accept an optional `score_threshold` filter to weed out low-confidence context; display similarity scores in the chunk inspector and search results.
- **Cross-Encoder Semantic Reranking**: Integrate sentence-transformers cross-encoder models (e.g., `cross-encoder/ms-marco-MiniLM-L-6-v2`) for semantic reranking of retrieved chunks; configurable via `USE_CROSS_ENCODER_RERANK` and `CROSS_ENCODER_MODEL` settings; takes precedence over lexical rerank; available in `/chat`, `/chat/stream`, and `/search` endpoints with Streamlit UI toggle.
- **Streamlit UI Integration**:
  - Session status picker (Active / Resolved / Escalated / Closed) and tags manager in sidebar.
  - Session status filter in past conversations list.
  - Quality Analytics card in sidebar with satisfaction rate (%) and rating counts.
  - Collection stats summary under active collection picker.
  - Relevance score badges in document chunk inspector and search results.
  - Cross-encoder rerank toggle in Retrieval Filters section.
- **Quality Gates**: Zero ruff/mypy errors, >=95% test coverage, comprehensive unit tests.

### Explicit Exclusions (Deferred to v0.24.0+)
- Multi-tenant user authentication and RBAC permissions.

### Granular Task Breakdown
- [x] Task 1: Session metadata schema migration (`status`, `tags` columns in `session_labels`) and DB functions (`update_session_metadata`, `get_all_sessions` filters) with unit tests
- [x] Task 2: Session metadata API routes & Pydantic models (`PATCH /sessions/{session_id}` status/tags, `GET /sessions?status=&tag=`, `SessionInfo`), client helpers, and unit tests
- [x] Task 3: Feedback quality & CSAT analytics DB queries (`get_feedback_analytics`) and unit tests
- [x] Task 4: Feedback analytics API endpoint `GET /feedback/analytics`, models, client helper `get_feedback_analytics()`, and unit tests
- [x] Task 5: Collection details & storage statistics DB query (`get_collections_details`) and unit tests
- [x] Task 6: Collection details API endpoint `GET /collections/details`, models, client helper `get_collections_details()`, and unit tests
- [x] Task 7: Retrieval confidence scoring and `score_threshold` in `POST /search`, presenter score support, Pydantic models, and unit tests
- [x] Task 8: Streamlit UI session lifecycle integration (status dropdown, tagging, status filtering in past sessions) and unit tests
- [x] Task 9: Streamlit UI collection insights summary widget and unit tests
- [x] Task 10: Streamlit UI feedback analytics cards (satisfaction rate, rating distribution) and unit tests
- [x] Task 11: Streamlit UI retrieval confidence score badges in chunk inspector with unit tests
- [x] Task 12: Documentation updates (`docs/API.md`, `README.md`), version bump to 0.22.0, and `ROADMAP.md` updates

## v0.24.0 plan — End-to-end UI testing (Playwright) & pydantic 2.12 fix ✅ COMPLETED

Deliver a runnable end-to-end browser suite covering the main user journeys,
belt it with a CI job, and fix the fresh-install breakage that running chat
for the first time exposed (pydantic >= 2.12 vs langchain <1).

### Scope & Objectives
- **Playwright e2e suite** (`tests/e2e`, opt-in via `-m e2e`; excluded from the
  default `pytest` run through `addopts`): page objects (`pages.py`), async
  fixtures (`conftest.py`), and 21 tests across:
  - Chat flow: UI controls (streaming, query expansion, rerank, retrieval
    filters) plus an LLM round-trip that preflights the live model and skips
    when it is unreachable (e.g. an OpenAI key without credits).
  - Document upload & management: single/multi/bulk upload, upload into a new
    collection (switching the active collection before asserting), listing,
    retrieval filtering, active-collection read.
  - Sessions panel: list/rename/delete, skipping when the store is empty.
  - UI smoke: frontend renders, backend health marker shown in the sidebar.
- **Environment resilience**: two known blockers made raw execution impossible
  on a credit-less machine and would be required for meaningful CI; both are
  handled with preflight skips rather than flaky failures.
- **pydantic >= 2.12 / langchain <1 fix**: the classic `langchain.chains`
  builders crash while evaluating pydantic annotations on fresh installs
  (`TypeError: 'function' object is not subscriptable`); the RAG chain is
  rebuilt from `langchain_core` runnables only (LCEL), keeping the streaming
  answer pipeline and matching `langchain.chains` absence in tests.
- **Upload bug found & fixed**: the Streamlit client pinned
  `Content-Type: application/json` on multipart upload requests, so the API
  could not parse the body and returned 422; uploads now use
  `_upload_headers()` (auth only) and let `requests` set the boundary.
- **CI**: a dedicated `e2e` job installs a headless Chromium, boots the API +
  Streamlit in the background against a throwaway DB, waits on the health
  endpoints, and runs the suite; `make test-e2e` mirrors it locally.
- **Quality Gates**: unit suite + e2e green; ruff + mypy clean; docs updated.

### Explicit Exclusions (Deferred to a later phase)
- Full authenticated multi-tenant UI coverage (no identity model yet).
- Screenshot/visual-regression testing and headed-mode test runs.
- Cross-browser matrix (Chromium only for now).

### Granular Task Breakdown
- [x] Task 1: e2e scaffolding — pytest-asyncio + `e2e` marker, opt-in addopts, Playwright page objects and fixtures
- [x] Task 2: Session panel page object completion (load/rename/delete/options)
- [x] Task 3: e2e tests: chat flow, sessions, UI smoke (plus upload/management files)
- [x] Task 4: Run e2e against a live API + UI and fix the blockers it surfaced:
      Streamlit websocket means `networkidle` never fires; async Playwright
      fixtures must share the session event loop; health text / selectors
      aligned with the real DOM
- [x] Task 5: Chat round-trip fix — RAG chain rebuilt in pure LCEL; `/chat` and
      `/chat/stream` accept str or dict answers; unit tests rewritten for LCEL
- [x] Task 6: Embargo preflights — chat skips when the model is unreachable,
      uploads skip when embeddings are, sessions skip on an empty store
- [x] Task 7: Upload bug fix — `_upload_headers()` without forced JSON
      content-type; e2e `helpers.py` with probe/skip, file utilities, wait-for-doc
- [x] Task 8: CI `e2e` job + `make test-e2e`; docs (`README`, `CONTRIBUTING`,
      `ROADMAP`) updated; version already billed as v0.24.0

## Next Candidates (v0.24.0+)

- Staging/production environment targets (dependent on real credentials)
- Multi-tenant user authentication and RBAC permissions

## v0.25.0 plan — Semantic chunking & re-chunking with visualization ✅ COMPLETED

Deliver the remaining chunking story: a dependency-free sentence-aware
"semantic" chunking strategy, persistent source text + chunking options so a
document can be re-chunked without re-uploading, a `POST /docs/{file_id}/rechunk`
endpoint, and a Re-chunk control plus chunking-settings display in the
document inspector. Validates the Phase 2.2 "semantic" chunking checkbox for
real (the shipped system only had recursive/markdown despite the completed
mark).

### Scope & Objectives
- **Semantic chunking strategy (offline)**: `ChunkingStrategy.SEMANTIC` backed
  by a `SentenceAwareTextSplitter` — paragraph-honoring, sentence-boundary
  preserving windows that respect `chunk_size`/`chunk_overlap`. No LLM or
  embedding calls at split time, so it works with zero credits.
- **Persistent source text + options**: new `document_sources` table
  (`file_id` PK→`document_store`, `source_text`, `strategy`, `chunk_size`,
  `chunk_overlap`, `updated_at`) filled at upload; chunk metadata also records
  the options that produced each chunk.
- **Re-chunk endpoint**: `POST /docs/{file_id}/rechunk` accepting
  `chunking_strategy`/`chunk_size`/`chunk_overlap` (same validation as upload),
  re-splitting the stored source text, replacing the Chroma chunks, and
  returning the refreshed `DocumentDetailResponse`.
- **UI visibility**: the document inspector shows how every document was chunked
  and offers a Re-chunk form (strategy/size/overlap) that calls the endpoint
  and refreshes chunk previews via the existing details call.
- **Deletion hygiene**: removing a document or collection also removes its
  `document_sources` row.
- **Quality Gates**: offline unit coverage for splitter, persistence/migration,
  endpoint, and UI wiring; default suite + ruff + mypy green; docs
  (`README.md`, `docs/API.md`) updated.

### Explicit Exclusions (Deferred)
- Embedding/LLM-driven semantic chunking (needs funded API credits).
- Browser-based rechunk e2e (uploads already skip without embeddings here; the
  rechunk flow inherits the same skip guard if wired later).
- Storing original file bytes (we persist extracted text, not the source file).
- Batch/background re-chunking across a collection.

### Granular Task Breakdown
- [x] Task 1: `ROADMAP.md` v0.25.0 plan + next-candidates prune
- [x] Task 2: `SEMANTIC` strategy + `SentenceAwareTextSplitter` (paragraph/sentence-aware, size+overlap respected, order-preserving) and unit tests
- [x] Task 3: `document_sources` table (create + migration), save/load/delete helpers and unit tests
- [x] Task 4: ingest wiring — store extracted source text + chunking options at upload; chunk metadata carries options; delete endpoints remove sources; tests
- [x] Task 5: `POST /docs/{file_id}/rechunk` (validation, split, replace chunks, update `document_sources`, return details) + model + tests + `docs/API.md`
- [x] Task 6: client `rechunk_document` helper + inspector settings display + Re-chunk form in sidebar + unit tests
- [x] Task 7: docs (`README.md`, `docs/API.md`, `ROADMAP.md` current state) + final validation (default suite, ruff, mypy) + push

## v0.26.0 plan — Batch Collection Re-Chunking & Chunk Quality Analytics ✅ COMPLETED

Deliver collection-wide chunk maintenance and operational chunk quality visibility:
batch re-chunk all documents in a collection with uniform strategy and windowing
parameters, compute granular chunk distribution analytics (character lengths,
histograms, strategy breakdowns), and integrate batch controls into the Streamlit UI.

### Scope & Objectives
- **Batch Collection Re-chunking**: `POST /collections/{collection}/rechunk` endpoint
  accepting `chunking_strategy`, `chunk_size`, and `chunk_overlap`. Iterates through all
  documents in the collection with stored source text, re-splits, updates Chroma chunks,
  and updates `document_sources`. Documents lacking source text are reported as skipped.
  Returns summary counts (`total_documents`, `rechunked_documents`, `skipped_documents`,
  `failed_documents`, `total_chunks_created`) and per-document statuses.
- **Collection Chunk Analytics**: `GET /collections/{collection}/analytics` endpoint
  computing chunk statistics across Chroma chunks in that collection:
  total chunks, document count, length metrics (avg, min, max, median), strategy distribution,
  and length histograms (`<200`, `200-500`, `500-1000`, `1000-2000`, `>2000`).
- **Client Integration**: `app/api_utils.py` helpers `rechunk_collection()` and
  `get_collection_analytics()` with header forwarding and error handling.
- **Streamlit UI Integration**:
  - Enhanced Collection Insights widget showing chunk distribution metrics and strategy pills.
  - Interactive "Batch Re-chunk Collection" expander form with strategy and size controls.
- **Quality Gates**: Maintain test coverage >= 80%, zero ruff/mypy errors.

### Explicit Exclusions (Deferred to v0.27.0+)
- Asynchronous Celery/Redis background task queues (batch operations remain synchronous for now).
- Embedding-based chunk clustering and semantic topic labeling.

### Granular Task Breakdown
- [x] Task 1: `ROADMAP.md` v0.26.0 plan specification
- [x] Task 2: Database helper `get_document_sources_by_collection` in `api/db_utils.py` with unit tests
- [x] Task 3: Pydantic models for batch re-chunking and collection chunk analytics in `api/pydantic_models.py` with unit tests
- [x] Task 4: Chroma operations `get_collection_chunk_analytics` and `rechunk_collection_in_chroma` in `api/chroma_utils.py` with unit tests
- [x] Task 5: API routes `POST /collections/{collection}/rechunk` and `GET /collections/{collection}/analytics` in `api/main.py` with unit tests
- [x] Task 6: Client helpers `rechunk_collection` and `get_collection_analytics` in `app/api_utils.py` with unit tests
- [x] Task 7: Streamlit UI batch re-chunk controls and chunk distribution analytics in `app/sidebar.py` with unit tests
- [x] Task 8: Documentation updates (`docs/API.md`, `README.md`, `pyproject.toml`) and final verification gate

## v0.27.0 plan — Support Conversation Summarization, Resolution Management & Triage Analytics ✅ COMPLETED

Deliver conversation intelligence, ticket resolution documentation, and operational triage KPIs for support workflows:
automated conversation summarization with key points, detected sentiment, and suggested tags; agent resolution notes
and summary persistence in session metadata; multi-format session export with resolution details; and an aggregated
support triage analytics API and Streamlit operations dashboard.

### Scope & Objectives
- **Conversation Summarization Engine**: `api/summarization.py` providing extractive dialogue summarization
  (inquiry extraction, resolution/response synthesis, key bullet points, sentiment classification into
  positive/neutral/negative, and domain-aware tag suggestions) running 100% offline without external API costs,
  with transparent fallback when LLM credits are not available.
- **Session Metadata & Persistence Enhancement**:
  - SQLite schema migration: add `summary` and `resolution_notes` columns to `session_labels`.
  - Database queries: update session metadata with notes/summary, fetch full session details, and compute
    aggregated support triage analytics (`get_support_triage_analytics`) including status breakdowns, resolution
    rate (%), escalation rate (%), average message turns, and top issue tags.
- **Pydantic Schemas**:
  - `SessionSummaryRequest` and `SessionSummaryResponse` with summary, key points, sentiment, and suggested tags.
  - Enhanced `SessionInfo` and `UpdateSessionRequest` including `resolution_notes` and `summary`.
  - `SupportTriageAnalyticsResponse` with status counts, rates, average turns, and tag distributions.
- **FastAPI Endpoints**:
  - `POST /sessions/{session_id}/summarize`: generate summary, sentiment, and tags, with optional database save.
  - `GET /sessions/triage-analytics`: return aggregated support triage analytics.
  - Extended `PATCH /sessions/{session_id}`: accept and update `resolution_notes` and `summary`.
  - Extended `GET /sessions/{session_id}/export`: include summary and resolution notes in Markdown, JSON, and CSV exports.
- **Client & Streamlit UI Integration**:
  - Client methods in `app/api_utils.py`: `summarize_session()`, `get_support_triage_analytics()`, and extended `update_session()`.
  - Support Triage Analytics Card in `app/sidebar.py`: display operational KPIs (Total Sessions, Resolution Rate %, Escalation Rate %, Avg Turns, status pills, top issue tags).
  - Active Session Resolution & Triage Panel in `app/sidebar.py`: button to trigger auto-summarization, sentiment badge, and resolution notes editor with save action.
- **Quality Gates**: Maintain test coverage >= 80%, zero ruff errors, zero mypy errors.

### Explicit Exclusions (Deferred to v0.28.0+)
- Real-time third-party ticketing webhooks (Zendesk, Jira, PagerDuty).
- Continuous audio/speech-to-text live stream ingestion.

### Granular Task Breakdown
- [x] Task 1: `ROADMAP.md` v0.27.0 plan specification
- [x] Task 2: Database schema migration and triage analytics queries in `api/db_utils.py` with unit tests
- [x] Task 3: Conversation summarization & sentiment engine in `api/summarization.py` with unit tests
- [x] Task 4: Pydantic schemas for summarization and triage analytics in `api/pydantic_models.py` with unit tests
- [x] Task 5: Multi-format session export presenter updates with resolution details in `api/presenters.py` with unit tests
- [x] Task 6: API routes `POST /sessions/{session_id}/summarize`, `GET /sessions/triage-analytics`, and extended `PATCH /sessions/{session_id}` in `api/main.py` with unit tests
- [x] Task 7: Client helpers `summarize_session`, `get_support_triage_analytics`, and extended `update_session` in `app/api_utils.py` with unit tests
- [x] Task 8: Streamlit UI support triage analytics widget and session resolution/summary panel in `app/sidebar.py` with unit tests
- [x] Task 9: Documentation updates (`docs/API.md`, `README.md`, `pyproject.toml`, `api/settings.py`) and final verification gate

## v0.28.0 plan — Webhook Dispatch & Escalation Alerting Engine ✅ COMPLETED

Deliver an automated webhook event notification engine with secure HMAC-SHA256 signature verification, event filtering, delivery audit logging, and administrative management in the Streamlit UI:
external notifications for escalated and resolved support sessions and negative CSAT feedback dispatched in real time to external systems (Slack, Zendesk, incident management, or custom HTTP endpoints).

### Scope & Objectives
- **Webhook Dispatcher Engine**: `api/webhooks.py` providing HMAC-SHA256 signature calculation (`X-Webhook-Signature`, `X-Webhook-Timestamp`, `X-Webhook-Event`), structured event envelope construction (`id`, `event`, `timestamp`, `data`), synchronous and background dispatch execution with timeout resilience, delivery audit recording, and test pinging (`ping_webhook`).
- **Database Persistence & Delivery Audit**:
  - SQLite schema migration: add `webhooks` table (endpoint URL, subscribed events, optional secret, active flag, failure count) and `webhook_delivery_logs` table (webhook ID, event, HTTP status code, success flag, payload preview, error details, delivered timestamp).
  - DB operations in `api/db_utils.py`: register, list, retrieve, update, and delete webhooks, record delivery attempts, and query delivery history.
- **Pydantic Schemas**:
  - `WebhookCreateRequest`, `WebhookUpdateRequest`, `WebhookResponse`, `WebhookDeliveryLogItem`, and `WebhookPingResponse` in `api/pydantic_models.py`.
- **FastAPI Endpoints**:
  - `POST /webhooks`: register a new webhook with URL validation and event filtering.
  - `GET /webhooks`: list registered webhooks.
  - `GET /webhooks/{webhook_id}`: get webhook details and recent delivery logs.
  - `PATCH /webhooks/{webhook_id}`: update webhook URL, events, active flag, or secret.
  - `DELETE /webhooks/{webhook_id}`: delete webhook and its delivery logs.
  - `POST /webhooks/{webhook_id}/ping`: test dispatch a verification event.
  - `GET /webhooks/deliveries`: query recent delivery audit logs across all webhooks.
- **Event Trigger Wiring**:
  - `session.escalated`: triggered on session status update to `escalated`.
  - `session.resolved`: triggered on session status update to `resolved`.
  - `feedback.negative`: triggered when user submits negative rating (`-1`).
- **Client & Streamlit UI Integration**:
  - Client methods in `app/api_utils.py`: `create_webhook()`, `list_webhooks()`, `update_webhook()`, `delete_webhook()`, `ping_webhook()`, `list_webhook_deliveries()`.
  - Streamlit UI in `app/sidebar.py`: Webhooks & Alerts management panel with webhook listing, event pills, one-click test ping, registration form, and delivery audit log viewer.
- **Quality Gates**: Maintain test coverage >= 80%, zero ruff errors, zero mypy errors.

### Explicit Exclusions (Deferred to v0.29.0+)
- Distributed Celery/RabbitMQ background queue brokers (runs in-process with FastAPI background tasks).
- OAuth2 token exchange with third-party webhook receivers.

### Granular Task Breakdown
- [x] Task 1: `ROADMAP.md` v0.28.0 plan specification
- [x] Task 2: Database schema migration and CRUD operations for webhooks and delivery logs in `api/db_utils.py` with unit tests
- [x] Task 3: Webhook dispatcher engine in `api/webhooks.py` with unit tests
- [x] Task 4: Pydantic schemas in `api/pydantic_models.py` with unit tests
- [x] Task 5: API routes in `api/main.py` and event trigger wiring with unit tests
- [x] Task 6: Client helpers in `app/api_utils.py` with unit tests
- [x] Task 7: Streamlit UI webhook manager and delivery audit viewer in `app/sidebar.py` with unit tests
- [x] Task 8: Documentation updates (`docs/API.md`, `README.md`, `ROADMAP.md`, `pyproject.toml`, `api/settings.py`), version bump to 0.28.0, and final verification gate

## v0.29.0 plan — Support Canned Responses & Action Macro Templates Engine ✅ COMPLETED

Deliver an enterprise-grade canned responses and action macro templates engine for real estate customer support operations:
pre-approved response templates with category classification, shortcut triggers, dynamic variable substitution (`{customer_name}`, `{session_id}`, `{unit_id}`, `{agent_name}`, `{date}`, `{support_contact}`), safe template rendering, quick action execution (automated status transitions to `resolved` or `escalated` with webhook triggers, tag assignment, conversation injection), and an interactive Quick Responses & Macros panel in the Streamlit UI.

### Scope & Objectives
- **Macro Template Rendering Engine**: `api/macros.py` providing template parsing, parameter extraction, and safe string substitution with fallback defaults for missing parameters, built-in system variables (`date`, `current_time`, `support_contact`), and domain-specific pre-seeded property management templates (Lease Renewal, Emergency Maintenance, Rent Payment Instructions, Move-Out Inspection).
- **Database Persistence & Seed Migration**:
  - SQLite schema migration: add `support_macros` table (`id`, `title`, `shortcut`, `category`, `content`, `tags` JSON, `status_action`, `created_at`, `updated_at`) with index on `category`.
  - Auto-seed property management standard templates on empty table initialization.
  - DB operations in `api/db_utils.py`: create macro, list macros (with optional `category`, `tag`, and `search` filters), get macro by ID or shortcut, update macro, delete macro, and list distinct categories.
- **Pydantic Schemas**:
  - `MacroCreateRequest`, `MacroUpdateRequest`, `MacroResponse`, `MacroRenderRequest`, `MacroRenderResponse`, `MacroApplyRequest`, and `MacroApplyResponse` in `api/pydantic_models.py`.
- **FastAPI Endpoints**:
  - `POST /macros`: register a new macro template with shortcut uniqueness validation.
  - `GET /macros`: list macro templates with optional category, tag, or search filtering.
  - `GET /macros/categories`: list distinct categories across all templates.
  - `GET /macros/{macro_id}`: get macro template details.
  - `PATCH /macros/{macro_id}`: update title, shortcut, category, content, tags, or status_action.
  - `DELETE /macros/{macro_id}`: delete macro template.
  - `POST /macros/{macro_id}/render`: preview rendered macro template with given variables without applying to session.
  - `POST /sessions/{session_id}/apply-macro`: apply macro directly to an active session: render variables, insert agent response into chat history, apply status transition and tag updates, trigger webhooks (e.g. `session.resolved` or `session.escalated`), and return applied summary.
- **Client & Streamlit UI Integration**:
  - Client methods in `app/api_utils.py`: `create_macro()`, `list_macros()`, `list_macro_categories()`, `get_macro()`, `update_macro()`, `delete_macro()`, `render_macro()`, `apply_macro_to_session()`.
  - Streamlit UI in `app/sidebar.py`: Quick Responses & Macros expander featuring category filtering, template selector with shortcut pill, interactive variable customization input, template preview, 1-click "Apply to Active Session" action button, and "Create New Template" form.
- **Quality Gates**: Maintain test coverage >= 80%, zero ruff errors, zero mypy errors.

### Explicit Exclusions (Deferred to v0.30.0+)
- Role-based permissions on macro creation/deletion (requires multi-tenant identity model).
- Automated AI macro suggestion matching incoming tenant queries using vector similarity.

### Granular Task Breakdown
- [x] Task 1: `ROADMAP.md` v0.29.0 plan specification and current state update
- [x] Task 2: Database schema migration, CRUD operations, and domain seeding for `support_macros` in `api/db_utils.py` with unit tests
- [x] Task 3: Macro template rendering engine in `api/macros.py` with unit tests
- [x] Task 4: Pydantic schemas in `api/pydantic_models.py` with unit tests
- [x] Task 5: FastAPI routes in `api/main.py` and session macro application with webhook trigger wiring with unit tests
- [x] Task 6: Client helpers in `app/api_utils.py` with unit tests
- [x] Task 7: Streamlit UI Quick Responses & Macros panel in `app/sidebar.py` with unit tests
- [x] Task 8: Documentation updates (`docs/API.md`, `README.md`, `ROADMAP.md`, `pyproject.toml`, `api/settings.py`), version bump to 0.29.0, and final verification gate

## v0.30.0 plan — Automated AI Macro Suggestions & Query Intent Classification Engine ✅ COMPLETED

Deliver an automated AI macro suggestion and query intent classification engine that matches incoming tenant inquiries to relevant property management canned responses, scores relevance confidence, automatically extracts query variables (e.g., unit IDs, resident names, dates), and provides 1-click preview and application in both the API and Streamlit UI.

### Scope & Objectives
- **Intent Classification & Entity Extraction Engine**: `api/macro_suggestions.py`
  - Detect property management customer intent taxonomies (`maintenance_emergency`, `maintenance_routine`, `rent_payment`, `lease_renewal`, `move_out`, `general_inquiry`) with confidence scores using hybrid heuristic pattern matching and domain triggers.
  - Extract domain-specific template entities (`unit_id`, `customer_name`, `issue_description`) from raw tenant messages to pre-populate macro placeholder variables.
  - Multi-factor macro recommendation scoring: evaluate candidate macros against user queries via shortcut triggers, intent category alignment, token/keyword overlap, and tag matching, normalizing confidence to `0.0` - `1.0`.
  - Provide human-readable match explanations (e.g., `"Matched emergency maintenance intent"`, `"Keywords matched: leak, water"`) for explainable operator recommendations.
- **Database Query Helper**:
  - `get_session_latest_user_query(session_id)` in `api/db_utils.py` to inspect the most recent user turn from `application_logs` for an active session.
- **Pydantic Schemas**:
  - `MacroSuggestionItem`, `MacroSuggestRequest`, `MacroSuggestResponse`, and `SessionMacroSuggestionsResponse` in `api/pydantic_models.py`.
- **FastAPI Endpoints**:
  - `POST /macros/suggest`: evaluate arbitrary query text (with optional category, threshold, and limit filters), returning ranked macro suggestions with rendered previews and suggested variables.
  - `GET /sessions/{session_id}/macro-suggestions`: inspect active session's latest turn, compute tailored suggestions, automatically filling `{session_id}` and extracted entities.
- **Client & Streamlit UI Integration**:
  - Client methods in `app/api_utils.py`: `suggest_macros()` and `get_session_macro_suggestions()` with error handling and API key forwarding.
  - Streamlit UI in `app/sidebar.py`:
    - Real-time "Smart Suggestions" card inside the Quick Responses & Macros expander when active sessions contain messages.
    - Top recommendation pill with confidence score (e.g. `92% Match`), detected intent, and match reasons.
    - One-click "Apply Suggestion" button that pre-fills template variables and loads the template for instant review and dispatch.
    - Interactive "Query Match Tester" expander enabling support agents to test queries and see real-time matching suggestions.
- **Quality Gates**: Maintain test coverage floor >= 80%, zero ruff lint errors, zero mypy type errors.

### Explicit Exclusions (Deferred to v0.31.0+)
- Role-based multi-tenant permissions on macro creation/deletion.
- Fine-tuned transformer model training pipelines in background Celery workers.

### Granular Task Breakdown
- [x] Task 1: `ROADMAP.md` v0.30.0 plan specification and current state update
- [x] Task 2: Core intent classification, entity extraction, and smart macro suggestion engine in `api/macro_suggestions.py` with unit tests in `tests/test_macro_suggestions.py`
- [x] Task 3: Pydantic schemas in `api/pydantic_models.py` with unit tests in `tests/test_models.py`
- [x] Task 4: Database helper `get_session_latest_user_query` in `api/db_utils.py` with unit tests in `tests/test_db_utils.py`
- [x] Task 5: FastAPI routes in `api/main.py` (`POST /macros/suggest`, `GET /sessions/{session_id}/macro-suggestions`) with unit tests in `tests/test_main.py`
- [x] Task 6: Client helpers in `app/api_utils.py` with unit tests in `tests/test_api_utils.py`
- [x] Task 7: Streamlit UI Smart Macro Suggestions and Query Tester in `app/sidebar.py` with unit tests in `tests/test_app_ui.py`
- [x] Task 8: Documentation updates (`docs/API.md`, `README.md`, `ROADMAP.md`, `pyproject.toml`, `api/settings.py`), version bump to 0.30.0, and final verification gate

## v0.31.0 plan — Customer Support SLA Policies, Priority Triage & Automated Escalation Alerts Engine ✅ COMPLETED

Deliver an operational Service Level Agreement (SLA) policy and priority triage tracking engine for real estate customer support operations:
configurable SLA target times per priority and category, session priority assignment (`urgent`, `high`, `medium`, `low`), automated deadline and breach calculations (`response_due_at`, `resolution_due_at`, `breach_status`), real-time webhook alerting triggers on approaching SLA breach (`sla.approaching_breach`) and breached deadlines (`sla.breached`), and Streamlit UI priority badges, SLA countdown timers, and operational SLA compliance analytics.

### Scope & Objectives
- **SLA Policy Management**:
  - SQLite table `sla_policies` (`id`, `name`, `priority`, `category`, `response_time_minutes`, `resolution_time_minutes`, `is_active`, `created_at`, `updated_at`) with unique index on `(priority, category)`.
  - Default property management SLA policies seeded on initialization:
    - Urgent Maintenance (priority: urgent, category: maintenance, response: 15m, resolution: 120m)
    - Urgent General (priority: urgent, category: general, response: 30m, resolution: 240m)
    - High Maintenance (priority: high, category: maintenance, response: 60m, resolution: 480m)
    - High General (priority: high, category: general, response: 120m, resolution: 720m)
    - Medium General (priority: medium, category: general, response: 240m, resolution: 1440m)
    - Low General (priority: low, category: general, response: 1440m, resolution: 2880m)
  - DB operations in `api/db_utils.py`: create, get, list, update, delete, and match best policy.
- **Session Priority Triage**:
  - Schema migration: add `priority TEXT NOT NULL DEFAULT 'medium'` to `session_labels`.
  - Priority validation (`urgent`, `high`, `medium`, `low`) and default handling.
  - Update `update_session_metadata()`, `get_session_metadata()`, and session queries to include priority.
- **Core SLA Engine (`api/sla.py`)**:
  - `calculate_session_sla_status(session_id, current_time=None)`:
    - Inferred category from session tags or query, matching active SLA policy.
    - Calculates `response_due_at`, `resolution_due_at`, `response_met`, `resolution_met`, `response_breached`, `resolution_breached`, `response_approaching`, `resolution_approaching`, `breach_status`, and remaining minutes.
  - `evaluate_and_dispatch_sla_alerts(approaching_threshold_minutes=30)`:
    - Evaluates all active sessions, dispatches `sla.approaching_breach` and `sla.breached` webhook events via `webhooks.dispatch_event`.
  - `get_sla_compliance_analytics()`:
    - Operational compliance rate (%), total tracked sessions, breached/approaching counts, priority breakdown.
- **Webhook Event Integration**:
  - Extend `VALID_WEBHOOK_EVENTS` in `api/db_utils.py` to allow `"sla.approaching_breach"` and `"sla.breached"`.
- **FastAPI Endpoints (`api/main.py`)**:
  - `GET /sla/policies`: list SLA policies with optional priority/category/active filters.
  - `POST /sla/policies`: create a new SLA policy.
  - `GET /sla/policies/{policy_id}`: get SLA policy by ID.
  - `PATCH /sla/policies/{policy_id}`: update policy targets or status.
  - `DELETE /sla/policies/{policy_id}`: delete SLA policy.
  - `GET /sessions/{session_id}/sla`: get real-time SLA status and deadlines for a session.
  - `POST /sla/evaluate-alerts`: scan sessions, evaluate deadlines, and dispatch webhook alerts.
  - `GET /sla/analytics`: get SLA compliance analytics.
  - Update session metadata routes to support updating `priority`.
- **Client & Streamlit UI Integration**:
  - Client methods in `app/api_utils.py`: `list_sla_policies()`, `create_sla_policy()`, `get_sla_policy()`, `update_sla_policy()`, `delete_sla_policy()`, `get_session_sla()`, `evaluate_sla_alerts()`, `get_sla_analytics()`.
  - Streamlit UI in `app/sidebar.py`:
    - Priority selector in session metadata panel with priority badges (🔴 Urgent, 🟠 High, 🟡 Medium, 🔵 Low).
    - Real-time SLA Status card on active session showing policy, target response/resolution due times, countdowns, and breach status.
    - "SLA Policies & Compliance" expander with compliance metrics, policy table/creator form, and one-click alert evaluation trigger.
- **Quality Gates**: Maintain test coverage floor >= 80%, zero ruff errors, zero mypy errors.

### Acceptance Criteria
1. `sla_policies` table exists, auto-seeds default real estate policies on initialization, and supports CRUD with `(priority, category)` resolution.
2. `session_labels` table migrates to include `priority TEXT NOT NULL DEFAULT 'medium'` column with validation for `urgent`, `high`, `medium`, `low`.
3. `calculate_session_sla_status()` matches the best policy, calculates `response_due_at`, `resolution_due_at`, evaluates met/breached/approaching status based on message timestamps and session lifecycle status.
4. Webhook events `sla.approaching_breach` and `sla.breached` are recognized and dispatched to registered webhooks when alerts are evaluated.
5. FastAPI endpoints `/sla/policies`, `/sessions/{session_id}/sla`, `/sla/evaluate-alerts`, and `/sla/analytics` are functional and schema-validated.
6. Client helpers in `app/api_utils.py` provide reliable access with authentication and error handling.
7. Streamlit UI displays priority badges, active session SLA countdown card, and SLA Policies & Compliance analytics panel.
8. Full test suite passes with >= 80% coverage and zero ruff / mypy errors.

### Granular Task Breakdown
- [x] Task 1: `ROADMAP.md` v0.31.0 plan specification and `docs/PROGRESS.md` record initialization
- [x] Task 2: Database schema migration, `sla_policies` CRUD, and priority support in `api/db_utils.py`
- [x] Task 3: Unit tests for database priority migration and SLA policy CRUD in `tests/test_db_utils.py`
- [x] Task 4: Pydantic schemas in `api/pydantic_models.py`
- [x] Task 5: Unit tests for SLA Pydantic models in `tests/test_models.py`
- [x] Task 6: Core SLA calculation, breach detection, alert dispatching, and compliance analytics engine in `api/sla.py`
- [x] Task 7: Unit tests for SLA engine in `tests/test_sla.py`
- [x] Task 8: FastAPI routes in `api/main.py` and session priority update handling
- [x] Task 9: Integration and endpoint tests for FastAPI SLA routes in `tests/test_api_routes.py`
- [x] Task 10: Client helpers in `app/api_utils.py` with unit tests in `tests/test_api_utils.py`
- [x] Task 11: Streamlit UI priority triage, SLA countdown card, and compliance panel in `app/sidebar.py`
- [x] Task 12: Streamlit UI unit tests in `tests/test_app_ui.py`
- [x] Task 13: Documentation updates in `docs/API.md` and `README.md`
- [x] Task 14: Version bump to 0.31.0 in `pyproject.toml` and `api/settings.py`
- [x] Task 15: Final verification, progress record completion, and review audit

## v0.32.0 plan — Customer Support Agent Assignment, Tiered Escalation Routing & Operating Business Hours Engine ✅ COMPLETED

Deliver an operational support agent directory, tiered session routing, workload balancing, and operating business hours engine:
support agent profiles (`support_agents` table: ID, name, email, tier, department/specialty, status), session assignment and escalation tiers (`assigned_agent` and `escalation_tier` on `session_labels`), assignment audit tracking (`session_assignment_history` table), intelligent workload-balanced auto-assignment, real-time assignment and tier escalation webhook triggers (`session.assigned`, `session.tier_escalated`), operating business hours engine (`api/business_hours.py`) calculating business-minute aware SLA deadlines and operating state, and Streamlit UI assignment controls, agent workload dashboard, and queue filters.

### Scope & Objectives
- **Support Agent Directory & Profile Management**:
  - SQLite table `support_agents` (`id`, `name`, `email`, `tier`, `department`, `is_active`, `created_at`, `updated_at`).
  - Pre-seeded default property management agent profiles across tiers:
    - Frontline (Tier 1): `agent_sarah` (Sarah Connor, general_leasing), `agent_david` (David Miller, maintenance)
    - Senior Operations (Tier 2): `agent_elena` (Elena Vance, maintenance), `agent_marcus` (Marcus Brody, billing)
    - Management & Legal (Tier 3): `agent_rachel` (Rachel Green, management)
  - DB CRUD operations in `api/db_utils.py`: create, get, list, update, and delete support agents.
- **Session Agent Assignment & Tiered Routing**:
  - Schema migration on `session_labels`:
    - Add `assigned_agent TEXT DEFAULT NULL`
    - Add `escalation_tier TEXT NOT NULL DEFAULT 'tier_1'` (`tier_1`, `tier_2`, `tier_3`)
  - Schema table `session_assignment_history` (`id`, `session_id`, `assigned_by`, `previous_agent`, `new_agent`, `previous_tier`, `new_tier`, `reason`, `assigned_at`).
  - Core assignment module `api/assignment.py`:
    - `assign_session(session_id, agent_id=None, tier=None, assigned_by=None, reason=None)`: validates agent, tier, updates session, logs history, and dispatches webhooks.
    - `auto_assign_session(session_id, strategy="least_busy")`: assigns least-busy eligible active agent for the session's category and tier.
    - `get_agent_workload_analytics()`: computes active sessions per agent, pending tickets per tier, and unassigned queue count.
  - Webhook integration: extend `VALID_WEBHOOK_EVENTS` to support `"session.assigned"` and `"session.tier_escalated"`.
- **Operating Business Hours Engine (`api/business_hours.py`)**:
  - Configurable weekly schedule: Monday to Friday 09:00 - 18:00 (default), with weekend/holiday boundary crossing.
  - `is_within_business_hours(dt, schedule=None) -> bool`.
  - `get_next_business_window_start(dt, schedule=None) -> datetime`.
  - `add_business_minutes(start_dt, minutes, schedule=None) -> datetime`: advances timestamps strictly through open business minutes.
  - `get_business_hours_status(current_time=None) -> BusinessHoursStatus`: returns live open/closed indicator, next opening time, and schedule summary.
  - SLA policy enhancement: add `use_business_hours INTEGER NOT NULL DEFAULT 0` column to `sla_policies` and wire into `calculate_session_sla_status()`.
- **FastAPI Endpoints (`api/main.py`)**:
  - `GET /agents`: list all agents with filters for `tier`, `department`, `is_active`.
  - `POST /agents`: create a new support agent profile.
  - `GET /agents/{agent_id}`: get agent profile.
  - `PATCH /agents/{agent_id}`: update agent profile.
  - `DELETE /agents/{agent_id}`: delete/deactivate agent.
  - `GET /agents/workload`: get team workload analytics and queue distribution.
  - `POST /sessions/{session_id}/assign`: assign or reassign session to agent / tier.
  - `POST /sessions/{session_id}/auto-assign`: auto-assign least-busy eligible agent.
  - `GET /sessions/{session_id}/assignment-history`: fetch assignment audit history.
  - `GET /business-hours/status`: get current operating hours status and schedule.
- **Client & Streamlit UI Integration**:
  - Client methods in `app/api_utils.py`: `list_agents()`, `create_agent()`, `get_agent()`, `update_agent()`, `delete_agent()`, `get_agent_workload()`, `assign_session()`, `auto_assign_session()`, `get_session_assignment_history()`, `get_business_hours_status()`.
  - Streamlit UI in `app/sidebar.py`:
    - Operating Hours status badge (🟢 Open / 🌙 Closed) in sidebar header.
    - Session Assignee & Escalation Tier controls in session metadata panel with 1-click Auto-Assign button.
    - Assignment history audit viewer expander for active session.
    - Past Sessions queue filters: All, Unassigned, Assigned to Me, Escalated (Tier 2/3).
    - Team Workload & Agent Directory management expander.
- **Quality Gates**: Maintain test coverage floor >= 80%, zero ruff errors, zero mypy errors.

### Acceptance Criteria
1. `support_agents` table exists, pre-seeds 5 default real estate agents on initialization, and supports full CRUD.
2. `session_labels` table migrates to include `assigned_agent TEXT DEFAULT NULL` and `escalation_tier TEXT NOT NULL DEFAULT 'tier_1'` with validation for `tier_1`, `tier_2`, `tier_3`.
3. `session_assignment_history` table records audit log transitions for agent and tier re-assignments with timestamps, actors, and reasons.
4. `api/assignment.py` supports manual assignment and least-busy auto-assignment with webhook notifications (`session.assigned`, `session.tier_escalated`).
5. `api/business_hours.py` accurately evaluates business hours status and advances deadlines across nights and weekends for business-hours SLA policies.
6. FastAPI endpoints `/agents`, `/agents/workload`, `/sessions/{id}/assign`, `/sessions/{id}/auto-assign`, `/sessions/{id}/assignment-history`, and `/business-hours/status` are functional and schema-validated.
7. Client helpers in `app/api_utils.py` provide typed API methods with error handling.
8. Streamlit UI displays operating hours indicator, assignee/tier controls, auto-assign action, queue filters, and team workload panel.
9. Full test suite passes with >= 80% coverage and zero ruff / mypy errors.

### Granular Task Breakdown
- [x] Task 1: `ROADMAP.md` v0.32.0 plan specification and `docs/PROGRESS.md` initialization
- [x] Task 2: Database schema migration, `support_agents` CRUD, `session_assignment_history` in `api/db_utils.py`
- [x] Task 3: Unit tests for database agent CRUD, assignment history, and migrations in `tests/test_db_utils.py`
- [x] Task 4: Operating business hours engine in `api/business_hours.py`
- [x] Task 5: Unit tests for business hours calculation in `tests/test_business_hours.py`
- [x] Task 6: Pydantic schemas in `api/pydantic_models.py`
- [x] Task 7: Unit tests for new Pydantic models in `tests/test_models.py`
- [x] Task 8: Core assignment, tiered routing, workload analytics, and SLA business hours integration in `api/assignment.py` and `api/sla.py`
- [x] Task 9: Unit tests for assignment and workload engine in `tests/test_assignment.py`
- [x] Task 10: FastAPI routes in `api/main.py`
- [x] Task 11: Integration and endpoint tests for FastAPI agent and assignment routes in `tests/test_api_routes.py`
- [x] Task 12: Client helpers in `app/api_utils.py` with unit tests in `tests/test_api_utils.py` and `tests/test_app_api_utils.py`
- [x] Task 13: Streamlit UI assignee/tier controls, auto-assign button, queue filters, and workload panel in `app/sidebar.py`
- [x] Task 14: Streamlit UI unit tests in `tests/test_app_ui.py`
- [x] Task 15: Documentation updates in `docs/API.md` and `README.md`
- [x] Task 16: Version bump to 0.32.0 in `pyproject.toml` and `api/settings.py`
- [x] Task 17: Final verification gate, progress record completion, and self-review audit

## v0.33.0 plan — Multi-Criteria CSAT Feedback, Review Queues & Performance Analytics Engine ✅ COMPLETED

Deliver an advanced Customer Satisfaction (CSAT) feedback rating, operator review queue, and agent performance scorecard engine for property management customer service:
5-star multi-criteria CSAT ratings (overall score 1-5, resolution satisfaction 1-5, agent helpfulness 1-5, response speed 1-5), tenant feedback review queue with triage statuses (`pending_review`, `reviewed`, `followup_required`, `archived`) and resolution notes, automated alert triggers on low CSAT (`feedback.low_csat`), agent scorecard analytics attributing ratings to assigned agents and escalation tiers, and Streamlit UI 5-star rating widget and feedback management review panel.

### Scope & Objectives
- **Multi-Criteria CSAT Feedback Schema & Persistence**:
  - Enhance `feedback` table schema via SQLite migration in `api/db_utils.py`:
    - Add `score INTEGER DEFAULT NULL` (1 to 5 star rating, alongside backward-compatible `rating` -1/1)
    - Add `resolution_satisfaction INTEGER DEFAULT NULL` (1 to 5)
    - Add `agent_helpfulness INTEGER DEFAULT NULL` (1 to 5)
    - Add `response_speed INTEGER DEFAULT NULL` (1 to 5)
    - Add `review_status TEXT NOT NULL DEFAULT 'pending_review'` (`pending_review`, `reviewed`, `followup_required`, `archived`)
    - Add `assigned_agent TEXT DEFAULT NULL` (automatically captured from session metadata at feedback submission)
    - Add `escalation_tier TEXT NOT NULL DEFAULT 'tier_1'` (captured from session metadata)
    - Add `reviewer_notes TEXT DEFAULT NULL`
    - Add `reviewed_at TEXT DEFAULT NULL`
    - Add `reviewed_by TEXT DEFAULT NULL`
  - DB operations in `api/db_utils.py`:
    - `submit_csat_feedback()`: records multi-criteria scores, captures active session assignee and tier, and auto-sets review status.
    - `list_feedback_review_queue()`: filters by `review_status`, `assigned_agent`, `min_score`, `max_score`, `escalation_tier`, and pagination.
    - `update_feedback_review()`: updates `review_status`, `reviewer_notes`, `reviewed_by`, and `reviewed_at`.
    - `get_agent_performance_analytics()`: calculates average CSAT, total ratings, 5-star distributions, resolution score, helpfulness score, and speed score grouped by agent and tier.
- **CSAT Analytics & Alerting Engine (`api/csat.py`)**:
  - `calculate_csat_summary()`: overall CSAT score (%), Net Promoter/Satisfaction Score, rating breakdown (1-5 stars), response rate, and category satisfaction trends.
  - `evaluate_low_csat_alert()`: dispatches real-time `feedback.low_csat` webhook event when feedback score <= 2 or rating == -1.
- **Webhook Integration**:
  - Extend `VALID_WEBHOOK_EVENTS` in `api/db_utils.py` to support `"feedback.low_csat"`.
- **Pydantic Schemas (`api/pydantic_models.py`)**:
  - `CSATFeedbackSubmitRequest`, `FeedbackReviewUpdateRequest`, `CSATSummaryResponse`, `AgentPerformanceScorecardItem`, `AgentPerformanceAnalyticsResponse`, and `FeedbackReviewItemResponse`.
- **FastAPI Endpoints (`api/main.py`)**:
  - `POST /feedback/csat`: submit multi-criteria 5-star CSAT rating with comments.
  - `GET /feedback/queue`: query feedback items with filter options for `review_status`, `assigned_agent`, `min_score`, `max_score`.
  - `PATCH /feedback/{feedback_id}/review`: update triage status and operator review notes on feedback.
  - `GET /feedback/csat-summary`: aggregated CSAT score percentages, star distribution, and criteria averages.
  - `GET /feedback/agent-scorecards`: agent and tier performance scorecards with CSAT attribution.
- **Client & Streamlit UI Integration**:
  - Client methods in `app/api_utils.py`: `submit_csat_feedback()`, `get_feedback_queue()`, `update_feedback_review()`, `get_csat_summary()`, `get_agent_scorecards()`.
  - Streamlit UI in `app/chat_interface.py`:
    - Interactive 5-star CSAT survey widget at conversation end or on resolved sessions (overall rating, resolution, agent helpfulness, speed, and optional tenant comment).
  - Streamlit UI in `app/sidebar.py`:
    - Enhanced Feedback Review Panel: filter by review status, score, agent; review actions (`Mark Reviewed`, `Request Follow-up`); reviewer note editor.
    - Agent CSAT Scorecards & Performance dashboard: display average CSAT, ratings count, and performance breakdown by tier.
- **Quality Gates**: Maintain test coverage floor >= 80%, zero ruff errors, zero mypy errors.

### Acceptance Criteria
1. `feedback` table schema migrates to support `score` (1-5), sub-criteria (`resolution_satisfaction`, `agent_helpfulness`, `response_speed`), `review_status`, `assigned_agent`, `escalation_tier`, `reviewer_notes`, `reviewed_at`, and `reviewed_by`.
2. `submit_csat_feedback()` persists multi-criteria feedback, captures current session's assigned agent and tier, and dispatches `feedback.low_csat` webhook when score <= 2.
3. `update_feedback_review()` allows operators to update `review_status` (`pending_review`, `reviewed`, `followup_required`, `archived`) and append reviewer notes.
4. `get_agent_performance_analytics()` and `calculate_csat_summary()` accurately compute aggregate metrics, star distributions, and agent scorecards.
5. FastAPI endpoints `/feedback/csat`, `/feedback/queue`, `/feedback/{id}/review`, `/feedback/csat-summary`, and `/feedback/agent-scorecards` are functional and schema-validated.
6. Client helpers in `app/api_utils.py` provide typed methods with authentication and error handling.
7. Streamlit UI supports 5-star multi-criteria CSAT submission in chat and administrative review queue & agent scorecard dashboard in the sidebar.
8. Full test suite passes with >= 80% coverage and zero ruff / mypy errors.

### Granular Task Breakdown
- [x] Task 1: `ROADMAP.md` v0.33.0 plan specification and `docs/PROGRESS.md` initialization
- [x] Task 2: Database schema migration and CRUD operations for CSAT & review queue in `api/db_utils.py`
- [x] Task 3: Unit tests for CSAT database schema, queries, and migrations in `tests/test_db_utils.py`
- [x] Task 4: Core CSAT calculation, agent scorecard analytics, and alert engine in `api/csat.py`
- [x] Task 5: Unit tests for CSAT calculation engine in `tests/test_csat.py`
- [x] Task 6: Pydantic schemas in `api/pydantic_models.py`
- [x] Task 7: Unit tests for CSAT Pydantic schemas in `tests/test_models.py`
- [x] Task 8: FastAPI routes in `api/main.py`
- [x] Task 9: Integration and endpoint tests for FastAPI CSAT routes in `tests/test_api_routes.py`
- [x] Task 10: Client helpers in `app/api_utils.py` with unit tests in `tests/test_api_utils.py` and `tests/test_app_api_utils.py`
- [x] Task 11: Streamlit chat interface 5-star CSAT survey widget in `app/chat_interface.py`
- [x] Task 12: Streamlit sidebar feedback review queue and agent performance scorecard in `app/sidebar.py`
- [x] Task 13: Streamlit UI unit tests in `tests/test_app_ui.py`
- [x] Task 14: Documentation updates in `docs/API.md` and `README.md`
- [x] Task 15: Version bump to 0.33.0 in `pyproject.toml` and `api/settings.py`
- [x] Task 16: Final verification gate, progress record completion, and self-review audit

## v0.34.0 plan — Knowledge Base Gap Detection, FAQ Article Drafting & Self-Service Deflection Engine ✅ COMPLETED

Deliver an end-to-end Knowledge Base Gap Detection, FAQ Article Drafting, and Self-Service Deflection Engine that closes the loop between customer support sessions/CSAT feedback and the RAG vector knowledge base:
automated and manual tracking of unanswered or low-confidence tenant queries (`knowledge_gaps` table with recurring query deduplication and frequency tracking), automated gap scanning across escalated and low-CSAT (`<= 2` stars) sessions, 1-click structured Markdown Knowledge Base / FAQ article drafting from resolved support sessions or knowledge gaps (`knowledge_articles` table + `api/knowledge_base.py`), 1-click publishing of KB articles directly into the persistent document store (`document_store` / `document_sources` + Chroma indexing) with automatic gap resolution and webhook notifications (`knowledge.gap_detected`, `knowledge.article_published`), self-service coverage & deflection analytics, and Streamlit UI controls for drafting articles from sessions and managing the Knowledge Base Gaps & Article Studio panel.

### Objective & Expected Outcome
Close the knowledge loop between customer support operations and the RAG retrieval corpus so that recurring tenant questions, escalated tickets, and low-CSAT sessions are systematically identified as knowledge gaps, converted into structured Markdown FAQ / Knowledge Base articles, and published directly into the searchable document library to deflect future tickets.

### Scope & Objectives
- **Knowledge Base Gaps & Articles Persistence (`api/db_utils.py`)**:
  - SQLite table `knowledge_gaps`:
    - `id INTEGER PRIMARY KEY AUTOINCREMENT`
    - `query TEXT NOT NULL`
    - `normalized_query TEXT NOT NULL` (for recurring query deduplication & frequency incrementing)
    - `category TEXT NOT NULL DEFAULT 'general'` (`general`, `maintenance`, `lease`, `billing`, `policy`)
    - `source_type TEXT NOT NULL DEFAULT 'unanswered_query'` (`unanswered_query`, `low_csat`, `escalated_session`, `manual`)
    - `session_id TEXT DEFAULT NULL`
    - `frequency INTEGER NOT NULL DEFAULT 1`
    - `priority TEXT NOT NULL DEFAULT 'medium'` (`urgent`, `high`, `medium`, `low`)
    - `status TEXT NOT NULL DEFAULT 'open'` (`open`, `drafting`, `resolved`, `dismissed`)
    - `linked_article_id INTEGER DEFAULT NULL`
    - `notes TEXT DEFAULT ''`
    - `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
    - `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
  - SQLite table `knowledge_articles`:
    - `id INTEGER PRIMARY KEY AUTOINCREMENT`
    - `title TEXT NOT NULL`
    - `category TEXT NOT NULL DEFAULT 'general'`
    - `question_pattern TEXT NOT NULL DEFAULT ''`
    - `content_markdown TEXT NOT NULL`
    - `tags TEXT NOT NULL DEFAULT ''`
    - `source_session_id TEXT DEFAULT NULL`
    - `source_gap_id INTEGER DEFAULT NULL`
    - `status TEXT NOT NULL DEFAULT 'draft'` (`draft`, `published`, `archived`)
    - `author TEXT NOT NULL DEFAULT 'support_agent'`
    - `published_file_id INTEGER DEFAULT NULL`
    - `published_collection TEXT DEFAULT NULL`
    - `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
    - `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
  - DB CRUD operations in `api/db_utils.py`:
    - `record_knowledge_gap()`, `get_knowledge_gap()`, `list_knowledge_gaps()`, `update_knowledge_gap()`, `delete_knowledge_gap()`
    - `create_knowledge_article()`, `get_knowledge_article()`, `list_knowledge_articles()`, `update_knowledge_article()`, `delete_knowledge_article()`
- **Knowledge Base Gap Detection, Article Synthesis & Publishing Engine (`api/knowledge_base.py`)**:
  - `is_unanswered_or_fallback_response(answer: str, sources_count: int = 0) -> bool`: detects fallback/low-coverage answers.
  - `scan_sessions_for_knowledge_gaps() -> dict`: scans escalated sessions, low-CSAT (`<= 2` stars or `rating == -1`) sessions, and unanswered chat logs to register/increment knowledge gaps and dispatch `knowledge.gap_detected` webhooks.
  - `draft_article_from_session(session_id: str, author: str = 'support_agent', category: str | None = None, link_gap_id: int | None = None) -> dict`: synthesizes a structured Markdown FAQ / KB article from a session's tenant inquiry, assistant answers, `summary`, and `resolution_notes` (100% offline deterministic builder with optional LLM refinement), persists it in `knowledge_articles`, and links any associated knowledge gap (`status = 'drafting'`).
  - `publish_knowledge_article(article_id: int, collection: str = 'default', chunking_strategy: str = 'markdown', chunk_size: int = 1000, chunk_overlap: int = 200) -> dict`: writes the article Markdown into `document_store` and `document_sources`, indexes chunks into Chroma (with graceful fallback if embeddings are offline), updates `status = 'published'` and `published_file_id`, transitions linked `knowledge_gaps` to `resolved`, and dispatches `knowledge.article_published` webhook.
  - `get_knowledge_base_analytics() -> dict`: aggregates gap counts by status/priority/category, recurring frequency totals, article counts (`draft`, `published`, `archived`), gap resolution rate (%), and estimated self-service ticket deflection metrics.
- **Webhook Integration (`api/db_utils.py`)**:
  - Extend `VALID_WEBHOOK_EVENTS` with `"knowledge.gap_detected"` and `"knowledge.article_published"`.
- **FastAPI Endpoints (`api/main.py` & `api/pydantic_models.py`)**:
  - `POST /knowledge/gaps`: create/log a knowledge gap (or increment recurring match).
  - `GET /knowledge/gaps`: list knowledge gaps with filters (`status`, `category`, `priority`, `source_type`, `limit`).
  - `GET /knowledge/gaps/{gap_id}`: retrieve a knowledge gap by ID.
  - `PATCH /knowledge/gaps/{gap_id}`: update gap status, priority, category, linked article, or notes.
  - `DELETE /knowledge/gaps/{gap_id}`: delete a knowledge gap.
  - `POST /knowledge/gaps/scan`: scan sessions & feedback for knowledge gaps.
  - `POST /knowledge/articles`: create a new KB article draft.
  - `POST /sessions/{session_id}/draft-article`: draft a KB article from a support session's dialogue and resolution notes.
  - `GET /knowledge/articles`: list KB articles with filters (`status`, `category`, `search`).
  - `GET /knowledge/articles/{article_id}`: get a KB article by ID.
  - `PATCH /knowledge/articles/{article_id}`: update a KB article.
  - `DELETE /knowledge/articles/{article_id}`: delete a KB article.
  - `POST /knowledge/articles/{article_id}/publish`: publish a KB article into the RAG document store and resolve linked gaps.
  - `GET /knowledge/analytics`: retrieve KB gap and self-service coverage analytics.
- **Client & Streamlit UI Integration (`app/api_utils.py` & `app/sidebar.py`)**:
  - Client helpers in `app/api_utils.py` for all `/knowledge/*` and `/sessions/{id}/draft-article` routes with `X-API-Key` propagation.
  - Session Resolution Panel (`app/sidebar.py`): 1-click **"📝 Draft KB Article"** button to synthesize a KB draft from the selected session.
  - Dedicated **"📚 Knowledge Gaps & Article Studio"** sidebar expander displaying coverage KPIs, 1-click gap scanner, knowledge gap triage queue, and KB article draft editor / 1-click RAG publisher.

### Acceptance Criteria
1. `knowledge_gaps` and `knowledge_articles` SQLite tables are created and support full CRUD, recurring query deduplication (`normalized_query` frequency incrementing), and validation (`tests/test_db_utils.py`).
2. `api/knowledge_base.py` accurately detects unanswered/fallback responses, scans escalated/low-CSAT sessions for gaps, synthesizes structured Markdown KB drafts from sessions, publishes articles into `document_store`/`document_sources` (resolving linked gaps), and dispatches `knowledge.gap_detected` and `knowledge.article_published` webhooks (`tests/test_knowledge_base.py`).
3. Pydantic schemas in `api/pydantic_models.py` validate all knowledge gap, article drafting, publishing, and analytics payloads (`tests/test_models.py`).
4. FastAPI endpoints `/knowledge/gaps`, `/knowledge/gaps/scan`, `/knowledge/gaps/{id}`, `/knowledge/articles`, `/knowledge/articles/{id}`, `/knowledge/articles/{id}/publish`, `/sessions/{id}/draft-article`, and `/knowledge/analytics` are wired and verified (`tests/test_api_routes.py`).
5. Client helpers in `app/api_utils.py` provide typed methods with `X-API-Key` header forwarding and error handling (`tests/test_app_api_utils.py`).
6. Streamlit UI in `app/sidebar.py` provides 1-click session KB article drafting and the "📚 Knowledge Gaps & Article Studio" management panel (`tests/test_app_ui.py`).
7. Documentation (`README.md`, `docs/API.md`, `ROADMAP.md`, `docs/PROGRESS.md`) and version (`0.34.0`) are updated and accurate.
8. Full verification suite (`pytest` with >= 80% coverage, `ruff check`, `mypy`) passes with zero regressions.

### Validation Plan
- Focused unit tests per micro-step (`tests/test_db_utils.py`, `tests/test_knowledge_base.py`, `tests/test_models.py`, `tests/test_api_routes.py`, `tests/test_app_api_utils.py`, `tests/test_app_ui.py`).
- Full suite verification: `python -m pytest`, `python -m ruff check api/ app/ tests/ scripts/`, `python -m mypy api/ app/ scripts/`.
- End-to-end API workflow verification exercising gap detection -> session article drafting -> article publishing into `document_store` -> gap resolution -> analytics verification.

### Exclusions
- External third-party CMS synchronization (e.g., Confluence, Notion, Zendesk Guide APIs) — excluded to keep the system 100% local-first and keyless.
- Automated unreviewed publishing of LLM-generated articles without operator trigger — excluded to preserve knowledge base curation safety.

### Granular Task Breakdown
- [x] Task 1: `ROADMAP.md` v0.34.0 plan specification and `docs/PROGRESS.md` initialization
- [x] Task 2: Database schema & CRUD operations for `knowledge_gaps` in `api/db_utils.py` + unit tests in `tests/test_db_utils.py`
- [x] Task 3: Database schema & CRUD operations for `knowledge_articles` in `api/db_utils.py` + unit tests in `tests/test_db_utils.py`
- [x] Task 4: Core knowledge gap detection, session scanner, and webhook alerts in `api/knowledge_base.py` + unit tests in `tests/test_knowledge_base.py`
- [x] Task 5: Session-to-KB Markdown article synthesis, RAG publishing, and coverage analytics in `api/knowledge_base.py` + unit tests in `tests/test_knowledge_base.py`
- [x] Task 6: Pydantic request/response models for knowledge gaps, articles, publishing, and analytics in `api/pydantic_models.py` + unit tests in `tests/test_models.py`
- [x] Task 7: FastAPI endpoints for knowledge gaps (`/knowledge/gaps*`) in `api/main.py` + route tests in `tests/test_api_routes.py`
- [x] Task 8: FastAPI endpoints for knowledge articles, session drafting, publishing, and analytics (`/knowledge/articles*`, `/sessions/{id}/draft-article`, `/knowledge/analytics`) in `api/main.py` + route tests in `tests/test_api_routes.py`
- [x] Task 9: Streamlit client API helpers in `app/api_utils.py` + unit tests in `tests/test_app_api_utils.py`
- [x] Task 10: Streamlit UI session KB drafting button and "📚 Knowledge Gaps & Article Studio" sidebar panel in `app/sidebar.py` + UI tests in `tests/test_app_ui.py`
- [x] Task 11: Documentation updates (`docs/API.md`, `README.md`) and version bump to `0.34.0` (`pyproject.toml`, `api/settings.py`)
- [x] Task 12: Final verification gate, self-review audit, progress record completion, and draft PR delivery

## v0.35.0 plan — Tenant Profiles, Property Unit Directory & Context Grounding Engine (IN PROGRESS)

Transform the customer support experience into a tenant-aware, property-grounded care platform. Maintain a structured directory of property units and tenant profiles with lease dates, rent amounts, and balances; link support sessions directly to tenants; inject verified tenant and property unit context into RAG query prompts for personalized tenant answers; auto-populate macro variables (`{customer_name}`, `{unit_id}`, `{tenant_email}`, `{monthly_rent}`, `{balance_due}`); and deliver a dedicated Tenant & Property Directory dashboard in Streamlit.

### Objective & Expected Outcome
Enable personalized, context-rich property management customer support by linking support conversations to persistent tenant and property unit entities. The RAG agent can answer tenant-specific inquiries (rent due, lease terms, amenities, parking, access codes), canned macro templates are auto-populated without manual entry, and property operators have an integrated directory of units, tenants, and comprehensive support histories.

### Scope & Objectives
- **Database Schema & Migrations (`api/db_utils.py`)**:
  - SQLite table `units`:
    - `id TEXT PRIMARY KEY`
    - `property_name TEXT NOT NULL`
    - `unit_number TEXT NOT NULL`
    - `building_name TEXT DEFAULT ''`
    - `floor INTEGER DEFAULT 1`
    - `address TEXT NOT NULL`
    - `city TEXT NOT NULL`
    - `state TEXT NOT NULL`
    - `zip_code TEXT NOT NULL`
    - `monthly_rent REAL NOT NULL DEFAULT 0.0`
    - `parking_spot TEXT DEFAULT ''`
    - `gate_code TEXT DEFAULT ''`
    - `wifi_ssid TEXT DEFAULT ''`
    - `trash_day TEXT DEFAULT ''`
    - `notes TEXT DEFAULT ''`
    - `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
    - `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
  - SQLite table `tenants`:
    - `id TEXT PRIMARY KEY`
    - `first_name TEXT NOT NULL`
    - `last_name TEXT NOT NULL`
    - `email TEXT NOT NULL UNIQUE`
    - `phone TEXT NOT NULL`
    - `unit_id TEXT REFERENCES units(id)`
    - `lease_start TEXT NOT NULL` (YYYY-MM-DD)
    - `lease_end TEXT NOT NULL` (YYYY-MM-DD)
    - `monthly_rent REAL NOT NULL DEFAULT 0.0`
    - `balance_due REAL NOT NULL DEFAULT 0.0`
    - `status TEXT NOT NULL DEFAULT 'active'` (`active`, `pending`, `past_due`, `moved_out`, `evicted`)
    - `emergency_contact_name TEXT DEFAULT ''`
    - `emergency_contact_phone TEXT DEFAULT ''`
    - `notes TEXT DEFAULT ''`
    - `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
    - `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
  - SQLite schema migration for `session_labels`:
    - Add `tenant_id TEXT DEFAULT NULL`
    - Add `unit_id TEXT DEFAULT NULL`
  - Pre-seeding: seed initial property units and tenant profiles on DB initialization for turnkey out-of-the-box operation.
  - CRUD & query methods in `api/db_utils.py`:
    - Units: `create_unit()`, `get_unit()`, `list_units()`, `update_unit()`, `delete_unit()`
    - Tenants: `create_tenant()`, `get_tenant()`, `list_tenants()`, `update_tenant()`, `delete_tenant()`
    - Linking: `link_session_tenant()`, `get_session_tenant_context()`, `get_tenant_support_history()`
- **Tenant Context Grounding & Macro Enhancement (`api/tenant_context.py` & `api/macros.py`)**:
  - `build_tenant_rag_context(tenant_id: str | None, unit_id: str | None) -> str`: produces a concise, structured system context block from tenant and unit profiles for injection into RAG prompt contexts.
  - Variable auto-population: enhance macro rendering in `api/macros.py` and `api/db_utils.py` to automatically resolve `{customer_name}`, `{unit_id}`, `{tenant_email}`, `{monthly_rent}`, `{balance_due}`, `{lease_end}`, `{parking_spot}`, and `{gate_code}` from the session's linked tenant.
  - Webhooks: extend `VALID_WEBHOOK_EVENTS` with `"tenant.created"`, `"tenant.updated"`, and `"tenant.balance_overdue"`.
- **Pydantic Models (`api/pydantic_models.py`)**:
  - Request and response schemas for Units (`UnitCreateRequest`, `UnitUpdateRequest`, `UnitResponse`, `UnitListResponse`).
  - Request and response schemas for Tenants (`TenantCreateRequest`, `TenantUpdateRequest`, `TenantResponse`, `TenantListResponse`).
  - Request and response schemas for Session Tenant Linking & Context (`SessionTenantLinkRequest`, `SessionTenantContextResponse`, `TenantSupportHistoryResponse`).
- **FastAPI Endpoints (`api/main.py`)**:
  - `/units`: CRUD endpoints (`POST /units`, `GET /units`, `GET /units/{id}`, `PATCH /units/{id}`, `DELETE /units/{id}`).
  - `/tenants`: CRUD endpoints (`POST /tenants`, `GET /tenants`, `GET /tenants/{id}`, `PATCH /tenants/{id}`, `DELETE /tenants/{id}`).
  - `/sessions/{id}/link-tenant`: link/unlink tenant and unit to a session.
  - `/sessions/{id}/tenant-context`: retrieve live tenant and property unit card for the session.
  - `/tenants/{id}/support-history`: retrieve all sessions, CSAT feedback ratings, and notes for a tenant.
- **Client & Streamlit UI Integration (`app/api_utils.py` & `app/sidebar.py`)**:
  - Client SDK methods in `app/api_utils.py` with `X-API-Key` propagation and resilient error handling.
  - Streamlit Session Metadata Panel (`app/sidebar.py`): Tenant Context Card & 1-click **"👤 Link Tenant"** modal/selector showing active lease, balance due, and unit details.
  - Streamlit **"🏢 Tenant & Property Directory"** expander panel (`app/sidebar.py`):
    - Unit directory tab/section: search, filter by property, register units.
    - Tenant directory tab/section: search, filter by lease status, register tenants.
    - Tenant Support History viewer: inspect cross-session tickets and CSAT ratings by tenant.
  - Quick Responses & Macros integration: auto-populate tenant details into macro inputs.

### Acceptance Criteria
1. `units` and `tenants` SQLite tables are created, seeded with defaults, supported with full CRUD and validation, and `session_labels` is migrated with `tenant_id` and `unit_id` columns (`tests/test_db_utils.py`).
2. `api/tenant_context.py` accurately generates structured RAG context blocks from tenant and unit records, and macro variable resolution automatically populates tenant details (`tests/test_tenant_context.py`).
3. Pydantic schemas in `api/pydantic_models.py` validate unit creation, tenant management, session linking, and tenant context payloads (`tests/test_models.py`).
4. FastAPI endpoints `/units*`, `/tenants*`, `/sessions/{id}/link-tenant`, `/sessions/{id}/tenant-context`, and `/tenants/{id}/support-history` are wired and verified with complete HTTP status codes (`tests/test_api_routes.py`).
5. Client helpers in `app/api_utils.py` provide typed methods with `X-API-Key` header forwarding and error handling (`tests/test_app_api_utils.py`).
6. Streamlit UI in `app/sidebar.py` provides the Tenant Context Card in session metadata and the "🏢 Tenant & Property Directory" management panel (`tests/test_app_ui.py`).
7. Documentation (`README.md`, `docs/API.md`, `ROADMAP.md`, `docs/PROGRESS.md`) and version (`0.35.0`) are updated and accurate.
8. Full verification suite (`pytest` with >= 80% coverage, `ruff check`, `mypy`) passes with zero regressions.

### Validation Plan
- Focused unit tests per micro-step (`tests/test_db_utils.py`, `tests/test_tenant_context.py`, `tests/test_models.py`, `tests/test_api_routes.py`, `tests/test_app_api_utils.py`, `tests/test_app_ui.py`).
- Full suite verification: `python -m pytest`, `python -m ruff check api/ app/ tests/ scripts/`, `python -m mypy api/ app/ scripts/`.
- End-to-end workflow verification exercising unit creation -> tenant registration -> session linking -> tenant context generation -> macro variable resolution -> support history retrieval.

### Exclusions
- External property management software integrations (e.g. Yardi Voyager, AppFolio, RealPage APIs) — excluded to maintain 100% offline, local-first operation.
- Payment gateway card processing (e.g. Stripe, Plaid) — balance tracking is informational; live merchant banking is out of scope.

### Granular Task Breakdown
- [x] Task 1: `ROADMAP.md` v0.35.0 plan specification and `docs/PROGRESS.md` initialization
- [x] Task 2: Database schema & CRUD operations for `units` in `api/db_utils.py` + unit tests in `tests/test_db_utils.py`
- [x] Task 3: Database schema & CRUD operations for `tenants` in `api/db_utils.py` + unit tests in `tests/test_db_utils.py`
- [x] Task 4: Session tenant linking, migration, and support history queries in `api/db_utils.py` + unit tests in `tests/test_db_utils.py`
- [x] Task 5: Core tenant context grounding engine and macro variable auto-resolution in `api/tenant_context.py` & `api/macros.py` + unit tests in `tests/test_tenant_context.py`
- [x] Task 6: Pydantic request/response models for units, tenants, linking, and context in `api/pydantic_models.py` + unit tests in `tests/test_models.py`
- [x] Task 7: FastAPI endpoints for property units (`/units*`) in `api/main.py` + route tests in `tests/test_api_routes.py`
- [x] Task 8: FastAPI endpoints for tenants, session linking, tenant context, and history (`/tenants*`, `/sessions/{id}/link-tenant`, `/sessions/{id}/tenant-context`) in `api/main.py` + route tests in `tests/test_api_routes.py`
- [x] Task 9: Streamlit client API helpers in `app/api_utils.py` + unit tests in `tests/test_app_api_utils.py`
- [x] Task 10: Streamlit UI session tenant context card, tenant linking, and "🏢 Tenant & Property Directory" sidebar panel in `app/sidebar.py` + UI tests in `tests/test_app_ui.py`
- [x] Task 11: Documentation updates (`docs/API.md`, `README.md`) and version bump to `0.35.0` (`pyproject.toml`, `api/settings.py`)
- [ ] Task 12: Final verification gate, self-review audit, progress record completion, and draft PR delivery

## v0.6.0 plan — Document collections ✅ COMPLETED

Big update: user-defined collections scope documents, retrieval, and the UI
(multi-tenancy stepping stone, no new deps).

- [x] DB: `collection` column on `document_store` with migration for existing DBs
- [x] Chroma: `collection` chunk metadata + filter support
- [x] API: `collection` on upload, `collections[]` filter on chat, `?collection=` on list
- [x] UI: collection picker scoping upload, chat, and document list
- [x] Per-IP daily token quotas (`TOKEN_DAILY_BUDGET_EST`, 0 = off)
- [x] Code-quality pass: dead code, import hygiene, warning-free tests

---

## Phase 1: Code Quality & Developer Experience (Week 1) ✅ COMPLETED

### 1.1 Add linting and formatting
- [x] Add `ruff` for fast Python linting
- [x] Add `black` for code formatting
- [x] Add `mypy` for type checking
- [x] Configure pre-commit hooks
- [x] Update CI to run linting/type-checking

### 1.2 Improve project structure
- [x] Add `pyproject.toml` with modern Python packaging
- [x] Move config to `pyproject.toml` (ruff, black, mypy, pytest)
- [x] Add `uv` support for faster dependency management

### 1.3 Enhance testing
- [x] Add integration tests for full RAG pipeline
- [x] Add test coverage reporting
- [x] Add contract tests for API schemas

---

## Phase 2: Core Features & Reliability (Week 2)

### 2.1 Streaming responses ✅ COMPLETED
- [x] Implement streaming chat endpoint (`/chat/stream`)
- [x] Update Streamlit UI for streaming display
- [x] Add Server-Sent Events (SSE) support

### 2.2 Document processing improvements ✅ COMPLETED
- [x] Add configurable chunking strategies (semantic, recursive, markdown-aware)
- [x] Extract and store document metadata (author, date, page count)
- [x] Add document preview/thumbnails
- [x] Support more file types (txt, md, csv)

### 2.3 Search & retrieval enhancements ✅ COMPLETED (scoped)
- [x] Add hybrid search helper (BM25 + vector, lazy import + vector fallback)
- [x] Add metadata filtering helper (by file_id / filename)
- [x] Wire file_ids / hybrid flags through `/chat` + RAG chain
- [x] Query expansion with RRF fusion (v0.8.0, dependency-free)
- [x] Lexical rerank retriever (v0.10.0, dependency-free baseline)
- [ ] Cross-encoder reranking (deferred: needs new model dependency)

### 2.4 Error handling & resilience ✅ COMPLETED
- [x] Add retry with exponential backoff for Chroma indexing
- [x] Add request-ID middleware (X-Request-ID echo/generate)
- [x] Add upload size limits + chunk-param validation
- [x] Improve error messages and codes (400/404/413/502 plus validation)

---

## Phase 3: Observability & Monitoring (Week 3, IN PROGRESS)

### 3.1 Logging improvements ✅ COMPLETED
- [x] Structured JSON logging (opt-in via LOG_FORMAT=json)
- [x] Correlation IDs for request tracing (X-Request-ID middleware)
- [x] Log levels via LOG_LEVEL (root logger)

### 3.2 Metrics & tracing ✅ COMPLETED (scoped)
- [x] Add lightweight `/metrics` + `/metrics.json` (in-memory counters)
- [x] Add per-route latency averages (no new deps)
- [x] Surface backend metrics in the Streamlit sidebar
- [x] Approximate token-usage counters (char-based estimate)
- [x] Ops dashboard = Streamlit metrics panel + `/metrics` scrape endpoint
- [ ] Integrate OpenTelemetry (deferred: needs py3.11/3.12 verification)
- [ ] Add LangSmith/LangFuse integration (already env-supported)

### 3.3 Health checks ✅ COMPLETED
- [x] Deep health checks (`/health/ready`: DB + Chroma dir; `/health/live`)
- [x] Readiness/liveness probes for Kubernetes (`/health/live`, `/health/ready`)

---

## Phase 4: Security & Production Hardening (Week 4, IN PROGRESS)

### 4.1 Authentication & Authorization (opt-in, no new deps) ✅ COMPLETED (scoped)
- [x] Optional API-key auth (`API_KEY` env; `X-API-Key` on chat/upload/delete)
- [ ] JWT token support (deferred: needs new dep + key management)
- [ ] Role-based access control (deferred: needs identity model)

### 4.2 Rate limiting & quotas (opt-in, no new deps) ✅ COMPLETED (scoped)
- [x] Per-IP sliding-window rate limiting (`RATE_LIMIT_PER_MIN`, 0 = off)
- [x] Approximate token-usage metering (char-based estimate in metrics)
- [x] Daily token quotas per IP (`TOKEN_DAILY_BUDGET_EST` + `GET /quota`)
- [x] Request size limits (`MAX_UPLOAD_MB` enforced → 413)

### 4.3 Data protection (PARTIAL)
- [x] PII redaction in file logs (emails, phones, SSN-like patterns)
- [ ] Encryption at rest for SQLite/Chroma (deferred: needs key management)
- [ ] Secure secret management (`.env` gitignored + secret scan in CI ✅)

---

## Phase 5: Advanced Features (Week 5+)

### 5.1 Multi-tenancy (PARTIAL)
- [x] Collection-scoped stores, retrieval, and UI (v0.6.0 stepping stone)
- [ ] Fully isolated document stores per tenant (deferred: needs identity model)
- [ ] Tenant-aware routing (deferred: needs identity model)

### 5.2 Agentic capabilities
- [ ] Tool use (web search, calculator, SQL)
- [ ] Multi-step reasoning
- [ ] Autonomous document analysis

### 5.3 Evaluation framework (PARTIAL)
- [x] Manual retrieval eval script + golden dataset (`docs/eval/`, needs `OPENAI_API_KEY`)
- [x] Prompt regression tests (fallback + contact + groundedness invariants)
- [ ] Automated RAG evaluation in CI (deferred: needs API credits + fixtures)

### 5.4 UI/UX improvements ✅ COMPLETED (scoped)
- [x] Conversation history sidebar (past sessions via `GET /sessions` + history)
- [x] Accept md/txt/csv in the Streamlit uploader (backend already supports them)
- [x] Dark mode (`.streamlit/config.toml`, shipped in the image)
- [ ] Document annotation/highlighting (deferred)
- [ ] Mobile responsive design (deferred)

---

## Phase 6: DevOps & Deployment (Ongoing)

### 6.1 Containerization ✅ COMPLETED (scoped)
- [x] Multi-stage Dockerfile
- [x] Docker Compose for local dev
- [x] Generic Kubernetes manifests (deployment + service + PVC, live/ready probes)

### 6.2 CI/CD ✅ COMPLETED (scoped)
- [x] Tag-triggered release workflow (tests + GitHub release)
- [x] Staging/production compose overlays + environment matrix
- [x] Database migrations (`migrate_document_store()` + table bootstrapping)

### 6.3 Documentation (PARTIAL)
- [x] API reference (`docs/API.md`; OpenAPI/Swagger auto-served at `/docs`)
- [x] Architecture notes (`docs/ARCHITECTURE.md`)
- [x] Contribution guide (`docs/CONTRIBUTING.md`)
- [x] Architecture decision records (`docs/adr/001-lazy-langchain-imports.md`)
- [x] Runbooks (`docs/RUNBOOK.md`)