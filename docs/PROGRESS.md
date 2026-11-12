# Phase Execution Progress: v0.50.0

## Phase Scope: Resident Utility Submetering, Energy & Water Consumption & Billing Splits Engine
Complete utility submetering, meter reading telemetry, consumption anomaly and water leak detection, ratio utility billing (RUBS), conversational RAG grounding, and Streamlit management operations hub.

## Acceptance Criteria Status

- [x] **AC1: SQLite Database Tables & Schema Migration (`api/utilities.py`)** ✅
  - Tables `utility_meters`, `utility_readings`, `utility_invoices`, and `utility_disputes` with indexes, foreign keys to `units` and `tenants`, and seed records.
- [ ] **AC2: Pydantic Validation Schemas & Enums (`api/pydantic_models.py`)**
  - Request/response schemas for meters, readings, invoices, disputes, session actions, and summary KPIs with full field validations.
- [ ] **AC3: FastAPI Endpoints & Webhook Dispatch (`api/main.py`, `api/db_utils.py`)**
  - RESTful endpoints for utility submetering, readings, invoices, metrics, unit/tenant summaries, and 1-click session actions `POST /sessions/{id}/record-meter-reading` and `POST /sessions/{id}/report-utility-leak`.
- [ ] **AC4: Conversational RAG Grounding & Prompt Macros (`api/tenant_context.py`)**
  - Context injection `[RESIDENT UTILITY METERS, USAGE & SUBMETERING]` and auto-resolution of `{primary_meter_status}`, `{latest_electric_kwh}`, `{latest_water_gallons}`, `{latest_utility_total}`, `{utility_anomaly_alert}`, `{utility_invoice_status}`.
- [ ] **AC5: Streamlit Client API Helpers (`app/api_utils.py`)**
  - Typed client API wrappers with error handling, session header forwarding, and payload verification.
- [ ] **AC6: Streamlit UI Utility Board & Session Actions (`app/sidebar.py`)**
  - 4-tab utility management board (`Meter Readings & Telemetry`, `Monthly Statements & RUBS`, `Consumption Alerts & Anomaly Monitor`, `Submetering KPIs`) and 1-click resident profile utility actions.
- [ ] **AC7: Automated Unit & Integration Tests (`tests/`)**
  - Test suites for database operations, models, FastAPI routes, RAG context, client utilities, and UI mocks.
- [ ] **AC8: Documentation Updates & Version Bump**
  - Endpoints documented in `docs/API.md`, feature highlights in `README.md`, version bump to `0.50.0` in `pyproject.toml` and `api/settings.py`.
- [ ] **AC9: 100% Green CI Parity & Remote Actions Pass**
  - All formatters, linters, type checks, secret scans, unit tests (coverage >= 80%), and remote CI runs green.

## Micro-Task Execution Checklist

- [x] Task 1: Document v0.50.0 scope, acceptance criteria, and checklist in `ROADMAP.md` and `docs/PROGRESS.md`.
- [x] Task 2: Implement `api/utilities.py` database schema, models, CRUD helpers, anomaly detection, metrics, and seed data with unit tests in `tests/test_utilities.py`.
- [ ] Task 3: Define Pydantic request/response schemas in `api/pydantic_models.py` and webhook events in `api/db_utils.py` with schema tests in `tests/test_models.py`.
- [ ] Task 4: Implement FastAPI endpoints and 1-click session actions in `api/main.py` with route tests in `tests/test_utility_routes.py`.
- [ ] Task 5: Implement RAG prompt grounding and macro variable resolution in `api/tenant_context.py` with tests in `tests/test_tenant_context.py`.
- [ ] Task 6: Implement Streamlit API client wrappers in `app/api_utils.py` with tests in `tests/test_app_api_utils.py`.
- [ ] Task 7: Implement Streamlit UI utility board and session resident widget in `app/sidebar.py` with tests in `tests/test_app_ui.py`.
- [ ] Task 8: Version bump to `0.50.0` and documentation updates in `docs/API.md` and `README.md`.
- [ ] Task 9: Final local and remote CI verification, Draft PR delivery, and final delivery report.

## Decision Log
- **D1: Dedicated Utilities & Submetering Module**: Followed established modular pattern (`api/announcements.py`, `api/incidents.py`, `api/move_logistics.py`) creating a dedicated `api/utilities.py`.
- **D2: Multi-Utility Submeter Hierarchy**: Support electricity (`kWh`), water (`gallons`), gas (`therms`), sewer, and trash meters with per-meter serial numbers and calibration dates.
- **D3: Rolling Anomaly Baseline**: Automatically flag any consumption reading exceeding prior average by >50% as a potential leak or equipment malfunction, enabling proactive resident alerts and 1-click work-order dispatch.
