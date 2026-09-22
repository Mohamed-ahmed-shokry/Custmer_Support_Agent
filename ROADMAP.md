# Customer Support RAG Agent - Roadmap

## Current State (v0.23.0, 2026-09-23)
- FastAPI backend: chat, streaming chat (SSE), upload/list/delete, sessions
  + history, metrics with per-route latency averages and approximate token
  usage, live/ready probes; retrieval filters (file_ids, source_filename,
  use_hybrid)
- Streamlit frontend with streaming toggle, chat interface, document
  management, past-sessions switcher, and backend metrics panel
- SQLite for session history and document metadata
- Chroma vector store with OpenAI embeddings; configurable chunking
  (recursive/markdown) and file types: pdf, docx, html, md, txt, csv;
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
- 373 tests passing; 94.32% total coverage (80% coverage floor in CI config); ruff + mypy clean (CI gates)

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
- Browser-based automated UI testing via Playwright.
- Browser-based automated UI testing via Playwright.

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

## Next Candidates (v0.24.0+)

- Staging/production environment targets (dependent on real credentials)
- Automated end-to-end browser tests via Playwright
- Document chunk semantic re-chunking and visualization
- Multi-tenant user authentication and RBAC permissions
- Browser-based automated UI testing via Playwright

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