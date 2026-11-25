# Phase Execution Progress: v0.56.0

## Phase Scope: Property Owner Portals, Monthly Disbursement Statements, CapEx Reserve Tracking & Owner Approvals Engine
Deliver an end-to-end Property Owner Portal, Monthly Disbursement Statements, CapEx Reserve Accounting & Owner Approvals Engine (`api/owner_portal.py`) integrated with FastAPI, conversational RAG grounding, template macros, real-time webhooks, and the Streamlit operations hub.

## Acceptance Criteria Status

- [x] **AC1: Core Engine & SQLite Schema (`api/owner_portal.py`)** ✅
  - Tables `property_owners`, `owner_statements`, and `owner_approvals` with indexes, foreign keys, enums, seeds, owner CRUD, statement generation/Markdown rendering/disbursement, CapEx approval workflow, summaries, and KPIs.
- [x] **AC2: Pydantic Validation Schemas & Webhook Events (`api/pydantic_models.py`, `api/db_utils.py`)** ✅
  - Request/response models for owners, statements, approvals, summaries, metrics, and 6 `owner.*` webhook events.
- [ ] **AC3: FastAPI Endpoints & 1-Click Session Escalation (`api/main.py`)**
  - Endpoints for `/owners/*`, `/units/{id}/owner-approvals/summary`, and 1-click session escalation.
- [ ] **AC4: Conversational RAG Grounding & Prompt Macros (`api/tenant_context.py`)**
  - Context block `[OWNER CAPEX & MAJOR REPAIR APPROVALS]` and 5 macro variables (`{owner_pending_approvals_count}`, `{owner_latest_approval_title}`, `{owner_latest_approval_status}`, `{owner_latest_approval_cost}`, `{owner_capex_status}`).
- [ ] **AC5: Streamlit API Client Helpers (`app/api_utils.py`)**
  - Typed client API wrappers for all owner portal endpoints.
- [ ] **AC6: Streamlit UI Operations Board & Session Widget (`app/sidebar.py`)**
  - 3-tab `🏛️ Owner Portal & Disbursements` sidebar expander and 1-click session approval widget.
- [ ] **AC7: Automated Unit & Integration Tests (`tests/`)**
  - Full test coverage across engine, models, routes, RAG context, API client, and UI with >= 80% total coverage.
- [ ] **AC8: Version Bump & Documentation Updates**
  - Version bumped to `0.56.0` in `pyproject.toml` and `api/settings.py`; docs updated in `docs/API.md`, `README.md`, `ROADMAP.md`, and `docs/PROGRESS.md`.
- [ ] **AC9: 100% Green CI Parity & Remote Actions Pass**
  - Ruff, mypy, secret scan, pytest coverage, and remote GitHub Actions CI green.

## Micro-Task Execution Checklist

- [x] Task 1: Define v0.56.0 phase scope in `ROADMAP.md` and `docs/PROGRESS.md`.
- [x] Task 2: Implement `api/owner_portal.py` (enums, schema, seeds, owner CRUD, statements, disbursements, CapEx approvals, summaries, KPIs) with unit tests.
- [x] Task 3: Register `owner.*` webhook events in `api/db_utils.py` and add Pydantic schemas in `api/pydantic_models.py` with tests.
- [ ] Task 4: Implement FastAPI endpoints and 1-click session escalation in `api/main.py` with route integration tests.
- [ ] Task 5: Implement RAG prompt grounding and macro variables in `api/tenant_context.py` with tests.
- [ ] Task 6: Implement Streamlit client API helpers in `app/api_utils.py` with tests.
- [ ] Task 7: Implement Streamlit UI operations board and session widget in `app/sidebar.py` with UI tests.
- [ ] Task 8: Version bump to `0.56.0` and update documentation.
- [ ] Task 9: Final self-review, local CI-parity verification, remote CI green check, and Draft PR delivery.

## Decision Log
- **D1: Dedicated Owner Portal Module (`api/owner_portal.py`)**: Follows the modular architecture pattern of `api/leasing_crm.py` and `api/security_deposits.py` with self-initializing SQLite tables and foreign keys to `units`.
- **D2: Automated Management Fee & Net Disbursement Math**: Monthly statements auto-compute `management_fee_amount = round((gross_rent_collected + other_income) * (management_fee_pct / 100.0), 2)` and `net_disbursement = round(gross_rent_collected + other_income - operating_expenses - management_fee_amount - reserve_contribution, 2)`.
- **D3: Reserve Balance Credit on Disbursement**: Disbursing a statement atomically marks it `disbursed` and credits `reserve_contribution` into the owner's `reserve_balance` so CapEx reserve ledgers stay synchronized.
- **D4: Unit-Level RAG Grounding for CapEx Approvals**: Ground pending/recent owner approvals for a resident's unit into `[OWNER CAPEX & MAJOR REPAIR APPROVALS]` so support agents can answer resident questions about major repairs awaiting owner authorization.

## CI & Validation Log
- Baseline (`origin/main` @ `f3ebc90`):
  - `python -m ruff check api/ app/ tests/ scripts/` → exit 0 ✅
  - `python -m mypy api/ app/ scripts/` → exit 0 (47 source files) ✅
  - Remote GitHub Actions CI (`main`, run `45406410780`) → success ✅
