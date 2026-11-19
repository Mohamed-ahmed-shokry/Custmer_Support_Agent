# Phase Execution Progress: v0.53.0

## Phase Scope: Preventative Maintenance, Seasonal HVAC/Fire Safety & Unit Compliance Engine
Fix the date-dependent baseline CI failure in `tests/test_move_logistics.py`, and deliver an end-to-end Preventative Maintenance, Seasonal HVAC/Fire Safety Inspections & Unit Compliance Engine (`api/preventative_maintenance.py`).

## Acceptance Criteria Status

- [x] **AC1: Fix Baseline CI Failure (`tests/test_move_logistics.py`)** ✅
  - Replace hardcoded `2026-11-25` date in `test_book_freight_elevator_and_collision_prevention` with `2099-06-15`.
- [x] **AC2: Core Engine & SQLite Schema (`api/preventative_maintenance.py`)** ✅
  - Tables `pm_schedules` and `pm_tasks` with indexes, foreign keys, seeds, CRUD, entry notices, fail-to-work-order escalation, and KPI metrics.
- [x] **AC3: Pydantic Validation Schemas & Webhook Events (`api/pydantic_models.py`, `api/db_utils.py`)** ✅
  - Request/response models for PM schedules, tasks, entry notices, completion/failure, summaries, and 6 `pm.*` webhook events.
- [x] **AC4: FastAPI Endpoints & 1-Click Session Actions (`api/main.py`)** ✅
  - Endpoints for `/pm/schedules*`, `/pm/tasks*`, `/pm/metrics`, `/units/{id}/pm/summary`, `/tenants/{id}/pm/summary`, and 1-click session actions.
- [ ] **AC5: Conversational RAG Grounding & Prompt Macros (`api/tenant_context.py`)**
  - Context block `[PREVENTATIVE MAINTENANCE & SAFETY COMPLIANCE]` and 5 macro variables (`{pm_next_inspection_date}`, `{pm_schedule_type}`, `{pm_compliance_status}`, `{pm_entry_notice_status}`, `{pm_overdue_count}`).
- [ ] **AC6: Streamlit API Client Helpers (`app/api_utils.py`)**
  - Typed client API wrappers for all PM endpoints.
- [ ] **AC7: Streamlit UI Operations Board & Session Widget (`app/sidebar.py`)**
  - 4-tab `🔧 Preventative Maintenance` sidebar expander and 1-click resident profile action widget.
- [ ] **AC8: Automated Unit & Integration Tests (`tests/`)**
  - Full test coverage across engine, models, routes, RAG context, API client, and UI with >= 80% total coverage.
- [ ] **AC9: Version Bump & Documentation Updates**
  - Version bumped to `0.53.0` in `pyproject.toml` and `api/settings.py`; docs updated in `docs/API.md`, `README.md`, `ROADMAP.md`, and `docs/PROGRESS.md`.
- [ ] **AC10: 100% Green CI Parity & Remote Actions Pass**
  - Ruff, mypy, secret scan, pytest coverage, and remote GitHub Actions CI green.

## Micro-Task Execution Checklist

- [x] Task 1: Fix flaky date collision in `tests/test_move_logistics.py` to restore 100% green baseline CI.
- [x] Task 2: Implement `api/preventative_maintenance.py` schema, enums, seeds, CRUD, entry notice, fail-to-work-order escalation, and metrics.
- [x] Task 3: Add Pydantic schemas in `api/pydantic_models.py` and webhook events in `api/db_utils.py`.
- [x] Task 4: Implement FastAPI endpoints and 1-click session actions in `api/main.py`.
- [ ] Task 5: Implement RAG prompt grounding and macro variables in `api/tenant_context.py`.
- [ ] Task 6: Implement Streamlit client API helpers in `app/api_utils.py`.
- [ ] Task 7: Implement Streamlit UI operations board and session widget in `app/sidebar.py`.
- [ ] Task 8: Version bump to `0.53.0` and update documentation.
- [ ] Task 9: Final self-review, local CI-parity verification, remote CI green check, and Draft PR delivery.

## Decision Log
- **D1: Dedicated Preventative Maintenance Module (`api/preventative_maintenance.py`)**: Follows the modular architecture pattern of `api/sublets.py` and `api/insurance.py` for clean isolation.
- **D2: Deterministic Future Date for Move Logistics Test**: Use `2099-06-15` in `test_book_freight_elevator_and_collision_prevention` so it never collides with dynamic `now_utc + 7/21 days` seed bookings.
- **D3: Automatic Work Order Escalation on Failed PM Task**: When a preventative maintenance task fails (`status='failed'`), optionally auto-create a linked `work_orders` record (`work_order_id`) so repairs are tracked seamlessly.
