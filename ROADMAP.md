# Customer Support RAG Agent - Roadmap

## Current State (v0.15.0, 2026-09-04)
- FastAPI backend: chat, streaming chat (SSE), upload/list/delete, sessions
  + history, metrics with per-route latency averages and approximate token
  usage, live/ready probes; retrieval filters (file_ids, source_filename,
  use_hybrid)
- Streamlit frontend with streaming toggle, chat interface, document
  management, past-sessions switcher, and backend metrics panel
- SQLite for session history and document metadata
- Chroma vector store with OpenAI embeddings; configurable chunking
  (recursive/markdown) and file types: pdf, docx, html, md, txt, csv;
  indexing retries with exponential backoff
- Resilience: X-Request-ID middleware, chunk-param validation, upload cap
- Security (opt-in): API_KEY auth, per-IP sliding-window rate limiting
- Data protection: PII redaction in file logs
- Observability: LOG_LEVEL / LOG_FORMAT=json, in-memory metrics, probes
- Containerization: multi-stage Dockerfile, compose stack, k8s manifests
- Releases: tag-triggered workflow (verify + GitHub release)
- Docs: API reference, architecture, contributing, ADR-001, runbook, eval set
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
- 148 tests passing; ruff + mypy clean (CI gates)

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

## v0.16.0 plan — Retention & maintenance (IN PROGRESS)

Keep a growing library healthy (no new deps).

- [ ] Feedback totals in `GET /stats`
- [ ] Session retention prune (`DELETE /sessions?before=...`)
- [ ] Quality: shared collection/session param normalization

## v0.17.0 candidates (next)

- Cross-encoder reranking (needs new model dependency + eval baseline)
- Staging/production environment targets

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