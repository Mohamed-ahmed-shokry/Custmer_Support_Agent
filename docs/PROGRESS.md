# v0.36.0 Progress Record: Maintenance Work Orders, Service Requests & Resident Dispatch Engine

**Phase Branch**: `phase/v0.36.0-maintenance-work-orders-dispatch`  
**Status**: 🚧 IN PROGRESS  
**Target Version**: 0.36.0  

---

## 1. Task Breakdown & Execution Status

- [x] **Task 1**: `ROADMAP.md` v0.36.0 plan specification and `docs/PROGRESS.md` initialization
- [x] **Task 2**: Database schema, table creation, default seed data, and CRUD operations for `work_orders` in `api/db_utils.py` + unit tests in `tests/test_db_utils.py`
- [x] **Task 3**: Context grounding engine integration for open maintenance work orders in `api/tenant_context.py` + unit tests in `tests/test_tenant_context.py`
- [ ] **Task 4**: Pydantic request/response schemas in `api/pydantic_models.py` + unit tests in `tests/test_models.py`
- [ ] **Task 5**: FastAPI endpoints for work orders, metrics, and session conversion in `api/main.py` + route tests in `tests/test_api_routes.py`
- [ ] **Task 6**: Streamlit client API helpers in `app/api_utils.py` + unit tests in `tests/test_app_api_utils.py`
- [ ] **Task 7**: Streamlit UI components in `app/sidebar.py` (session work order conversion & "🛠️ Maintenance & Work Orders" board) + UI tests in `tests/test_app_ui.py`
- [ ] **Task 8**: Documentation updates (`docs/API.md`, `README.md`) and version bump to `0.36.0` (`pyproject.toml`, `api/settings.py`)
- [ ] **Task 9**: Final verification gate (`pytest` >= 80% coverage, `ruff check`, `mypy`), progress record completion, and draft PR delivery

---

## 2. Acceptance Criteria Status

| # | Acceptance Criterion | Status | Evidence |
|---|----------------------|--------|----------|
| AC1 | `work_orders` SQLite table is created, seeded with defaults, and supported with CRUD, category/priority/status filters, and summary metrics in `api/db_utils.py` | PASSED | `api/db_utils.py`, `tests/test_db_utils.py` |
| AC2 | `api/tenant_context.py` augments grounding prompt context with active maintenance work orders for the linked session/tenant/unit | PASSED | `api/tenant_context.py`, `tests/test_tenant_context.py` |
| AC3 | Webhook events `work_order.created`, `work_order.emergency_escalated`, and `work_order.status_changed` trigger correctly on lifecycle transitions | PENDING | `api/webhooks.py`, `tests/test_webhooks.py` |
| AC4 | Pydantic schemas in `api/pydantic_models.py` validate work order creation, update, filtering, metrics, and session conversion | PENDING | `api/pydantic_models.py`, `tests/test_models.py` |
| AC5 | FastAPI endpoints `/work-orders*`, `/sessions/{id}/create-work-order`, and `/units/{id}/work-orders` are wired and covered with tests | PENDING | `api/main.py`, `tests/test_api_routes.py` |
| AC6 | Client helpers in `app/api_utils.py` provide typed methods with `X-API-Key` header forwarding and error handling | PENDING | `app/api_utils.py`, `tests/test_app_api_utils.py` |
| AC7 | Streamlit UI in `app/sidebar.py` provides 1-click work order creation from the resident session card and the "🛠️ Maintenance & Work Orders" board | PENDING | `app/sidebar.py`, `tests/test_app_ui.py` |
| AC8 | Documentation (`README.md`, `docs/API.md`, `ROADMAP.md`, `docs/PROGRESS.md`) and version (`0.36.0`) are updated | PENDING | `README.md`, `docs/API.md`, `pyproject.toml`, `api/settings.py` |
| AC9 | Full verification suite (`pytest` with >= 80% coverage, `ruff check`, `mypy`) passes with zero regressions | PENDING | `pytest`, `ruff check`, `mypy` |

---

## 3. Decision Log

- **Decision 1 (2026-10-15)**: Select **v0.36.0 — Maintenance Work Orders, Service Requests & Resident Dispatch Engine** as the development phase.
  - *Context*: In v0.35.0, resident profiles and property unit directories were introduced, enabling session linking and verified lease context grounding. However, maintenance repair workflows—the most frequent and urgent category of property management customer inquiries—cannot currently be tracked, dispatched, or queried via conversational RAG.
  - *Alternatives considered*: Document lease upload / PDF vector ingestion (informational only; does not resolve operational maintenance requests) or external PMS webhook sync (requires external credentials/mock APIs).
  - *Rationale*: Creating a local-first maintenance work order and dispatch system directly connected to units, tenants, and sessions bridges conversational support and physical property operations with zero external dependencies.
  - *Blast radius & Reversibility*: Additive SQLite table `work_orders`, non-breaking addition to prompt context blocks, additive endpoints `/work-orders` and `/sessions/{id}/create-work-order`.

---

## 4. Validation Commands & Results

- **Baseline Check (v0.35.0)**:
  - `python -m ruff check api/ app/ tests/ scripts/` -> ✅ Passed (`All checks passed!`)
  - `python -m mypy api/ app/ scripts/` -> ✅ Passed (`Success: no issues found in 30 source files`)
  - `python -m pytest -q` -> ✅ Passed (`753 passed, 21 deselected, 93.28% coverage, fail_under=80%`)
