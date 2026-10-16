# v0.37.0 Progress Record: Resident Billing, Rent Ledgers, Invoices & Payment Operations Engine

**Phase Branch**: `phase/v0.37.0-resident-billing-ledgers`  
**Status**: 🟡 IN PROGRESS  
**Target Version**: 0.37.0  

---

## 1. Task Breakdown & Execution Status

- [x] **Task 1**: `ROADMAP.md` v0.37.0 plan specification and `docs/PROGRESS.md` initialization
- [ ] **Task 2**: Database schema, table creation, default seed data, and CRUD operations for `billing_transactions` in `api/db_utils.py` + unit tests in `tests/test_db_utils.py`
- [ ] **Task 3**: Payment recording and tenant balance reconciliation logic in `api/db_utils.py` + unit tests in `tests/test_db_utils.py`
- [ ] **Task 4**: Context grounding engine integration for billing & ledgers in `api/tenant_context.py` + unit tests in `tests/test_tenant_context.py`
- [ ] **Task 5**: Pydantic request/response schemas in `api/pydantic_models.py` + unit tests in `tests/test_models.py`
- [ ] **Task 6**: FastAPI endpoints for billing transactions, ledger statements, and session payment recording in `api/main.py` + route tests in `tests/test_api_routes.py`
- [ ] **Task 7**: Streamlit client API helpers in `app/api_utils.py` + unit tests in `tests/test_app_api_utils.py`
- [ ] **Task 8**: Streamlit UI components in `app/sidebar.py` (session payment recording & "💰 Billing & Rent Ledgers" panel) + UI tests in `tests/test_app_ui.py`
- [ ] **Task 9**: Documentation updates (`docs/API.md`, `README.md`) and version bump to `0.37.0` (`pyproject.toml`, `api/settings.py`)
- [ ] **Task 10**: Final verification gate (`pytest` >= 80% coverage, `ruff check`, `mypy`), progress record completion, and draft PR delivery

---

## 2. Acceptance Criteria Status

| # | Acceptance Criterion | Status | Evidence |
|---|----------------------|--------|----------|
| AC1 | `billing_transactions` SQLite table is created, pre-seeded with defaults, and supported with full CRUD, filtering, ledger summaries, and portfolio metrics in `api/db_utils.py` | PENDING | Pending Task 2 |
| AC2 | `record_tenant_payment()` performs atomic payment logging and automatic `tenants.balance_due` reconciliation | PENDING | Pending Task 3 |
| AC3 | `api/tenant_context.py` augments grounding prompt context with `[RESIDENT BILLING & PAYMENT LEDGER]` and auto-resolves billing macro variables | PENDING | Pending Task 4 |
| AC4 | Webhook events `billing.payment_received`, `billing.charge_posted`, `billing.late_fee_assessed`, and `billing.overdue_escalated` trigger correctly on transaction events | PENDING | Pending Task 3 & 6 |
| AC5 | Pydantic schemas in `api/pydantic_models.py` validate transaction creation, payments, ledger queries, and summary responses | PENDING | Pending Task 5 |
| AC6 | FastAPI endpoints `/billing/*`, `/tenants/{id}/payments`, `/tenants/{id}/ledger`, and `/sessions/{id}/record-payment` are wired and tested | PENDING | Pending Task 6 |
| AC7 | Client helpers in `app/api_utils.py` provide typed methods with `X-API-Key` forwarding and resilient error handling | PENDING | Pending Task 7 |
| AC8 | Streamlit UI in `app/sidebar.py` provides the 1-click payment recording widget in session card and the "💰 Billing & Rent Ledgers" management panel | PENDING | Pending Task 8 |
| AC9 | Documentation (`README.md`, `docs/API.md`, `ROADMAP.md`, `docs/PROGRESS.md`) and version bump to `0.37.0` (`pyproject.toml`, `api/settings.py`) are complete | PENDING | Pending Task 9 |
| AC10 | Full verification suite (`pytest` with >= 80% coverage, `ruff check`, `mypy`) passes with zero regressions | PENDING | Pending Task 10 |

---

## 3. Decision Log

- **Decision 1 (2026-10-17)**: Select **v0.37.0 — Resident Billing, Rent Ledgers, Invoices & Payment Operations Engine** as the development phase.
  - *Context*: Following v0.35.0 (Tenant & Property Directory) and v0.36.0 (Maintenance Work Orders & Dispatch), financial questions regarding rent balances, fee breakdowns, payment confirmations, and ledger statements represent the second highest customer support inquiry volume. Currently, `tenants` stores an isolated `balance_due` without a backing financial transaction ledger or payment history.
  - *Alternatives considered*: Lease renewal document generation (lower frequency inquiry; relies on financial standing) or third-party payment gateway integration (breaks local-first, zero-external-dependency requirement).
  - *Rationale*: A local-first financial ledger (`billing_transactions`) with atomic balance reconciliation and context grounding empowers customer service agents to address billing disputes, verify payments, and log resident payments without external payment processors.
  - *Blast radius & Reversibility*: Additive SQLite table `billing_transactions`, additive webhook events, additive context block `[RESIDENT BILLING & PAYMENT LEDGER]`, and new isolated `/billing/*` endpoints.

---

## 4. Validation Commands & Results

- **Baseline Check (v0.36.0)**:
  - `python -m ruff check api/ app/ tests/ scripts/` -> ✅ Passed (`All checks passed!`)
  - `python -m mypy api/ app/ scripts/` -> ✅ Passed (`Success: no issues found in 30 source files`)
  - `python -m pytest -q` -> ✅ Passed (`776 passed, 21 deselected, 93.38% coverage, fail_under=80%`)
