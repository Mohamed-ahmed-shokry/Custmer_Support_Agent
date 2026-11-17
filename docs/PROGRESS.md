# Phase Execution Progress: v0.52.0

## Phase Scope: Resident Subletting, Lease Assignment & Guest Room Occupancy Verification Engine
Complete resident subletting lifecycle, roommate replacement workflows, guest room occupancy tracking, short-term rental / Airbnb violation detection, administrative fee assessment to rent ledgers, conversational RAG grounding, and Streamlit management operations hub.

## Acceptance Criteria Status

- [x] **AC1: SQLite Database Tables & Schema Migration (`api/sublets.py`)** ✅
  - Tables `sublet_requests`, `sublet_occupants`, and `unauthorized_rental_alerts` with indexes, foreign keys to `units` and `tenants`, and default seed records.
- [x] **AC2: Pydantic Validation Schemas & Enums (`api/pydantic_models.py`)** ✅
  - Request/response schemas for sublet requests, approvals, occupants, unauthorized rental alerts, session actions, and summary KPIs with full field validations.
- [x] **AC3: FastAPI Endpoints & Webhook Dispatch (`api/main.py`, `api/db_utils.py`)** ✅
  - RESTful endpoints for sublets, occupants, alerts, metrics, unit/tenant summaries, and 1-click session actions `POST /sessions/{id}/submit-sublet-request` and `POST /sessions/{id}/report-unauthorized-rental`.
- [x] **AC4: Conversational RAG Grounding & Prompt Macros (`api/tenant_context.py`)** ✅
  - Context injection `[RESIDENT SUBLETTING, LEASE ASSIGNMENT & GUEST OCCUPANCY]` and auto-resolution of `{sublet_status}`, `{sublet_start_date}`, `{sublet_end_date}`, `{subtenant_name}`, `{sublet_fee}`, `{max_occupancy_limit}`, `{current_occupancy_count}`.
- [x] **AC5: Streamlit Client API Helpers (`app/api_utils.py`)** ✅
  - Typed client API wrappers with error handling, session header forwarding, and payload verification.
- [ ] **AC6: Streamlit UI Subletting Board & Session Actions (`app/sidebar.py`)**
  - 4-tab sublet management board (`Sublet Requests`, `Guest Registry & Occupants`, `Unauthorized Rental Alerts`, `Occupancy KPIs`) and 1-click resident profile subletting actions.
- [ ] **AC7: Automated Unit & Integration Tests (`tests/`)**
  - Test suites for database operations, models, FastAPI routes, RAG context, client utilities, and UI mocks.
- [ ] **AC8: Documentation Updates & Version Bump**
  - Endpoints documented in `docs/API.md`, feature highlights in `README.md`, version bump to `0.52.0` in `pyproject.toml` and `api/settings.py`.
- [ ] **AC9: 100% Green CI Parity & Remote Actions Pass**
  - All formatters, linters, type checks, secret scans, unit tests (coverage >= 80%), and remote CI runs green.

## Micro-Task Execution Checklist

- [x] Task 1: Document v0.52.0 scope, acceptance criteria, and checklist in `ROADMAP.md` and `docs/PROGRESS.md`.
- [x] Task 2: Implement `api/sublets.py` database schema, models, CRUD helpers, approval workflow, fee posting, occupant management, rental alerts, metrics, and seed data with unit tests in `tests/test_sublets.py`.
- [x] Task 3: Define Pydantic request/response schemas in `api/pydantic_models.py` and webhook events in `api/db_utils.py` with schema tests in `tests/test_models.py`.
- [x] Task 4: Implement FastAPI endpoints and 1-click session actions in `api/main.py` with route tests in `tests/test_sublet_routes.py`.
- [x] Task 5: Implement RAG prompt grounding and macro variable resolution in `api/tenant_context.py` with tests in `tests/test_tenant_context.py`.
- [x] Task 6: Implement Streamlit API client wrappers in `app/api_utils.py` with tests in `tests/test_app_api_utils.py`.
- [ ] Task 7: Implement Streamlit UI subletting board and session resident widget in `app/sidebar.py` with tests in `tests/test_app_ui.py`.
- [ ] Task 8: Version bump to `0.52.0` and documentation updates in `docs/API.md` and `README.md`.
- [ ] Task 9: Final local and remote CI verification, Draft PR delivery, and final delivery report.

## Decision Log
- **D1: Dedicated Subletting & Occupancy Module**: Follow established modular architectural pattern (`api/insurance.py`, `api/utilities.py`, `api/move_logistics.py`) creating a dedicated `api/sublets.py`.
- **D2: Standard Administrative Subletting Fee**: Property management reviews, background checks, and sublet lease addenda assess a standard $150.00 administrative fee posted directly to the resident's rent ledger (`billing_transactions`), matching property management operational best practice.
- **D3: Short-Term Rental Violation Workflow**: Unregistered Airbnb/VRBO listings pose significant security and regulatory risks. Unauthorized listings trigger dedicated alerts (`unauthorized_rental_alerts`) with investigative statuses and automated fine assessment options.
- **D4: Maximum Occupancy Limit Standard**: Default unit occupancy formula enforces standard municipal property guidelines: 2 persons per bedroom plus 1 additional occupant (e.g. 1BR = max 3, 2BR = max 5), tracking actual count of active tenants plus registered subtenants/long-term guests.
