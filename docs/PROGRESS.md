# Phase Execution Progress: v0.46.0

## Phase Scope: Smart Access Control, Key Fobs, Digital Mobile Keys, Intercom & Guest Passes Engine
Complete residential access credentials management, temporary visitor PIN pass generation, callbox/intercom directory, lost fob deactivation and replacement billing, conversational RAG grounding, and Streamlit management hub.

## Acceptance Criteria Status

- [x] **AC1: SQLite Database Tables & Schema Migration (`api/access_control.py`)**
  - Tables `access_credentials`, `guest_passes`, and `intercom_directory` bootstrapped with UUID/hex primary keys, foreign references to `units` and `tenants`, indexing on lookup keys, and pre-seeded default credentials and guest passes.
- [x] **AC2: Pydantic Validation Schemas & Enums (`api/pydantic_models.py`)**
  - Request/response schemas for credentials, guest passes, intercom entries, session actions, and summary KPIs with full field validations.
- [x] **AC3: FastAPI Endpoints & Webhook Dispatch (`api/main.py`, `api/db_utils.py`)**
  - RESTful endpoints for access credentials, guest passes, intercom directory, metrics, and 1-click session actions `POST /sessions/{id}/generate-guest-pass` and `POST /sessions/{id}/report-lost-fob`.
- [x] **AC4: Conversational RAG Grounding & Prompt Macros (`api/tenant_context.py`)**
  - Context injection `[RESIDENTIAL ACCESS CREDENTIALS & GUEST PASSES]` and auto-resolution of `{active_fob_count}`, `{primary_fob_number}`, `{guest_pass_code}`, `{guest_pass_expires}`, `{access_zones}`, `{intercom_code}`, `{fob_replacement_fee}`.
- [x] **AC5: Streamlit Client API Helpers (`app/api_utils.py`)**
  - Typed client API wrappers with error handling, session header forwarding, and payload verification.
- [x] **AC6: Streamlit UI Access Board & Session Actions (`app/sidebar.py`)**
  - 4-tab access management board (`Credentials & Fobs`, `Guest Passes`, `Intercom Directory`, `Access KPIs`) and 1-click resident profile guest pass & lost fob actions.
- [x] **AC7: Automated Unit & Integration Tests (`tests/`)**
  - Test suites for database operations, models, FastAPI routes, RAG context, client utilities, and UI mocks.
- [x] **AC8: Documentation Updates & Version Bump**
  - Endpoints documented in `docs/API.md`, feature highlights in `README.md`, version bump to `0.46.0` in `pyproject.toml` and `api/settings.py`.
- [x] **AC9: 100% Green CI Parity & Remote Actions Pass**
  - All formatters, linters, type checks, secret scans, unit tests (coverage >= 80%), and remote CI runs green.

## Micro-Task Execution Checklist

- [x] Task 1: Document v0.46.0 scope, acceptance criteria, and checklist in `ROADMAP.md` and `docs/PROGRESS.md`.
- [x] Task 2: Implement `api/access_control.py` database schema, models, CRUD helpers, metrics, and seed data with unit tests in `tests/test_access_control.py`.
- [x] Task 3: Define Pydantic request/response schemas in `api/pydantic_models.py` and webhook events in `api/db_utils.py` with schema tests in `tests/test_models.py`.
- [x] Task 4: Implement FastAPI endpoints and 1-click session actions in `api/main.py` with route tests in `tests/test_access_control_routes.py`.
- [x] Task 5: Implement RAG prompt grounding and macro variable resolution in `api/tenant_context.py` with tests in `tests/test_tenant_context.py`.
- [x] Task 6: Implement Streamlit API client wrappers in `app/api_utils.py` with tests in `tests/test_app_api_utils.py`.
- [x] Task 7: Implement Streamlit UI access board and session resident widget in `app/sidebar.py` with tests in `tests/test_app_ui.py`.
- [x] Task 8: Version bump to `0.46.0` and documentation updates in `docs/API.md` and `README.md`.
- [x] Task 9: Final local and remote CI verification, Draft PR delivery, and final delivery report.

## Decision Log
- **D1: Integrated Fob & Guest Pass Storage**: Followed existing modular pattern established in `api/parking.py`, `api/amenities.py`, and `api/pets.py` using dedicated `api/access_control.py`.
- **D2: Security Standard for Guest Passes**: Formatted guest pass access codes as 6-digit cryptographic-quality numeric PINs with explicit expiry and multi-zone permission arrays (`main_lobby`, `elevator`, `unit_door`, `garage`, `amenities`).
- **D3: Lost Fob Replacement Fee**: Standardized replacement fee at $50 per lost fob, automatically emitting webhook `access.fob_reported_lost` and integrating with the resident's unit billing ledger.
