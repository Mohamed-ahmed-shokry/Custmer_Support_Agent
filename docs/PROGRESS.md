# Phase Execution Progress: v0.47.0

## Phase Scope: Resident Incident Reports, Community Violations, Security Patrols & Notice-to-Cure Engine
Complete residential incident reporting, community violation notices, notice-to-cure statutory deadlines, fine assessment into unit billing ledgers, resident appeal workflow, conversational RAG grounding, and Streamlit management hub.

## Acceptance Criteria Status

- [x] **AC1: SQLite Database Tables & Schema Migration (`api/incidents.py`)**
  - Tables `community_incidents`, `violation_notices`, and `violation_appeals` bootstrapped with UUID primary keys, foreign references to `units` and `tenants`, indexing on lookup keys, and pre-seeded default incident and notice.
- [x] **AC2: Pydantic Validation Schemas & Enums (`api/pydantic_models.py`)**
  - Request/response schemas for incidents, notices, appeals, session actions, and summary KPIs with full field validations.
- [x] **AC3: FastAPI Endpoints & Webhook Dispatch (`api/main.py`, `api/db_utils.py`)**
  - RESTful endpoints for incidents, notices, appeals, metrics, and 1-click session actions `POST /sessions/{id}/issue-violation-notice` and `POST /sessions/{id}/submit-violation-appeal`.
- [x] **AC4: Conversational RAG Grounding & Prompt Macros (`api/tenant_context.py`)**
  - Context injection `[RESIDENTIAL INCIDENTS & COMMUNITY VIOLATIONS]` and auto-resolution of `{active_violations_count}`, `{primary_violation_type}`, `{notice_type}`, `{cure_deadline}`, `{fine_amount}`, `{appeal_status}`.
- [x] **AC5: Streamlit Client API Helpers (`app/api_utils.py`)**
  - Typed client API wrappers with error handling, session header forwarding, and payload verification.
- [x] **AC6: Streamlit UI Incidents Board & Session Actions (`app/sidebar.py`)**
  - 4-tab incident management board (`Incidents Directory`, `Violation Notices`, `Resident Appeals`, `Compliance KPIs`) and 1-click resident profile notice & appeal actions.
- [x] **AC7: Automated Unit & Integration Tests (`tests/`)**
  - Test suites for database operations, models, FastAPI routes, RAG context, client utilities, and UI mocks.
- [x] **AC8: Documentation Updates & Version Bump**
  - Endpoints documented in `docs/API.md`, feature highlights in `README.md`, version bump to `0.47.0` in `pyproject.toml` and `api/settings.py`.
- [x] **AC9: 100% Green CI Parity & Remote Actions Pass**
  - All formatters, linters, type checks, secret scans, unit tests (coverage >= 80%), and remote CI runs green.

## Micro-Task Execution Checklist

- [x] Task 1: Document v0.47.0 scope, acceptance criteria, and checklist in `ROADMAP.md` and `docs/PROGRESS.md`.
- [x] Task 2: Implement `api/incidents.py` database schema, models, CRUD helpers, metrics, and seed data with unit tests in `tests/test_incidents.py`.
- [x] Task 3: Define Pydantic request/response schemas in `api/pydantic_models.py` and webhook events in `api/db_utils.py` with schema tests in `tests/test_models.py`.
- [x] Task 4: Implement FastAPI endpoints and 1-click session actions in `api/main.py` with route tests in `tests/test_incident_routes.py`.
- [x] Task 5: Implement RAG prompt grounding and macro variable resolution in `api/tenant_context.py` with tests in `tests/test_tenant_context.py`.
- [x] Task 6: Implement Streamlit API client wrappers in `app/api_utils.py` with tests in `tests/test_app_api_utils.py`.
- [x] Task 7: Implement Streamlit UI incident board and session resident widget in `app/sidebar.py` with tests in `tests/test_app_ui.py`.
- [x] Task 8: Version bump to `0.47.0` and documentation updates in `docs/API.md` and `README.md`.
- [x] Task 9: Final local and remote CI verification, Draft PR delivery, and final delivery report.

## Decision Log
- **D1: Dedicated Incident and Violation Storage**: Followed existing modular pattern established in `api/access_control.py`, `api/parking.py`, and `api/pets.py` using dedicated `api/incidents.py`.
- **D2: Notice to Cure Timelines**: Standardized cure notice windows (e.g. 3-day notice to quit/cure, 7-day cure window, 14-day appeal window) calculated relative to notice issuance.
- **D3: Direct Ledger Integration**: When fine notices are finalized, charges are directly recorded into `tenant_ledger` in `api/billing.py` with reason code `violation_fine`.
