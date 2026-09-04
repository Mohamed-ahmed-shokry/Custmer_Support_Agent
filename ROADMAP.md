# Customer Support RAG Agent - Roadmap

## Current State (v0.5.0, 2026-09-04)
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
- 65 tests passing; ruff + mypy clean (CI gates)

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

### 2.3 Search & retrieval enhancements (IN PROGRESS)
- [x] Add hybrid search helper (BM25 + vector, lazy import + vector fallback)
- [x] Add metadata filtering helper (by file_id / filename)
- [x] Wire file_ids / hybrid flags through `/chat` + RAG chain
- [ ] Add reranking with cross-encoder (deferred: needs new model dep + eval)
- [ ] Implement query expansion/rewriting (deferred: needs eval harness)

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

### 3.2 Metrics & tracing (PARTIAL)
- [x] Add lightweight `/metrics` + `/metrics.json` (in-memory counters)
- [x] Add per-route latency averages (no new deps)
- [x] Surface backend metrics in the Streamlit sidebar
- [x] Approximate token-usage counters (char-based estimate)
- [ ] Integrate OpenTelemetry (deferred: needs py3.11/3.12 verification)
- [ ] Add LangSmith/LangFuse integration (already env-supported)
- [ ] Dashboard for latency, token usage, error rates

### 3.3 Health checks ✅ COMPLETED
- [x] Deep health checks (`/health/ready`: DB + Chroma dir; `/health/live`)
- [x] Readiness/liveness probes for Kubernetes (`/health/live`, `/health/ready`)

---

## Phase 4: Security & Production Hardening (Week 4, IN PROGRESS)

### 4.1 Authentication & Authorization (opt-in, no new deps) ✅ COMPLETED (scoped)
- [x] Optional API-key auth (`API_KEY` env; `X-API-Key` on chat/upload/delete)
- [ ] JWT token support (deferred: needs new dep + key management)
- [ ] Role-based access control (deferred: needs identity model)

### 4.2 Rate limiting & quotas (opt-in, no new deps) (PARTIAL)
- [x] Per-IP sliding-window rate limiting (`RATE_LIMIT_PER_MIN`, 0 = off)
- [x] Approximate token-usage metering (char-based estimate in metrics)
- [ ] Token usage quotas (deferred: needs tokenizer + per-key budgets)
- [x] Request size limits (`MAX_UPLOAD_MB` enforced → 413)

### 4.3 Data protection (PARTIAL)
- [x] PII redaction in file logs (emails, phones, SSN-like patterns)
- [ ] Encryption at rest for SQLite/Chroma (deferred: needs key management)
- [ ] Secure secret management (`.env` gitignored + secret scan in CI ✅)

---

## Phase 5: Advanced Features (Week 5+)

### 5.1 Multi-tenancy
- [ ] Isolated document stores per tenant
- [ ] Tenant-aware routing

### 5.2 Agentic capabilities
- [ ] Tool use (web search, calculator, SQL)
- [ ] Multi-step reasoning
- [ ] Autonomous document analysis

### 5.3 Evaluation framework (PARTIAL)
- [x] Manual retrieval eval script + golden dataset (`docs/eval/`, needs `OPENAI_API_KEY`)
- [x] Prompt regression tests (fallback + contact + groundedness invariants)
- [ ] Automated RAG evaluation in CI (deferred: needs API credits + fixtures)

### 5.4 UI/UX improvements (PARTIAL)
- [x] Conversation history sidebar (past sessions via `GET /sessions` + history)
- [x] Accept md/txt/csv in the Streamlit uploader (backend already supports them)
- [ ] Document annotation/highlighting (deferred)
- [ ] Dark mode (deferred: Streamlit theming)
- [ ] Mobile responsive design (deferred)

---

## Phase 6: DevOps & Deployment (Ongoing)

### 6.1 Containerization ✅ COMPLETED (scoped)
- [x] Multi-stage Dockerfile
- [x] Docker Compose for local dev
- [x] Generic Kubernetes manifests (deployment + service + PVC, live/ready probes)

### 6.2 CI/CD (PARTIAL)
- [x] Tag-triggered release workflow (tests + GitHub release)
- [ ] Staging/production environments (deferred: needs hosting target)
- [ ] Database migrations (deferred: schema is IF NOT EXISTS; needs change driver)

### 6.3 Documentation (PARTIAL)
- [x] API reference (`docs/API.md`; OpenAPI/Swagger auto-served at `/docs`)
- [x] Architecture notes (`docs/ARCHITECTURE.md`)
- [x] Contribution guide (`docs/CONTRIBUTING.md`)
- [x] Architecture decision records (`docs/adr/001-lazy-langchain-imports.md`)
- [x] Runbooks (`docs/RUNBOOK.md`)