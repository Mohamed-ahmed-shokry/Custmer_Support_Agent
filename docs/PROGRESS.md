# v0.39.0 Progress Record: Resident Move-In/Move-Out Inspections, Turnover Punchlists & Security Deposit Accounting Engine

**Phase Branch**: `phase/v0.39.0-move-in-out-inspections`  
**Status**: ⏳ IN PROGRESS  
**Target Version**: 0.39.0  

---

## 1. Task Breakdown & Execution Status

- [ ] **Task 1**: `ROADMAP.md` v0.39.0 plan specification and `docs/PROGRESS.md` initialization
- [ ] **Task 2**: Database schema, table creation, default seed data, and CRUD operations for `inspections` in `api/db_utils.py` + unit tests in `tests/test_db_utils.py`
- [ ] **Task 3**: Inspection completion, deposit deduction accounting, and punchlist-to-work-order conversion in `api/db_utils.py` + unit tests in `tests/test_db_utils.py`
- [ ] **Task 4**: Inspection report Markdown synthesis and RAG document publishing in `api/inspections.py` + unit tests in `tests/test_inspections.py`
- [ ] **Task 5**: Context grounding engine integration for inspections in `api/tenant_context.py` + unit tests in `tests/test_tenant_context.py`
- [ ] **Task 6**: Pydantic request/response schemas in `api/pydantic_models.py` + unit tests in `tests/test_models.py`
- [ ] **Task 7**: FastAPI endpoints for inspections, completion, work order dispatch, and session linking in `api/main.py` + route tests in `tests/test_api_routes.py`
- [ ] **Task 8**: Streamlit client API helpers in `app/api_utils.py` + unit tests in `tests/test_app_api_utils.py`
- [ ] **Task 9**: Streamlit UI components in `app/sidebar.py` (session inspection widget & "📋 Move-In/Out & Inspections" panel) + UI tests in `tests/test_app_ui.py`
- [ ] **Task 10**: Documentation updates (`docs/API.md`, `README.md`) and version bump to `0.39.0` (`pyproject.toml`, `api/settings.py`)
- [ ] **Task 11**: Final verification gate (`pytest` >= 80% coverage, `ruff check`, `mypy`), progress record completion, and draft PR delivery

---

## 2. Acceptance Criteria Status

| # | Acceptance Criterion | Status | Evidence |
|---|----------------------|--------|----------|
| AC1 | `inspections` SQLite table is created, pre-seeded with defaults, and supported with full CRUD, filtering, completion, and portfolio metrics in `api/db_utils.py` | ⏳ PENDING | Pending Task 2 |
| AC2 | `complete_inspection()` calculates total itemized deposit deductions, net deposit refund, and records completion timestamp | ⏳ PENDING | Pending Task 3 |
| AC3 | `convert_inspection_item_to_work_order()` converts an inspection deficiency item into an active maintenance work order in `work_orders` | ⏳ PENDING | Pending Task 3 |
| AC4 | `api/inspections.py` synthesizes structured Markdown inspection condition & deposit reports and publishes them into `document_store` and Chroma | ⏳ PENDING | Pending Task 4 |
| AC5 | `api/tenant_context.py` augments grounding prompt context with `[RESIDENT INSPECTIONS, MOVE-IN/OUT & DEPOSIT SETTLEMENT]` and auto-resolves inspection macro variables | ⏳ PENDING | Pending Task 5 |
| AC6 | Webhook events `inspection.scheduled`, `inspection.completed`, `inspection.deposit_deductions_assessed`, and `inspection.keys_returned` trigger correctly on inspection events | ⏳ PENDING | Pending Task 2 & 3 |
| AC7 | Pydantic schemas in `api/pydantic_models.py` validate inspection creation, items, updates, completion, and summary responses | ⏳ PENDING | Pending Task 6 |
| AC8 | FastAPI endpoints `/inspections/*`, `/sessions/{id}/create-inspection`, `/tenants/{id}/inspections`, and `/units/{id}/inspections` are wired and tested | ⏳ PENDING | Pending Task 7 |
| AC9 | Client helpers in `app/api_utils.py` provide typed methods with `X-API-Key` forwarding and resilient error handling | ⏳ PENDING | Pending Task 8 |
| AC10 | Streamlit UI in `app/sidebar.py` provides the 1-click inspection scheduling widget in session card and the "📋 Move-In/Out & Inspections" management panel | ⏳ PENDING | Pending Task 9 |
| AC11 | Documentation (`README.md`, `docs/API.md`, `ROADMAP.md`, `docs/PROGRESS.md`) and version bump to `0.39.0` (`pyproject.toml`, `api/settings.py`) are complete | ⏳ PENDING | Pending Task 10 |
| AC12 | All local CI-parity checks and remote CI workflow runs pass 100% | ⏳ PENDING | Pending Task 11 |

---

## 3. Decision Log

- **Decision 1 (2026-10-18)**: Select **v0.39.0 — Resident Move-In/Move-Out Inspections, Turnover Punchlists & Security Deposit Accounting Engine** as the development phase.
  - *Context*: Following tenant context (v0.35.0), maintenance dispatch (v0.36.0), resident billing (v0.37.0), and lease renewals (v0.38.0), move-in and move-out inspections along with punchlist repairs, key tracking, and security deposit deductions represent the final essential pillar of property management resident operations.
  - *Alternatives considered*: External IoT smart lock integration (requires external hardware APIs) or court eviction workflows (high legal liability).
  - *Rationale*: A local-first inspection and punchlist turnover engine (`inspections`) with itemized condition checklists, automated deposit deduction/refund calculation, direct conversion of deficiencies into maintenance work orders (`work_orders`), RAG context grounding, and condition report publishing to Chroma vector storage solves the complete resident turnover cycle cleanly and deterministically.
  - *Blast radius & Reversibility*: Additive SQLite table `inspections`, additive webhook events (`inspection.*`), additive context block `[RESIDENT INSPECTIONS, MOVE-IN/OUT & DEPOSIT SETTLEMENT]`, new `api/inspections.py` module, and isolated `/inspections/*` endpoints.

---

## 4. Validation Commands & Results

- Baseline verification passed: `ruff check` (0 errors), `mypy` (0 errors), `pytest` (801 passed, 92.54% coverage).
