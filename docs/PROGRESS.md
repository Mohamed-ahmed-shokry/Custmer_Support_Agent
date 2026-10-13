# v0.34.0 Progress Record: Knowledge Base Gap Detection, FAQ Article Drafting & Self-Service Deflection Engine

**Phase Branch**: `phase/v0.34.0-knowledge-gaps-article-studio`  
**Status**: 🚧 IN PROGRESS  
**Target Version**: 0.34.0  

---

## 1. Task Breakdown & Execution Status

- [x] **Task 1**: `ROADMAP.md` v0.34.0 plan specification and `docs/PROGRESS.md` initialization
- [x] **Task 2**: Database schema & CRUD operations for `knowledge_gaps` in `api/db_utils.py` + unit tests in `tests/test_db_utils.py`
- [x] **Task 3**: Database schema & CRUD operations for `knowledge_articles` in `api/db_utils.py` + unit tests in `tests/test_db_utils.py`
- [x] **Task 4**: Core knowledge gap detection, session scanner, and webhook alerts in `api/knowledge_base.py` + unit tests in `tests/test_knowledge_base.py`
- [x] **Task 5**: Session-to-KB Markdown article synthesis, RAG publishing, and coverage analytics in `api/knowledge_base.py` + unit tests in `tests/test_knowledge_base.py`
- [x] **Task 6**: Pydantic request/response models for knowledge gaps, articles, publishing, and analytics in `api/pydantic_models.py` + unit tests in `tests/test_models.py`
- [x] **Task 7**: FastAPI endpoints for knowledge gaps (`/knowledge/gaps*`) in `api/main.py` + route tests in `tests/test_api_routes.py`
- [x] **Task 8**: FastAPI endpoints for knowledge articles, session drafting, publishing, and analytics (`/knowledge/articles*`, `/sessions/{id}/draft-article`, `/knowledge/analytics`) in `api/main.py` + route tests in `tests/test_api_routes.py`
- [ ] **Task 9**: Streamlit client API helpers in `app/api_utils.py` + unit tests in `tests/test_app_api_utils.py`
- [ ] **Task 10**: Streamlit UI session KB drafting button and "📚 Knowledge Gaps & Article Studio" sidebar panel in `app/sidebar.py` + UI tests in `tests/test_app_ui.py`
- [ ] **Task 11**: Documentation updates (`docs/API.md`, `README.md`) and version bump to `0.34.0` (`pyproject.toml`, `api/settings.py`)
- [ ] **Task 12**: Final verification gate, self-review audit, progress record completion, and draft PR delivery

---

## 2. Acceptance Criteria Status

| # | Acceptance Criterion | Status | Evidence |
|---|----------------------|--------|----------|
| AC1 | `knowledge_gaps` and `knowledge_articles` SQLite tables are created and support full CRUD, recurring query deduplication (`normalized_query` frequency incrementing), and validation | VERIFIED | `api/db_utils.py`, `tests/test_db_utils.py` (86 passed) |
| AC2 | `api/knowledge_base.py` accurately detects unanswered/fallback responses, scans escalated/low-CSAT sessions for gaps, synthesizes structured Markdown KB drafts from sessions, publishes articles into `document_store`/`document_sources` (resolving linked gaps), and dispatches `knowledge.gap_detected` and `knowledge.article_published` webhooks | VERIFIED | `api/knowledge_base.py`, `tests/test_knowledge_base.py` (6 passed) |
| AC3 | Pydantic schemas in `api/pydantic_models.py` validate all knowledge gap, article drafting, publishing, and analytics payloads | VERIFIED | `api/pydantic_models.py`, `tests/test_models.py` (47 passed) |
| AC4 | FastAPI endpoints `/knowledge/gaps`, `/knowledge/gaps/scan`, `/knowledge/gaps/{id}`, `/knowledge/articles`, `/knowledge/articles/{id}`, `/knowledge/articles/{id}/publish`, `/sessions/{id}/draft-article`, and `/knowledge/analytics` are wired and verified | VERIFIED | `api/main.py`, `tests/test_api_routes.py` (5 passed) |
| AC5 | Client helpers in `app/api_utils.py` provide typed methods with `X-API-Key` header forwarding and error handling | PENDING | `app/api_utils.py`, `tests/test_app_api_utils.py` |
| AC6 | Streamlit UI in `app/sidebar.py` provides 1-click session KB article drafting and the "📚 Knowledge Gaps & Article Studio" management panel | PENDING | `app/sidebar.py`, `tests/test_app_ui.py` |
| AC7 | Documentation (`README.md`, `docs/API.md`, `ROADMAP.md`, `docs/PROGRESS.md`) and version (`0.34.0`) are updated and accurate | PENDING | `README.md`, `docs/API.md`, `pyproject.toml`, `api/settings.py` |
| AC8 | Full verification suite (`pytest` with >= 80% coverage, `ruff check`, `mypy`) passes with zero regressions | PENDING | `pytest`, `ruff check`, `mypy` |

---

## 3. Decision Log

- **Decision 1 (2026-10-13)**: Select **v0.34.0 — Knowledge Base Gap Detection, FAQ Article Drafting & Self-Service Deflection Engine** as the development phase.
  - *Context*: Baseline checks (`pytest`, `ruff`, `mypy`) are 100% green on `v0.33.0`. Previous phases built the RAG document store (`v0.6`–`v0.26`) and the customer support operational helpdesk (`v0.27`–`v0.33`: summarization, webhooks, macros, SLA triage, agent routing, and multi-criteria CSAT). However, there was no closed-loop mechanism connecting support escalations, unanswered tenant questions, and low-CSAT conversations back into the RAG knowledge base.
  - *Alternatives considered*: External helpdesk CRM sync (requires third-party API credentials) or standalone RBAC auth overhaul (high blast radius across existing keyless routes).
  - *Rationale*: Closing the loop between support operations and the RAG corpus—detecting knowledge gaps from unanswered/low-CSAT/escalated sessions, drafting structured Markdown FAQ articles from resolved conversations, and publishing them directly into `document_store`/`document_sources` + Chroma—delivers high product value, zero external dependencies, and complete end-to-end integration across DB, API, client SDK, and Streamlit UI.
  - *Blast radius & Reversibility*: Additive SQLite tables (`knowledge_gaps`, `knowledge_articles`), dedicated `api/knowledge_base.py` domain module, and additive `/knowledge/*` + `/sessions/{id}/draft-article` routes.

- **Decision 2 (2026-10-13)**: Make KB article publishing resilient to offline/keyless environments during Chroma indexing.
  - *Context*: Publishing a KB article writes the Markdown document to `document_store` and `document_sources` and indexes chunks into Chroma. In CI or local environments without OpenAI API keys, live embedding calls in Chroma may fail unless handled gracefully.
  - *Rationale*: Persist `document_store` and `document_sources` deterministically first, attempt Chroma chunk indexing via `reindex_chunks_in_chroma`, and catch embedding provider errors gracefully (recording `indexed_in_vectorstore: bool` in the publish response) so publishing works 100% end-to-end both with and without external OpenAI credentials.

---

## 4. Validation Commands & Results

- **Baseline Check (v0.33.0)**:
  - `python -m ruff check api/ app/ tests/ scripts/` -> ✅ Passed (`All checks passed!`)
  - `python -m mypy api/ app/ scripts/` -> ✅ Passed (`Success: no issues found in 28 source files`)
  - `python -m pytest -q` -> ✅ Passed (`695 passed, 21 deselected, 94.14% coverage, fail_under=80%`)
