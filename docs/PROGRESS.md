# v0.37.0 Progress Record: Resident Billing, Rent Ledgers, Invoices & Payment Operations Engine

**Phase Branch**: `phase/v0.37.0-resident-billing-ledgers`  
**Status**: 🟢 COMPLETED  
**Target Version**: 0.37.0  

---

## 1. Task Breakdown & Execution Status

- [x] **Task 1**: `ROADMAP.md` v0.37.0 plan specification and `docs/PROGRESS.md` initialization
- [x] **Task 2**: Database schema, table creation, default seed data, and CRUD operations for `billing_transactions` in `api/db_utils.py` + unit tests in `tests/test_db_utils.py`
- [x] **Task 3**: Payment recording and tenant balance reconciliation logic in `api/db_utils.py` + unit tests in `tests/test_db_utils.py`
- [x] **Task 4**: Context grounding engine integration for billing & ledgers in `api/tenant_context.py` + unit tests in `tests/test_tenant_context.py`
- [x] **Task 5**: Pydantic request/response schemas in `api/pydantic_models.py` + unit tests in `tests/test_models.py`
- [x] **Task 6**: FastAPI endpoints for billing transactions, ledger statements, and session payment recording in `api/main.py` + route tests in `tests/test_api_routes.py`
- [x] **Task 7**: Streamlit client API helpers in `app/api_utils.py` + unit tests in `tests/test_app_api_utils.py`
- [x] **Task 8**: Streamlit UI components in `app/sidebar.py` (session payment recording & "💰 Billing & Rent Ledgers" panel) + UI tests in `tests/test_app_ui.py`
- [x] **Task 9**: Documentation updates (`docs/API.md`, `README.md`) and version bump to `0.37.0` (`pyproject.toml`, `api/settings.py`)
- [x] **Task 10**: Final verification gate (`pytest` >= 80% coverage, `ruff check`, `mypy`), progress record completion, and draft PR delivery

---

## 2. Acceptance Criteria Status

| # | Acceptance Criterion | Status | Evidence |
|---|----------------------|--------|----------|
| AC1 | `billing_transactions` SQLite table is created, pre-seeded with defaults, and supported with full CRUD, filtering, ledger summaries, and portfolio metrics in `api/db_utils.py` | ✅ VERIFIED | Passed unit tests in `tests/test_db_utils.py` (`test_create_billing_transaction`, `test_get_billing_transactions_filtered`, `test_get_tenant_ledger_summary`, `test_get_billing_summary_metrics`) |
| AC2 | `record_tenant_payment()` performs atomic payment logging and automatic `tenants.balance_due` reconciliation | ✅ VERIFIED | Passed in `tests/test_db_utils.py` (`test_record_tenant_payment_reconciliation_exact_and_overpayment`, `test_record_tenant_payment_webhook_dispatch`) |
| AC3 | `api/tenant_context.py` augments grounding prompt context with `[RESIDENT BILLING & PAYMENT LEDGER]` and auto-resolves billing macro variables | ✅ VERIFIED | Passed in `tests/test_tenant_context.py` (`test_build_tenant_grounding_block_includes_ledger_statement`, `test_resolve_billing_macro_variables`) |
| AC4 | Webhook events `billing.payment_received`, `billing.charge_posted`, `billing.late_fee_assessed`, and `billing.overdue_escalated` trigger correctly on transaction events | ✅ VERIFIED | Verified via mock delivery assertions in `tests/test_db_utils.py` and `tests/test_api_routes.py` |
| AC5 | Pydantic schemas in `api/pydantic_models.py` validate transaction creation, payments, ledger queries, and summary responses | ✅ VERIFIED | Passed 12 unit tests in `tests/test_models.py` validating enums, models, validation bounds, and serialization |
| AC6 | FastAPI endpoints `/billing/*`, `/tenants/{id}/payments`, `/tenants/{id}/ledger`, and `/sessions/{id}/record-payment` are wired and tested | ✅ VERIFIED | Passed in `tests/test_api_routes.py` covering route statuses (200, 201, 404, 422) |
| AC7 | Client helpers in `app/api_utils.py` provide typed methods with `X-API-Key` forwarding and resilient error handling | ✅ VERIFIED | Passed in `tests/test_app_api_utils.py` with mock responses and fallback scenarios |
| AC8 | Streamlit UI in `app/sidebar.py` provides the 1-click payment recording widget in session card and the "💰 Billing & Rent Ledgers" management panel | ✅ VERIFIED | Passed in `tests/test_app_ui.py` (`test_render_session_billing_widget`, `test_render_billing_board_and_tabs`) |
| AC9 | Documentation (`README.md`, `docs/API.md`, `ROADMAP.md`, `docs/PROGRESS.md`) and version bump to `0.37.0` (`pyproject.toml`, `api/settings.py`) are complete | ✅ VERIFIED | Verified in `pyproject.toml`, `api/settings.py`, `docs/API.md`, and `README.md` |
| AC10 | Full verification suite (`pytest` with >= 80% coverage, `ruff check`, `mypy`) passes with zero regressions | ✅ VERIFIED | Local suite passed: 787 passed, 92.77% coverage (threshold 80%), zero ruff errors, zero mypy errors |

