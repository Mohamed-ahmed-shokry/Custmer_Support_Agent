# Phase Execution Progress: v0.48.0

## Phase Scope: Community Announcements, Emergency Broadcast Alerts & Resident Concierge Requests Engine
Complete community announcements, emergency building broadcast alerts, resident acknowledgment tracking, concierge service request workflows, conversational RAG grounding, and Streamlit management hub.

## Acceptance Criteria Status

- [ ] **AC1: SQLite Database Tables & Schema Migration (`api/announcements.py`)**
  - Tables `community_announcements`, `announcement_acknowledgments`, and `concierge_requests` bootstrapped with UUID primary keys, foreign references to `units` and `tenants`, indexing on lookup keys, and pre-seeded default announcement and concierge task.
- [ ] **AC2: Pydantic Validation Schemas & Enums (`api/pydantic_models.py`)**
  - Request/response schemas for announcements, acknowledgments, concierge requests, session actions, and summary KPIs with full field validations.
- [ ] **AC3: FastAPI Endpoints & Webhook Dispatch (`api/main.py`, `api/db_utils.py`)**
  - RESTful endpoints for announcements, acknowledgments, concierge requests, metrics, and 1-click session actions `POST /sessions/{id}/acknowledge-alert` and `POST /sessions/{id}/request-concierge`.
- [ ] **AC4: Conversational RAG Grounding & Prompt Macros (`api/tenant_context.py`)**
  - Context injection `[COMMUNITY ANNOUNCEMENTS & ACTIVE BUILDING ALERTS]` and auto-resolution of `{active_announcements_count}`, `{active_emergency_alerts_count}`, `{latest_alert_headline}`, `{latest_alert_priority}`, `{alert_acknowledgment_status}`, `{concierge_requests_count}`.
- [ ] **AC5: Streamlit Client API Helpers (`app/api_utils.py`)**
  - Typed client API wrappers with error handling, session header forwarding, and payload verification.
- [ ] **AC6: Streamlit UI Announcements Board & Session Actions (`app/sidebar.py`)**
  - 4-tab announcement management board (`Active Notices`, `Publish Announcement`, `Concierge Desk`, `Broadcast KPIs`) and 1-click resident profile alert acknowledgment & concierge request actions.
- [ ] **AC7: Automated Unit & Integration Tests (`tests/`)**
  - Test suites for database operations, models, FastAPI routes, RAG context, client utilities, and UI mocks.
- [ ] **AC8: Documentation Updates & Version Bump**
  - Endpoints documented in `docs/API.md`, feature highlights in `README.md`, version bump to `0.48.0` in `pyproject.toml` and `api/settings.py`.
- [ ] **AC9: 100% Green CI Parity & Remote Actions Pass**
  - All formatters, linters, type checks, secret scans, unit tests (coverage >= 80%), and remote CI runs green.

## Micro-Task Execution Checklist

- [x] Task 1: Document v0.48.0 scope, acceptance criteria, and checklist in `ROADMAP.md` and `docs/PROGRESS.md`.
- [ ] Task 2: Implement `api/announcements.py` database schema, models, CRUD helpers, metrics, and seed data with unit tests in `tests/test_announcements.py`.
- [ ] Task 3: Define Pydantic request/response schemas in `api/pydantic_models.py` and webhook events in `api/db_utils.py` with schema tests in `tests/test_models.py`.
- [ ] Task 4: Implement FastAPI endpoints and 1-click session actions in `api/main.py` with route tests in `tests/test_announcement_routes.py`.
- [ ] Task 5: Implement RAG prompt grounding and macro variable resolution in `api/tenant_context.py` with tests in `tests/test_tenant_context.py`.
- [ ] Task 6: Implement Streamlit API client wrappers in `app/api_utils.py` with tests in `tests/test_app_api_utils.py`.
- [ ] Task 7: Implement Streamlit UI announcements board and session resident widget in `app/sidebar.py` with tests in `tests/test_app_ui.py`.
- [ ] Task 8: Version bump to `0.48.0` and documentation updates in `docs/API.md` and `README.md`.
- [ ] Task 9: Final local and remote CI verification, Draft PR delivery, and final delivery report.

## Decision Log
- **D1: Dedicated Announcements & Concierge Module**: Followed established modular pattern (`api/incidents.py`, `api/access_control.py`, `api/parking.py`) creating a dedicated `api/announcements.py`.
- **D2: Flexible Target Scopes**: Community announcements support scoping by `portfolio_wide`, `building`, `floor`, or `unit_specific` so that RAG context queries accurately ground notices relevant to the resident's specific building/unit.
- **D3: Mandatory Acknowledgment Workflow**: Emergency and urgent alerts flagged with `require_acknowledgment=True` track resident acknowledgment events, enabling managers to track safety compliance during critical building incidents.
