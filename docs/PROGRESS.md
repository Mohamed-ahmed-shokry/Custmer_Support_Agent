# v0.42.0 Progress Record: Resident Package & Parcel Delivery Locker Management Engine

**Phase Branch**: phase/v0.42.0-resident-packages  
**Status**: 🟡 IN PROGRESS  
**Target Version**: 0.42.0  
**Plan**: see ROADMAP.md ("v0.42.0 plan")

---

## 1. Task Breakdown & Execution Status

- [x] **Task 1**: Update ROADMAP.md (mark v0.41.0 complete, add v0.42.0 plan) & initialize docs/PROGRESS.md
- [ ] **Task 2**: Package database engine & metrics (`api/packages.py`) + tests in `tests/test_packages.py`
- [ ] **Task 3**: Pydantic models & webhook event registration in `api/pydantic_models.py` and `api/db_utils.py`
- [ ] **Task 4**: FastAPI endpoints in `api/main.py` + route tests in `tests/test_package_routes.py`
- [ ] **Task 5**: Context grounding & macro variable resolution in `api/tenant_context.py` + tests in `tests/test_tenant_context.py`
- [ ] **Task 6**: Streamlit client API helpers in `app/api_utils.py` + unit tests in `tests/test_app_api_utils.py`
- [ ] **Task 7**: Streamlit UI components in `app/sidebar.py` (Package intake, deliveries board, metrics, session card widget) + tests in `tests/test_app_ui.py`
- [ ] **Task 8**: Documentation updates (`docs/API.md`, `README.md`) and version bump to `0.42.0` (`pyproject.toml`, `api/settings.py`)
- [ ] **Task 9**: Final verification gate (`pytest` >= 80% coverage, `ruff`, `mypy`, secret scan, real E2E run) & Draft PR delivery

---

## 2. Acceptance Criteria Status

| # | Status | Evidence |
|---|--------|----------|
| AC1 | 🟡 PENDING | `packages` SQLite table created idempotently with proper indices on `tenant_id`, `unit_id`, `status` |
| AC2 | 🟡 PENDING | Package intake validates carrier, generates secure 6-digit PIN, sets status to `delivered`, fires `package.delivered` webhook |
| AC3 | 🟡 PENDING | Package pickup verifies secure PIN; sets status `picked_up`, records `picked_up_at`, fires `package.picked_up` webhook; invalid PIN rejected |
| AC4 | 🟡 PENDING | Summary metrics report total packages, pending count, picked up count, return count, carrier breakdown, and average pickup turnaround hours |
| AC5 | 🟡 PENDING | Resident prompt context automatically includes `[RESIDENT PACKAGES & PARCEL DELIVERIES]` when deliveries exist |
| AC6 | 🟡 PENDING | Macro variables `{package_carrier}`, `{package_tracking_number}`, `{package_status}`, `{package_pickup_pin}`, `{package_location}`, `{pending_packages_count}` resolve accurately |
| AC7 | 🟡 PENDING | Streamlit UI renders Deliveries Board, Package Intake Form, Locker Metrics, and Session Quick Intake widget with full interactive controls |
| AC8 | 🟡 PENDING | 100% CI parity: local pytest (>=80% coverage), ruff clean, mypy clean, secret scan clean, real E2E API run, and remote GitHub Actions CI green |

---

## 3. Decision Log

| # | Decision | Options considered | Repository evidence |
|---|----------|--------------------|---------------------|
| D1 | Branch `phase/v0.42.0-resident-packages` from `origin/main` | Continue on merged v0.41.0 branch | PR #13 merged into main; clean branch follows git lifecycle |
| D2 | Maintain untouched pre-existing user files (`uv.lock`, `write_pages.py`) | Stage or delete them | Hard Rule #1: Protect user work and git history |
| D3 | Modularize package engine in dedicated `api/packages.py` | Add directly into `db_utils.py` | Follows modular domain pattern (like `api/vendors.py`, `api/inspections.py`, `api/lease_renewals.py`) avoiding bloating `db_utils.py` |
| D4 | Store numeric 6-digit secure PIN for package pickup | Plaintext string without format constraint | Standardizes self-service parcel locker hardware interaction and resident verification PIN UX |

---

## 4. CI & Validation Log

| Check | Command | Result |
|-------|---------|--------|
| Baseline CI (remote, main) | gh run list --branch main | ✅ PR #13 merged with green CI |
| Local pytest baseline | python -m pytest | ✅ 867 passed, 92.67% coverage |
| Local lint baseline | python -m ruff check api/ app/ tests/ scripts/ | ✅ exit 0 (clean) |
| Local typecheck baseline | python -m mypy api/ app/ scripts/ | ✅ exit 0 (33 source files) |