---

## 3. Decision Log

- **Decision 1 (2026-10-17)**: Select **v0.37.0 — Resident Billing, Rent Ledgers, Invoices & Payment Operations Engine** as the development phase.
  - *Context*: Following v0.35.0 (Tenant & Property Directory) and v0.36.0 (Maintenance Work Orders & Dispatch), financial questions regarding rent balances, fee breakdowns, payment confirmations, and ledger statements represent the second highest customer support inquiry volume. Currently, `tenants` stores an isolated `balance_due` without a backing financial transaction ledger or payment history.
  - *Alternatives considered*: Lease renewal document generation (lower frequency inquiry; relies on financial standing) or third-party payment gateway integration (breaks local-first, zero-external-dependency requirement).
  - *Rationale*: A local-first financial ledger (`billing_transactions`) with atomic balance reconciliation and context grounding empowers customer service agents to address billing disputes, verify payments, and log resident payments without external payment processors.
  - *Blast radius & Reversibility*: Additive SQLite table `billing_transactions`, additive webhook events, additive context block `[RESIDENT BILLING & PAYMENT LEDGER]`, and new isolated `/billing/*` endpoints.

- **Decision 2 (2026-10-17)**: Atomic charge reconciliation strategy in `record_tenant_payment()`.
  - *Context*: When a resident submits a payment (e.g. $1,250), the system must reconcile past charges while adjusting `tenants.balance_due`.
  - *Rationale*: Sort unpaid charges (`status IN ('overdue', 'posted', 'pending')`) chronologically by `due_date ASC`, mark matching charges `paid`, update timestamps, and decrement tenant `balance_due` atomically inside SQLite transaction.

- **Decision 3 (2026-10-17)**: Fix GNU grep binary false positive in CI workflow `.github/workflows/ci.yml`.
  - *Context*: The PR cleanliness step in CI ran `grep -R` looking for unwanted files and matched SQLite binary DB files inside `.mypy_cache`.
  - *Rationale*: Added `-I` (ignore binary) and `--exclude-dir=.mypy_cache --exclude-dir=.pytest_cache` to ensure clean, deterministic CI checks.

---

## 4. Validation Commands & Results

- **Baseline Check (v0.36.0)**:
  - `python -m ruff check api/ app/ tests/ scripts/` -> ✅ Passed (`All checks passed!`)
  - `python -m mypy api/ app/ scripts/` -> ✅ Passed (`Success: no issues found in 30 source files`)
  - `python -m pytest -q` -> ✅ Passed (`776 passed, 21 deselected, 93.38% coverage, fail_under=80%`)

- **Phase Delivery Check (v0.37.0)**:
  - `python -m ruff check api/ app/ tests/ scripts/` -> ✅ Passed (`All checks passed!`)
  - `python -m mypy api/ app/ scripts/` -> ✅ Passed (`Success: no issues found in 30 source files`)
  - `python -m pytest -q` -> ✅ Passed (`787 passed, 21 deselected, 92.77% coverage, fail_under=80%`)
