# Phase Execution Progress: v0.49.0

## Phase Scope: Resident Move-In / Move-Out Logistics, Freight Elevator Bookings & Key Handover Engine
Complete move-in/move-out logistics orchestration engine including freight elevator reservations, loading dock access, moving company COI compliance, interactive move checklists, conversational RAG grounding, and Streamlit management hub.

## Acceptance Criteria Status

- [ ] **AC1: SQLite Database Tables & Schema Migration (`api/move_logistics.py`)** ✅
- [ ] **AC2: Pydantic Validation Schemas & Enums (`api/pydantic_models.py`)**
  - Request/response schemas for move logistics events, elevator bookings, checklist status updates, session actions, and summary KPIs with full field validations.
- [ ] **AC3: FastAPI Endpoints & Webhook Dispatch (`api/main.py`, `api/db_utils.py`)**
  - RESTful endpoints for move logistics, elevator reservations, checklist updates, metrics, and 1-click session actions `POST /sessions/{id}/schedule-move` and `POST /sessions/{id}/reserve-freight-elevator`.
- [ ] **AC4: Conversational RAG Grounding & Prompt Macros (`api/tenant_context.py`)**
  - Context injection `[MOVE-IN / MOVE-OUT LOGISTICS & ELEVATOR RESERVATIONS]` and auto-resolution of `{move_logistics_type}`, `{move_date}`, `{elevator_slot}`, `{loading_dock_status}`, `{move_checklist_progress}`, `{move_status}`.
- [ ] **AC5: Streamlit Client API Helpers (`app/api_utils.py`)**
  - Typed client API wrappers with error handling, session header forwarding, and payload verification.
- [ ] **AC6: Streamlit UI Move Logistics Board & Session Actions (`app/sidebar.py`)**
  - 4-tab move logistics management board (`Scheduled Moves`, `Book Move / Elevator`, `Mover COI Tracker`, `Logistics KPIs`) and 1-click resident profile move scheduling & elevator reservation actions.
- [ ] **AC7: Automated Unit & Integration Tests (`tests/`)**
  - Test suites for database operations, models, FastAPI routes, RAG context, client utilities, and UI mocks.
- [ ] **AC8: Documentation Updates & Version Bump**
  - Endpoints documented in `docs/API.md`, feature highlights in `README.md`, version bump to `0.49.0` in `pyproject.toml` and `api/settings.py`.
- [ ] **AC9: 100% Green CI Parity & Remote Actions Pass**
  - All formatters, linters, type checks, secret scans, unit tests (coverage >= 80%), and remote CI runs green.

## Micro-Task Execution Checklist

- [x] Task 1: Document v0.49.0 scope, acceptance criteria, and checklist in `ROADMAP.md` and `docs/PROGRESS.md`.
- [x] Task 2: Implement `api/move_logistics.py` database schema, models, CRUD helpers, metrics, and seed data with unit tests in `tests/test_move_logistics.py`.
- [x] Task 3: Define Pydantic request/response schemas in `api/pydantic_models.py` and webhook events in `api/db_utils.py` with schema tests in `tests/test_models.py`.
- [ ] Task 4: Implement FastAPI endpoints and 1-click session actions in `api/main.py` with route tests in `tests/test_move_logistics_routes.py`.
- [ ] Task 5: Implement RAG prompt grounding and macro variable resolution in `api/tenant_context.py` with tests in `tests/test_tenant_context.py`.
- [ ] Task 6: Implement Streamlit API client wrappers in `app/api_utils.py` with tests in `tests/test_app_api_utils.py`.
- [ ] Task 7: Implement Streamlit UI move logistics board and session resident widget in `app/sidebar.py` with tests in `tests/test_app_ui.py`.
- [ ] Task 8: Version bump to `0.49.0` and documentation updates in `docs/API.md` and `README.md`.
- [ ] Task 9: Final local and remote CI verification, Draft PR delivery, and final delivery report.

## Decision Log
- **D1: Dedicated Move Logistics & Elevator Module**: Followed established modular pattern (`api/announcements.py`, `api/incidents.py`, `api/access_control.py`) creating a dedicated `api/move_logistics.py`.
- **D2: Dedicated Elevator Booking Slots**: Freight elevators operate in fixed discrete slots (`slot_morning_08_12`, `slot_afternoon_12_16`, `slot_evening_16_20`) with strict double-booking collision prevention per building/elevator.
- **D3: Moving Company Insurance (COI) Verification**: COI compliance state machine (`pending`, `verified`, `waived`, `rejected`) ensures building security and safety protocols prior to elevator key release.
