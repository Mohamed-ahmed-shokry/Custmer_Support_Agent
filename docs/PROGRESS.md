# Phase Execution Progress: v0.55.0

## Phase Scope: Prospective Leasing CRM, Property Tours, Rental Applications & Applicant Screening Engine
Deliver an end-to-end Prospective Leasing CRM, Property Tour Scheduling, Rental Application Intake & Automated Applicant Screening Engine (`api/leasing_crm.py`) integrated with FastAPI, conversational RAG grounding, template macros, real-time webhooks, and the Streamlit operations hub.

## Acceptance Criteria Status

- [x] **AC1: Core Engine & SQLite Schema (`api/leasing_crm.py`)** ✅
  - Tables `leasing_prospects`, `property_tours`, and `rental_applications` with indexes, foreign keys, enums, seeds, prospect CRUD, tour lifecycle, application screening/decisioning, unit summaries, and funnel KPIs.
- [x] **AC2: Pydantic Validation Schemas & Webhook Events (`api/pydantic_models.py`, `api/db_utils.py`)** ✅
  - Request/response models for prospects, tours, applications, screening, decisions, summaries, metrics, and 6 `leasing.*` webhook events.
- [x] **AC3: FastAPI Endpoints & 1-Click Session Actions (`api/main.py`)** ✅
  - Endpoints for `/leasing/*`, `/units/{id}/leasing/summary`, and 1-click session actions.
- [x] **AC4: Conversational RAG Grounding & Prompt Macros (`api/tenant_context.py`)** ✅
  - Context block `[PROSPECTIVE LEASING, TOURS & APPLICATIONS]` and 5 macro variables (`{leasing_prospect_count}`, `{leasing_active_applications}`, `{leasing_next_tour_date}`, `{leasing_unit_demand_status}`, `{leasing_income_requirement}`).
- [ ] **AC5: Streamlit API Client Helpers (`app/api_utils.py`)**
  - Typed client API wrappers for all leasing CRM endpoints.
- [ ] **AC6: Streamlit UI Operations Board & Session Widget (`app/sidebar.py`)**
  - 3-tab `🏢 Leasing CRM & Applications` sidebar expander and 1-click session widget.
- [ ] **AC7: Automated Unit & Integration Tests (`tests/`)**
  - Full test coverage across engine, models, routes, RAG context, API client, and UI with >= 80% total coverage.
- [ ] **AC8: Version Bump & Documentation Updates**
  - Version bumped to `0.55.0` in `pyproject.toml` and `api/settings.py`; docs updated in `docs/API.md`, `README.md`, `ROADMAP.md`, and `docs/PROGRESS.md`.
- [ ] **AC9: 100% Green CI Parity & Remote Actions Pass**
  - Ruff, mypy, secret scan, pytest coverage, and remote GitHub Actions CI green.

## Micro-Task Execution Checklist

- [x] Task 1: Define v0.55.0 phase scope in `ROADMAP.md` and `docs/PROGRESS.md`.
- [x] Task 2: Implement `api/leasing_crm.py` (enums, schema, seeds, prospects, tours, applications, screening, decisioning, summaries, KPIs) with unit tests.
- [x] Task 3: Register `leasing.*` webhook events in `api/db_utils.py` and add Pydantic schemas in `api/pydantic_models.py` with tests.
- [x] Task 4: Implement FastAPI endpoints and 1-click session actions in `api/main.py` with route integration tests.
- [x] Task 5: Implement RAG prompt grounding and macro variables in `api/tenant_context.py` with tests.
- [ ] Task 6: Implement Streamlit client API helpers in `app/api_utils.py` with tests.
- [ ] Task 7: Implement Streamlit UI operations board and session widget in `app/sidebar.py` with UI tests.
- [ ] Task 8: Version bump to `0.55.0` and update documentation.
- [ ] Task 9: Final self-review, local CI-parity verification, remote CI green check, and Draft PR delivery.

## Decision Log
- **D1: Dedicated Leasing CRM Module (`api/leasing_crm.py`)**: Follows the modular architecture pattern of `api/security_deposits.py` and `api/preventative_maintenance.py` with self-initializing SQLite tables and foreign keys to `units`.
- **D2: Automated 3.0x Income-to-Rent & Credit Score Qualification**: Screening calculates `income_to_rent_ratio = round(monthly_income / target_rent, 2)` and recommends `approved` (>= 3.0x & credit >= 650 & background passed), `conditionally_approved` (>= 2.5x or credit 600-649), or `denied` otherwise.
- **D3: Relative UTC Dates in Seeds**: Use relative UTC dates (`+3 days`, `+14 days`) for seeded tours and target move-in dates so tests never flake as calendar dates advance.
- **D4: Automatic Prospect Funnel Stage Progression**: Scheduling a tour moves a prospect to `tour_scheduled`, completing a tour moves to `toured`, submitting an application moves to `applied`, and approving an application moves to `approved`.

## CI & Validation Log
- Baseline (`origin/main` @ `2232b41`):
  - `python -m ruff check api/ app/ tests/ scripts/` → exit 0 ✅
  - `python -m mypy api/ app/ scripts/` → exit 0 (46 source files) ✅
  - Remote GitHub Actions CI (`main`, run `45233881269`) → success ✅
