# Customer Support RAG Agent - Roadmap

## Current State (v0.2.0)
- FastAPI backend with chat, document upload/list/delete endpoints
- Streamlit frontend with chat interface and document management
- SQLite for session history and document metadata
- Chroma vector store with OpenAI embeddings
- LangChain RAG chain with history-aware retrieval
- 32 unit/integration tests passing

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

### 2.3 Search & retrieval enhancements
- [ ] Add hybrid search (BM25 + vector)
- [ ] Add metadata filtering (by date, source, tags)
- [ ] Add reranking with cross-encoder
- [ ] Implement query expansion/rewriting

### 2.4 Error handling & resilience
- [ ] Add circuit breaker for external API calls
- [ ] Implement retry logic with exponential backoff
- [ ] Add request validation middleware
- [ ] Improve error messages and codes

---

## Phase 3: Observability & Monitoring (Week 3)

### 3.1 Logging improvements
- [ ] Structured JSON logging
- [ ] Correlation IDs for request tracing
- [ ] Log levels per module

### 3.2 Metrics & tracing
- [ ] Add Prometheus metrics endpoint
- [ ] Integrate OpenTelemetry
- [ ] Add LangSmith/LangFuse integration
- [ ] Dashboard for latency, token usage, error rates

### 3.3 Health checks
- [ ] Deep health checks (DB, Chroma, OpenAI connectivity)
- [ ] Readiness/liveness probes for Kubernetes

---

## Phase 4: Security & Production Hardening (Week 4)

### 4.1 Authentication & Authorization
- [ ] Add API key authentication
- [ ] Add JWT token support
- [ ] Role-based access control (admin, user)

### 4.2 Rate limiting & quotas
- [ ] Per-user/IP rate limiting
- [ ] Token usage quotas
- [ ] Request size limits

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

### 6.1 Containerization
- [ ] Multi-stage Dockerfile
- [ ] Docker Compose for local dev
- [ ] Kubernetes manifests

### 6.2 CI/CD
- [ ] Automated releases
- [ ] Staging/production environments
- [ ] Database migrations

### 6.3 Documentation
- [ ] API reference (OpenAPI/Swagger)
- [ ] Architecture decision records (ADRs)
- [ ] Contribution guide
- [ ] Runbooks