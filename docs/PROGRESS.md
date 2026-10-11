# v0.32.0 Progress Record: Customer Support Agent Assignment, Tiered Escalation Routing & Operating Business Hours Engine

**Phase Branch**: `phase/v0.32.0-agent-assignment-business-hours`  
**Status**: IN PROGRESS  
**Target Version**: 0.32.0  

---

## 1. Task Breakdown & Execution Status

- [x] **Task 1**: `ROADMAP.md` v0.32.0 plan specification and `docs/PROGRESS.md` initialization
- [x] **Task 2**: Database schema migration, `support_agents` CRUD, `session_assignment_history` in `api/db_utils.py`
- [x] **Task 3**: Unit tests for database agent CRUD, assignment history, and migrations in `tests/test_db_utils.py`
- [x] **Task 4**: Operating business hours engine in `api/business_hours.py`
- [x] **Task 5**: Unit tests for business hours calculation in `tests/test_business_hours.py`
- [x] **Task 6**: Pydantic schemas in `api/pydantic_models.py`
- [x] **Task 7**: Unit tests for new Pydantic models in `tests/test_models.py`
- [x] **Task 8**: Core assignment, tiered routing, workload analytics, and SLA business hours integration in `api/assignment.py` and `api/sla.py`
- [x] **Task 9**: Unit tests for assignment and workload engine in `tests/test_assignment.py`
- [ ] **Task 10**: FastAPI routes in `api/main.py`
- [ ] **Task 11**: Integration and endpoint tests for FastAPI agent and assignment routes in `tests/test_api_routes.py`
- [ ] **Task 12**: Client helpers in `app/api_utils.py` with unit tests in `tests/test_api_utils.py` and `tests/test_app_api_utils.py`
- [ ] **Task 13**: Streamlit UI assignee/tier controls, auto-assign button, queue filters, and workload panel in `app/sidebar.py`
- [ ] **Task 14**: Streamlit UI unit tests in `tests/test_app_ui.py`
- [ ] **Task 15**: Documentation updates in `docs/API.md` and `README.md`
- [ ] **Task 16**: Version bump to 0.32.0 in `pyproject.toml` and `api/settings.py`
- [ ] **Task 17**: Final verification gate, progress record completion, and self-review audit

---

## 2. Acceptance Criteria Status

| # | Acceptance Criterion | Status | Evidence |
|---|----------------------|--------|----------|
| AC1 | `support_agents` table exists, pre-seeds 5 default real estate agents on initialization, and supports full CRUD | VERIFIED | `tests/test_db_utils.py::test_create_support_agents_seeds_defaults`, `test_support_agent_crud_and_validation`, `test_list_support_agents_filters` |
| AC2 | `session_labels` table migrates to include `assigned_agent TEXT DEFAULT NULL` and `escalation_tier TEXT NOT NULL DEFAULT 'tier_1'` with validation for `tier_1`, `tier_2`, `tier_3` | VERIFIED | `tests/test_db_utils.py::test_migrate_session_labels_adds_agent_and_tier`, `test_update_and_get_session_metadata_agent_and_tier`, `test_get_all_sessions_agent_and_tier_filtering` |
| AC3 | `session_assignment_history` table records audit log transitions for agent and tier re-assignments with timestamps, actors, and reasons | VERIFIED | `tests/test_db_utils.py::test_session_assignment_history` |
| AC4 | `api/assignment.py` supports manual assignment and least-busy auto-assignment with webhook notifications (`session.assigned`, `session.tier_escalated`) | PENDING | Pending Task 8 & 9 |
| AC5 | `api/business_hours.py` accurately evaluates business hours status and advances deadlines across nights and weekends for business-hours SLA policies | VERIFIED | `tests/test_business_hours.py::test_is_within_business_hours_standard_weekday`, `test_is_within_business_hours_weekend`, `test_get_next_business_window_start`, `test_add_business_minutes_same_day`, `test_add_business_minutes_crosses_evening_and_weekend`, `test_calculate_business_minutes_between`, `test_get_business_hours_status`, `test_custom_schedule_support` |
| AC6 | FastAPI endpoints `/agents`, `/agents/workload`, `/sessions/{id}/assign`, `/sessions/{id}/auto-assign`, `/sessions/{id}/assignment-history`, and `/business-hours/status` are functional and schema-validated | PENDING | Pending Task 10 & 11 |
| AC7 | Client helpers in `app/api_utils.py` provide typed API methods with error handling | PENDING | Pending Task 12 |
| AC8 | Streamlit UI displays operating hours indicator, assignee/tier controls, auto-assign action, queue filters, and team workload panel | PENDING | Pending Task 13 & 14 |
| AC9 | Full test suite passes with >= 80% coverage and zero ruff / mypy errors | PENDING | Baseline passed (629 passed, 94.72% coverage) |

---

## 3. Decision Log

- **Decision 1 (2026-10-11)**: Select v0.32.0 Customer Support Agent Assignment, Tiered Escalation Routing & Operating Business Hours Engine as the next development phase.
  - *Context*: Baseline tests, ruff, and mypy are fully green. v0.31.0 delivered priority triage and SLA tracking, and explicitly deferred business hours schedule calculations and agent-specific escalation assignment.
  - *Alternatives considered*: Direct multi-tenant database isolation or external calendar syncing.
  - *Rationale*: Agent ownership, tiered routing (Tier 1 Frontline -> Tier 2 Operations/Specialist -> Tier 3 Management), and business hours calculation complete the core operational workflow needed for property management support desks without requiring heavy external dependencies.
  - *Blast radius & Reversibility*: High cohesion with existing session metadata, webhooks, and SLA policies. Database schema additions are backward-compatible with default values.

- **Decision 2 (2026-10-11)**: Design Business Hours as a deterministic schedule engine in `api/business_hours.py` supporting opt-in SLA policies via `use_business_hours` flag.
  - *Context*: Emergency maintenance requests must track 24/7 calendar minutes, whereas routine leasing or billing inquiries must not breach SLA over weekends or after 18:00.
  - *Rationale*: Adding `use_business_hours` to `sla_policies` provides fine-grained control per policy, allowing urgent policies to run 24/7 while routine policies respect operating hours.

---

## 4. Validation Commands & Results

- **Baseline Check (v0.31.0)**:
  - `python -m ruff check api/ app/ tests/ scripts/` -> ✅ Passed (0 issues)
  - `python -m mypy api app scripts` -> ✅ Passed (0 issues in 25 source files)
  - `python -m pytest` -> ✅ Passed (629 passed, 21 deselected, 94.72% coverage, fail_under=80%)
