# Phase Execution Progress: v0.57.0

## Phase Scope: Eviction Compliance, Legal Notices, Court Filings & Payment Plan Workouts Engine
Deliver an end-to-end Eviction Compliance, Statutory Legal Notices, Court Filing Milestones & Resident Payment Plan Workouts Engine (`api/evictions.py`) integrated with FastAPI, conversational RAG grounding, template macros, real-time webhooks, and the Streamlit operations hub.

## Acceptance Criteria Status

- [x] **AC1: Core Engine & SQLite Schema (`api/evictions.py`)** ✅
  - Tables `eviction_cases` and `payment_plans` with indexes, foreign keys, enums, seeds, CRUD, court filing, case closure, payment plan workouts, summaries, and KPIs.
- [ ] **AC2: Pydantic Validation Schemas & Webhook Events (`api/pydantic_models.py`, `api/db_utils.py`)**
  - Request/response models for eviction cases, court filings, closures, payment plans, installments, summaries, metrics, and 6 `eviction.*` webhook events.
- [ ] **AC3: FastAPI Endpoints & 1-Click Session Actions (`api/main.py`)**
  - Endpoints for `/evictions/*`, `/tenants/{id}/evictions/summary`, `/units/{id}/evictions/summary`, and 1-click session actions.
- [ ] **AC4: Conversational RAG Grounding & Prompt Macros (`api/tenant_context.py`)**
  - Context block `[EVICTION COMPLIANCE, LEGAL NOTICES & PAYMENT PLANS]` and 5 macro variables (`{eviction_case_status}`, `{eviction_cure_deadline}`, `{eviction_arrears_amount}`, `{payment_plan_status}`, `{payment_plan_next_due}`).
- [ ] **AC5: Streamlit API Client Helpers (`app/api_utils.py`)**
  - Typed client API wrappers for all eviction compliance and payment plan endpoints.
- [ ] **AC6: Streamlit UI Operations Board & Session Widget (`app/sidebar.py`)**
  - 3-tab `⚖️ Evictions & Payment Plans` sidebar expander and 1-click session delinquency/workout widget.
- [ ] **AC7: Automated Unit & Integration Tests (`tests/`)**
  - Full test coverage across engine, models, routes, RAG context, API client, and UI with >= 80% total coverage.
- [ ] **AC8: Version Bump & Documentation Updates**
  - Version bumped to `0.57.0` in `pyproject.toml` and `api/settings.py`; docs updated in `docs/API.md`, `README.md`, `ROADMAP.md`, and `docs/PROGRESS.md`.
- [ ] **AC9: 100% Green CI Parity & Remote Actions Pass**
  - Ruff, mypy, secret scan, pytest coverage, and remote GitHub Actions CI green.

## Micro-Task Execution Checklist

- [x] Task 1: Define v0.57.0 phase scope in `ROADMAP.md` and `docs/PROGRESS.md`.
- [x] Task 2: Implement `api/evictions.py` (enums, schema, seeds, cases, court filings, closures, payment plans, summaries, KPIs) with unit tests.
- [ ] Task 3: Register `eviction.*` webhook events in `api/db_utils.py` and add Pydantic schemas in `api/pydantic_models.py` with tests.
- [ ] Task 4: Implement FastAPI endpoints and 1-click session actions in `api/main.py` with route integration tests.
- [ ] Task 5: Implement RAG prompt grounding and macro variables in `api/tenant_context.py` with tests.
- [ ] Task 6: Implement Streamlit client API helpers in `app/api_utils.py` with tests.
- [ ] Task 7: Implement Streamlit UI operations board and session widget in `app/sidebar.py` with UI tests.
- [ ] Task 8: Version bump to `0.57.0` and update documentation.
- [ ] Task 9: Final self-review, local CI-parity verification, remote CI green check, and Draft PR delivery.

## Decision Log
- **D1: Dedicated Evictions & Payment Plans Module (`api/evictions.py`)**: Follows the modular architecture pattern of `api/owner_portal.py` and `api/leasing_crm.py` with self-initializing SQLite tables and foreign keys to `units` and `tenants`.
- **D2: Auto-Cure on Payment Plan Completion**: When `record_plan_installment` brings `amount_paid >= total_arrears` (or `installments_paid >= installment_count`), the plan transitions to `completed` and any linked `eviction_cases` record automatically transitions to `cured_dismissed`.
- **D3: Relative UTC Dates in Seeds**: Use relative UTC dates (`+5 days`, `+10 days`) for seeded cure deadlines and installment due dates so tests never flake across calendar dates.
- **D4: Statutory Cure Deadline Default**: Default `cure_deadline_date` to `notice_served_date + 5 days` when omitted, while allowing explicit overrides per jurisdiction.

## CI & Validation Log
- Baseline (`origin/main` @ `36c833b`):
  - `python -m ruff check api/ app/ tests/ scripts/` → exit 0 ✅
  - `python -m mypy api/ app/ scripts/` → exit 0 (48 source files) ✅
  - Remote GitHub Actions CI (`main`, run `45717019383`) → success ✅
