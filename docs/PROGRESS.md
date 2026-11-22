# Phase Execution Progress: v0.54.0

## Phase Scope: Security Deposit Escrow, Itemized Deductions, Statutory Disposition & Dispute Resolution Engine
Deliver an end-to-end Security Deposit Escrow, Itemized Deductions, Statutory Return Deadline Compliance & Resident Dispute Resolution Engine (`api/security_deposits.py`) integrated with FastAPI, conversational RAG grounding, template macros, real-time webhooks, and the Streamlit operations hub.

## Acceptance Criteria Status

- [x] **AC1: Core Engine & SQLite Schema (`api/security_deposits.py`)** ✅
  - Tables `security_deposits`, `deposit_deductions`, and `deposit_disputes` with indexes, foreign keys, enums, seeds, CRUD, itemized statements, refunds, disputes, summaries, and KPI metrics.
- [x] **AC2: Pydantic Validation Schemas & Webhook Events (`api/pydantic_models.py`, `api/db_utils.py`)** ✅
  - Request/response models for deposits, deductions, statements, refunds, disputes, summaries, metrics, and 6 `deposit.*` webhook events.
- [ ] **AC3: FastAPI Endpoints & 1-Click Session Actions (`api/main.py`)**
  - Endpoints for `/deposits*`, `/units/{id}/deposits/summary`, `/tenants/{id}/deposits/summary`, and 1-click session actions.
- [ ] **AC4: Conversational RAG Grounding & Prompt Macros (`api/tenant_context.py`)**
  - Context block `[SECURITY DEPOSIT & REFUND DISPOSITION]` and 5 macro variables (`{deposit_amount}`, `{deposit_status}`, `{deposit_deductions_total}`, `{deposit_net_refund}`, `{deposit_deadline_date}`).
- [ ] **AC5: Streamlit API Client Helpers (`app/api_utils.py`)**
  - Typed client API wrappers for all security deposit endpoints.
- [ ] **AC6: Streamlit UI Operations Board & Session Widget (`app/sidebar.py`)**
  - 3-tab `🏦 Security Deposits & Refunds` sidebar expander and 1-click resident profile action widget.
- [ ] **AC7: Automated Unit & Integration Tests (`tests/`)**
  - Full test coverage across engine, models, routes, RAG context, API client, and UI with >= 80% total coverage.
- [ ] **AC8: Version Bump & Documentation Updates**
  - Version bumped to `0.54.0` in `pyproject.toml` and `api/settings.py`; docs updated in `docs/API.md`, `README.md`, `ROADMAP.md`, and `docs/PROGRESS.md`.
- [ ] **AC9: 100% Green CI Parity & Remote Actions Pass**
  - Ruff, mypy, secret scan, pytest coverage, and remote GitHub Actions CI green.

## Micro-Task Execution Checklist

- [x] Task 1: Define v0.54.0 phase scope in `ROADMAP.md` and `docs/PROGRESS.md`.
- [x] Task 2: Implement `api/security_deposits.py` (enums, schema, seeds, CRUD, deductions, disposition statements, refunds, disputes, summaries, metrics) with unit tests.
- [x] Task 3: Register `deposit.*` webhook events in `api/db_utils.py` and add Pydantic schemas in `api/pydantic_models.py` with tests.
- [ ] Task 4: Implement FastAPI endpoints and 1-click session actions in `api/main.py` with route integration tests.
- [ ] Task 5: Implement RAG prompt grounding and macro variables in `api/tenant_context.py` with tests.
- [ ] Task 6: Implement Streamlit client API helpers in `app/api_utils.py` with tests.
- [ ] Task 7: Implement Streamlit UI operations board and session widget in `app/sidebar.py` with UI tests.
- [ ] Task 8: Version bump to `0.54.0` and update documentation.
- [ ] Task 9: Final self-review, local CI-parity verification, remote CI green check, and Draft PR delivery.

## Decision Log
- **D1: Dedicated Security Deposits Module (`api/security_deposits.py`)**: Follows the modular architecture pattern of `api/preventative_maintenance.py`, `api/sublets.py`, and `api/insurance.py` with self-initializing SQLite tables and foreign keys to `units` and `tenants`.
- **D2: Deterministic Future-Proof Statutory Deadlines in Seeds**: Use relative UTC dates (`+21 days` / `+30 days`) for seeded deposits so tests never flake as calendar dates advance.
- **D3: Computed Net Refundable Balance**: `net_refundable = max(0.0, round(principal_amount + accrued_interest - total_deductions, 2))` is dynamically computed from `deposit_deductions` so itemized adjustments and dispute resolutions remain strictly consistent.
- **D4: Explicit Interest Accrual vs. Jurisdiction Tables**: Track `accrued_interest` explicitly per deposit record rather than embedding hard-coded state-by-state legal tables, keeping the model flexible across jurisdictions.

## CI & Validation Log
- Baseline (`origin/main` @ `7c26fac`):
  - `python -m ruff check api/ app/ tests/ scripts/` → exit 0 ✅
  - `python -m mypy api/ app/ scripts/` → exit 0 (45 source files) ✅
  - `python -m pytest -q --no-cov` → 1128 passed, 0 failed ✅
  - Remote GitHub Actions CI (`main`, run `44634911037`) → success ✅
