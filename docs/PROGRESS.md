# v0.35.0 Progress Record: Tenant Profiles, Property Unit Directory & Context Grounding Engine

**Phase Branch**: `phase/v0.35.0-tenant-context-property-directory`  
**Status**: 🚧 IN PROGRESS  
**Target Version**: 0.35.0  

---

## 1. Task Breakdown & Execution Status

- [x] **Task 1**: `ROADMAP.md` v0.35.0 plan specification and `docs/PROGRESS.md` initialization
- [ ] **Task 2**: Database schema & CRUD operations for `units` in `api/db_utils.py` + unit tests in `tests/test_db_utils.py`
- [ ] **Task 3**: Database schema & CRUD operations for `tenants` in `api/db_utils.py` + unit tests in `tests/test_db_utils.py`
- [ ] **Task 4**: Session tenant linking, migration, and support history queries in `api/db_utils.py` + unit tests in `tests/test_db_utils.py`
- [ ] **Task 5**: Core tenant context grounding engine and macro variable auto-resolution in `api/tenant_context.py` & `api/macros.py` + unit tests in `tests/test_tenant_context.py`
- [ ] **Task 6**: Pydantic request/response models for units, tenants, linking, and context in `api/pydantic_models.py` + unit tests in `tests/test_models.py`
- [ ] **Task 7**: FastAPI endpoints for property units (`/units*`) in `api/main.py` + route tests in `tests/test_api_routes.py`
- [ ] **Task 8**: FastAPI endpoints for tenants, session linking, tenant context, and history (`/tenants*`, `/sessions/{id}/link-tenant`, `/sessions/{id}/tenant-context`) in `api/main.py` + route tests in `tests/test_api_routes.py`
- [ ] **Task 9**: Streamlit client API helpers in `app/api_utils.py` + unit tests in `tests/test_app_api_utils.py`
- [ ] **Task 10**: Streamlit UI session tenant context card, tenant linking, and "🏢 Tenant & Property Directory" sidebar panel in `app/sidebar.py` + UI tests in `tests/test_app_ui.py`
- [ ] **Task 11**: Documentation updates (`docs/API.md`, `README.md`) and version bump to `0.35.0` (`pyproject.toml`, `api/settings.py`)
- [ ] **Task 12**: Final verification gate, self-review audit, progress record completion, and draft PR delivery

---

## 2. Acceptance Criteria Status

| # | Acceptance Criterion | Status | Evidence |
|---|----------------------|--------|----------|
| AC1 | `units` and `tenants` SQLite tables are created, seeded with defaults, supported with full CRUD and validation, and `session_labels` is migrated with `tenant_id` and `unit_id` columns | PENDING | `api/db_utils.py`, `tests/test_db_utils.py` |
| AC2 | `api/tenant_context.py` accurately generates structured RAG context blocks from tenant and unit records, and macro variable resolution automatically populates tenant details | PENDING | `api/tenant_context.py`, `tests/test_tenant_context.py` |
| AC3 | Pydantic schemas in `api/pydantic_models.py` validate unit creation, tenant management, session linking, and tenant context payloads | PENDING | `api/pydantic_models.py`, `tests/test_models.py` |
| AC4 | FastAPI endpoints `/units*`, `/tenants*`, `/sessions/{id}/link-tenant`, `/sessions/{id}/tenant-context`, and `/tenants/{id}/support-history` are wired and verified with complete HTTP status codes | PENDING | `api/main.py`, `tests/test_api_routes.py` |
| AC5 | Client helpers in `app/api_utils.py` provide typed methods with `X-API-Key` header forwarding and error handling | PENDING | `app/api_utils.py`, `tests/test_app_api_utils.py` |
| AC6 | Streamlit UI in `app/sidebar.py` provides the Tenant Context Card in session metadata and the "🏢 Tenant & Property Directory" management panel | PENDING | `app/sidebar.py`, `tests/test_app_ui.py` |
| AC7 | Documentation (`README.md`, `docs/API.md`, `ROADMAP.md`, `docs/PROGRESS.md`) and version (`0.35.0`) are updated and accurate | PENDING | `README.md`, `docs/API.md`, `pyproject.toml`, `api/settings.py` |
| AC8 | Full verification suite (`pytest` with >= 80% coverage, `ruff check`, `mypy`) passes with zero regressions | PENDING | `pytest`, `ruff check`, `mypy` |

---

## 3. Decision Log

- **Decision 1 (2026-10-14)**: Select **v0.35.0 — Tenant Profiles, Property Unit Directory & Context Grounding Engine** as the development phase.
  - *Context*: Baseline checks (`pytest`, `ruff`, `mypy`) are 100% green on `v0.34.0`. In prior phases, support chat sessions were anonymous, lacking persistent tenant identity, lease terms, or property unit context. Support agents had to manually query or re-enter tenant information, macros required manual parameter entry for `{customer_name}` and `{unit_id}`, and the RAG assistant lacked personal lease context for tenant questions (rent due, lease end, amenities, parking, gate codes).
  - *Alternatives considered*: Direct third-party property management API sync (requires enterprise credentials) or maintenance work orders dispatch (benefits directly from having tenant and unit entities first).
  - *Rationale*: Creating a local-first Property Unit Directory and Tenant Profile engine, linking sessions to tenants, and injecting verified tenant context into RAG prompts and canned macros delivers foundational domain value for property management customer care with zero external dependencies.
  - *Blast radius & Reversibility*: Additive SQLite tables (`units`, `tenants`), backward-compatible migration on `session_labels` (nullable `tenant_id` and `unit_id`), additive `/units` and `/tenants` routes, and optional tenant prompt grounding.

---

## 4. Validation Commands & Results

- **Baseline Check (v0.34.0)**:
  - `python -m ruff check api/ app/ tests/ scripts/` -> ✅ Passed (`All checks passed!`)
  - `python -m mypy api/ app/ scripts/` -> ✅ Passed (`Success: no issues found in 29 source files`)
  - `python -m pytest -q` -> ✅ Passed (`717 passed, 21 deselected, 93.26% coverage, fail_under=80%`)
