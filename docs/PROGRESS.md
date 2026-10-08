# v0.31.0 Progress Record: Customer Support SLA Policies, Priority Triage & Automated Escalation Alerts Engine

**Phase Branch**: `phase/v0.31.0-sla-triage`  
**Status**: IN PROGRESS  
**Target Version**: 0.31.0  

---

## 1. Task Breakdown & Execution Status

- [x] **Task 1**: `ROADMAP.md` v0.31.0 plan specification and `docs/PROGRESS.md` record initialization
- [x] **Task 2**: Database schema migration, `sla_policies` table & CRUD, and priority support in `api/db_utils.py`
- [x] **Task 3**: Unit tests for database priority migration and SLA policy CRUD in `tests/test_db_utils.py`
- [x] **Task 4**: Pydantic schemas in `api/pydantic_models.py`
- [x] **Task 5**: Unit tests for SLA Pydantic models in `tests/test_models.py`
- [x] **Task 6**: Core SLA calculation, breach detection, alert dispatching, and compliance analytics engine in `api/sla.py`
- [x] **Task 7**: Unit tests for SLA engine in `tests/test_sla.py`
- [x] **Task 8**: FastAPI routes in `api/main.py` and session priority update handling
- [x] **Task 9**: Integration and endpoint tests for FastAPI SLA routes in `tests/test_api_routes.py`
- [x] **Task 10**: Client helpers in `app/api_utils.py` with unit tests in `tests/test_api_utils.py` and `tests/test_app_api_utils.py`
- [x] **Task 11**: Streamlit UI priority triage, SLA countdown card, and compliance panel in `app/sidebar.py`
- [x] **Task 12**: Streamlit UI unit tests in `tests/test_app_ui.py`
- [x] **Task 13**: Documentation updates in `docs/API.md` and `README.md`
- [ ] **Task 14**: Version bump to 0.31.0 in `pyproject.toml` and `api/settings.py`
- [ ] **Task 15**: Final verification, progress record completion, and review audit

---

## 2. Acceptance Criteria Status

| # | Acceptance Criterion | Status | Evidence |
|---|----------------------|--------|----------|
| AC1 | `sla_policies` table exists, auto-seeds default real estate policies on init, and supports CRUD with `(priority, category)` resolution | VERIFIED | `tests/test_db_utils.py::test_create_sla_policies_seeds_defaults`, `test_create_and_get_sla_policy`, `test_get_matching_sla_policy_with_fallbacks`, `test_list_and_update_and_delete_sla_policy` |
| AC2 | `session_labels` table migrates to include `priority TEXT NOT NULL DEFAULT 'medium'` column with validation for `urgent`, `high`, `medium`, `low` | VERIFIED | `tests/test_db_utils.py::test_migrate_session_labels_adds_priority_column`, `test_normalize_session_priority`, `test_update_and_get_session_metadata_with_priority` |
| AC3 | `calculate_session_sla_status()` matches best policy, calculates `response_due_at`, `resolution_due_at`, evaluates met/breached/approaching status based on message timestamps and session lifecycle status | VERIFIED | `tests/test_sla.py::test_calculate_session_sla_status_healthy_and_policy_match`, `test_calculate_session_sla_status_response_met_and_breached`, `test_calculate_session_sla_status_resolution_met` |
| AC4 | Webhook events `sla.approaching_breach` and `sla.breached` are recognized and dispatched to registered webhooks when alerts are evaluated | VERIFIED | `tests/test_sla.py::test_evaluate_and_dispatch_sla_alerts` |
| AC5 | FastAPI endpoints `/sla/policies`, `/sessions/{session_id}/sla`, `/sla/evaluate-alerts`, and `/sla/analytics` are functional and schema-validated | VERIFIED | `tests/test_api_routes.py::test_sla_policies_crud_routes`, `test_session_priority_update_route`, `test_session_sla_route`, `test_evaluate_sla_alerts_route`, `test_sla_analytics_route` |
| AC6 | Client helpers in `app/api_utils.py` provide reliable access with authentication and error handling | VERIFIED | `tests/test_app_api_utils.py::test_list_sla_policies`, `test_create_sla_policy`, `test_get_and_delete_sla_policy`, `test_update_sla_policy`, `test_get_session_sla_status`, `test_evaluate_sla_alerts`, `test_get_sla_compliance_analytics`, `test_update_session_with_priority` |
| AC7 | Streamlit UI displays priority badges, active session SLA countdown card, and SLA Policies & Compliance analytics panel | VERIFIED | `tests/test_app_ui.py::test_render_session_metadata_with_priority`, `test_render_session_sla_card`, `test_render_sla_compliance_metrics`, `test_render_sla_alerts_trigger`, `test_render_sla_policy_list_and_delete`, `test_render_sla_policy_creator` |
| AC8 | Full test suite passes with >= 80% coverage and zero ruff / mypy errors | PENDING | Pending Task 15 |

---

## 3. Decision Log

- **Decision 1 (2026-10-08)**: Select v0.31.0 SLA Policies, Priority Triage & Automated Escalation Alerts Engine as the next development phase.
  - *Context*: Baseline tests, ruff, and mypy are fully passing. The next unfinished item in `ROADMAP.md` is v0.31.0.
  - *Alternatives considered*: Maintenance refactoring or moving directly to multi-tenant agent auth.
  - *Rationale*: v0.31.0 directly builds on the triage analytics (v0.27.0), webhooks (v0.28.0), and macro templates (v0.29.0) by providing SLA enforcement and priority routing essential for property management customer operations.
  - *Blast radius & Reversibility*: High cohesion with existing session metadata and webhook dispatching, zero breaking changes to existing endpoints.

- **Decision 2 (2026-10-08)**: Use calendar-minute SLA deadlines (24/7 basis) with `(priority, category)` policy fallback.
  - *Context*: Property management urgent maintenance emergencies (water leaks, heating failure) require immediate 24/7 tracking without complex calendar schedules.
  - *Rationale*: A fallback mechanism that checks `(priority, category)` -> `(priority, 'general')` -> default provides graceful handling for any incoming session without requiring strict category tagging.

---

## 4. Validation Commands & Results

- **Baseline Check**:
  - `python -m ruff check api/ app/ tests/ scripts/` -> ✅ Passed (0 issues)
  - `python -m mypy api/ app/ scripts/` -> ✅ Passed (0 issues in 24 source files)
  - `python -m pytest` -> ✅ Passed (588 passed, 95.82% coverage, fail_under=80%)
