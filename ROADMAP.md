# Customer Support RAG Agent - Roadmap

## Current State (v0.3.0, 2026-09-04)
- FastAPI backend: chat, streaming chat (SSE), upload/list/delete, metrics,
  live/ready probes; retrieval filters (file_ids, source_filename, use_hybrid)
- Streamlit frontend with streaming toggle, chat interface, document management
- SQLite for session history and document metadata
- Chroma vector store with OpenAI embeddings; configurable chunking
  (recursive/markdown) and file types: pdf, docx, html, md, txt, csv;
  indexing retries with exponential backoff
- Resilience: X-Request-ID middleware, chunk-param validation, upload cap
- Observability: LOG_LEVEL / LOG_FORMAT=json, in-memory metrics, probes
- 41 tests passing; ruff + black + mypy clean

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

### 3.2 Metrics & tracing (IN PROGRESS)
- [x] Add lightweight `/metrics` + `/metrics.json` (in-memory counters)
- [ ] Add per-route latency averages (no new deps)
- [ ] Integrate OpenTelemetry (deferred: needs py3.11/3.12 verification)
- [ ] Add LangSmith/LangFuse integration (already env-supported)
- [ ] Dashboard for latency, token usage, error rates

### 3.3 Health checks ✅ COMPLETED
- [x] Deep health checks (`/health/ready`: DB + Chroma dir; `/health/live`)
- [x] Readiness/liveness probes for Kubernetes (`/health/live`, `/health/ready`)

---

## Phase 4: Security & Production Hardening (Week 4, IN PROGRESS)

### 4.1 Authentication & Authorization (opt-in, no new deps)
- [ ] Optional API-key auth (`API_KEY` env; `X-API-Key` on chat/upload/delete)
- [ ] JWT token support (deferred: needs new dep + key management)
- [ ] Role-based access control (deferred: needs identity model)

### 4.2 Rate limiting & quotas (opt-in, no new deps)
- [ ] Per-IP sliding-window rate limiting (`RATE_LIMIT_PER_MIN`, 0 = off)
- [ ] Token usage quotas (deferred: needs tokenizer + metering)
- [x] Request size limits (`MAX_UPLOAD_MB` enforced → 413)

### 4.3 Data protection
- [ ] PII detection/redaction in logs
- [ ] Encryption at rest for SQLite/Chroma
- [ ] Secure secret management

---

## Phase 5: Advanced Features (Week 5+)

### 5.1 Multi-tenancy
- [ ] Isolated document stores per tenant
- [ ] Tenant-aware routing

### 5.2 Agentic capabilities
- [ ] Tool use (web search, calculator, SQL)
- [ ] Multi-step reasoning
- [ ] Autonomous document analysis

### 5.3 Evaluation framework
- [ ] Automated RAG evaluation (faithfulness, relevance)
- [ ] Golden dataset management
- [ ] Regression testing for prompts

### 5.4 UI/UX improvements
- [ ] Conversation history sidebar
- [ ] Document annotation/highlighting
- [ ] Dark mode
- [ ] Mobile responsive design

---

## Phase 6: DevOps & Deployment (Ongoing)

### 6.1 Containerization (IN PROGRESS)
- [ ] Multi-stage Dockerfile
- [ ] Docker Compose for local dev
- [ ] Kubernetes manifests (deferred: needs cluster target details)

### 6.2 CI/CD
- [ ] Automated releases
- [ ] Staging/production environments
- [ ] Database migrations

### 6.3 Documentation (PARTIAL)
- [x] API reference (`docs/API.md`; OpenAPI/Swagger auto-served at `/docs`)
- [x] Architecture notes (`docs/ARCHITECTURE.md`)
- [x] Contribution guide (`docs/CONTRIBUTING.md`)
- [ ] Architecture decision records (ADRs)
- [ ] Runbooks