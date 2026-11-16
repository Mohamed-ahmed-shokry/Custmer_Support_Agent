# Phase Execution Progress: v0.51.0

## Phase Scope: Resident Renters Insurance Compliance, Policy Verification & Claims Engine
Complete renters insurance compliance verification, certificate of insurance (COI) tracking, coverage lapse detection, automatic force-placed non-compliance fee assessment, resident claim filing, conversational RAG grounding, and Streamlit management operations hub.

## Acceptance Criteria Status

- [x] **AC1: SQLite Database Tables & Schema Migration (`api/insurance.py`)** ✅
  - Tables `insurance_policies` and `insurance_claims` with indexes, foreign keys to `units` and `tenants`, and default seed records.
- [x] **AC2: Pydantic Validation Schemas & Enums (`api/pydantic_models.py`)** ✅
  - Request/response schemas for policies, verification, claims, disputes, session actions, and summary KPIs with full field validations.
- [ ] **AC3: FastAPI Endpoints & Webhook Dispatch (`api/main.py`, `api/db_utils.py`)**
  - RESTful endpoints for insurance policies, verification, claims, metrics, unit/tenant summaries, and 1-click session actions `POST /sessions/{id}/submit-insurance` and `POST /sessions/{id}/file-insurance-claim`.
- [ ] **AC4: Conversational RAG Grounding & Prompt Macros (`api/tenant_context.py`)**
  - Context injection `[RESIDENT RENTERS INSURANCE & COVERAGE COMPLIANCE]` and auto-resolution of `{insurance_policy_status}`, `{insurance_carrier}`, `{insurance_policy_number}`, `{insurance_liability_coverage}`, `{insurance_expiration_date}`, `{insurance_compliance_fee}`.
- [ ] **AC5: Streamlit Client API Helpers (`app/api_utils.py`)**
  - Typed client API wrappers with error handling, session header forwarding, and payload verification.
- [ ] **AC6: Streamlit UI Insurance Board & Session Actions (`app/sidebar.py`)**
  - 4-tab insurance management board (`Active Policies & COIs`, `Verification Queue`, `Resident Claims`, `Compliance KPIs`) and 1-click resident profile insurance actions.
- [ ] **AC7: Automated Unit & Integration Tests (`tests/`)**
  - Test suites for database operations, models, FastAPI routes, RAG context, client utilities, and UI mocks.
- [ ] **AC8: Documentation Updates & Version Bump**
  - Endpoints documented in `docs/API.md`, feature highlights in `README.md`, version bump to `0.51.0` in `pyproject.toml` and `api/settings.py`.
- [ ] **AC9: 100% Green CI Parity & Remote Actions Pass**
  - All formatters, linters, type checks, secret scans, unit tests (coverage >= 80%), and remote CI runs green.

## Micro-Task Execution Checklist

- [x] Task 1: Document v0.51.0 scope, acceptance criteria, and checklist in `ROADMAP.md` and `docs/PROGRESS.md`.
- [x] Task 2: Implement `api/insurance.py` database schema, models, CRUD helpers, verification, fee assessment, metrics, and seed data with unit tests in `tests/test_insurance.py`.
- [x] Task 3: Define Pydantic request/response schemas in `api/pydantic_models.py` and webhook events in `api/db_utils.py` with schema tests in `tests/test_models.py`.
- [x] Task 4: Implement FastAPI endpoints and 1-click session actions in `api/main.py` with route tests in `tests/test_insurance_routes.py`.
- [x] Task 5: Implement RAG prompt grounding and macro variable resolution in `api/tenant_context.py` with tests in `tests/test_tenant_context.py`.
- [x] Task 6: Implement Streamlit API client wrappers in `app/api_utils.py` with tests in `tests/test_app_api_utils.py`.
- [x] Task 7: Implement Streamlit UI insurance board and session resident widget in `app/sidebar.py` with tests in `tests/test_app_ui.py`.
- [ ] Task 8: Version bump to `0.51.0` and documentation updates in `docs/API.md` and `README.md`.
- [ ] Task 9: Final local and remote CI verification, Draft PR delivery, and final delivery report.

## Decision Log
- **D1: Dedicated Insurance Module**: Followed established modular pattern (`api/utilities.py`, `api/move_logistics.py`, `api/announcements.py`) creating a dedicated `api/insurance.py`.
- **D2: Standard Liability Threshold & Interested Party**: Enforce minimum $100,000 personal liability requirement for property compliance and require property entity listed as interested party on the certificate of insurance.
- **D3: Automatic Non-Compliance Ledger Fee**: When a resident's policy lapses or is rejected, property management assesses a monthly non-compliance fee ($25.00) directly posted to resident rent ledger (`billing_transactions`), with automatic charge reversal if a verified policy with retroactive proof is provided.
