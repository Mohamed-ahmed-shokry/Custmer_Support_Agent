# v0.44.0 Progress Record: Parking Management, Permit Passes & Vehicle Directory Engine

**Phase Branch**: phase/v0.44.0-parking-management  
**Status**: 🟡 IN PROGRESS  
**Target Version**: 0.44.0  
**Plan**: see ROADMAP.md ("v0.44.0 plan")

---

## 1. Task Breakdown & Execution Status

- [x] **Task 1**: Update ROADMAP.md & initialize docs/PROGRESS.md with v0.44.0 plan
- [ ] **Task 2**: Parking engine database schema & helpers (`api/parking.py`) + tests in `tests/test_parking.py`
- [ ] **Task 3**: Pydantic schemas & webhook registration in `api/pydantic_models.py` and `api/db_utils.py` + tests in `tests/test_models.py`
- [ ] **Task 4**: FastAPI endpoints in `api/main.py` + route tests in `tests/test_parking_routes.py`
- [ ] **Task 5**: Context grounding & macro variable resolution in `api/tenant_context.py` + tests in `tests/test_tenant_context.py`
- [ ] **Task 6**: Streamlit client API helpers in `app/api_utils.py` + unit tests in `tests/test_app_api_utils.py`
- [ ] **Task 7**: Streamlit UI components in `app/sidebar.py` + UI tests in `tests/test_app_ui.py`
- [ ] **Task 8**: Documentation updates (`docs/API.md`, `README.md`) and version bump to `0.44.0` (`pyproject.toml`, `api/settings.py`)
- [ ] **Task 9**: Final verification gate (`pytest` >= 80% coverage, `ruff`, `mypy`, secret scan, real E2E run) & Draft PR delivery

---

## 2. Acceptance Criteria Status

| # | Status | Evidence |
|---|--------|----------|
| AC1 | 🟡 PENDING | SQLite tables `parking_spots`, `resident_vehicles`, `visitor_parking_passes`, and `parking_violations` created idempotently with proper indices and pre-seeded default parking spots |
| AC2 | 🟡 PENDING | Vehicle registration enforces unique license plate validation and associates vehicle with tenant and unit |
| AC3 | 🟡 PENDING | Visitor parking pass issuance generates unique pass codes and enforces expiration windows |
| AC4 | 🟡 PENDING | Parking violations record incident details, license plates, violation types, and fine amounts |
| AC5 | 🟡 PENDING | Summary metrics report total spots, occupied spots, registered vehicles, active visitor passes, and pending violations |
| AC6 | 🟡 PENDING | Active resident chat prompt context automatically injects `[RESIDENT VEHICLES & PARKING PASSES]` when parking or vehicle records exist |
| AC7 | 🟡 PENDING | Canned macro variables `{assigned_parking_spot}`, `{vehicle_plate}`, `{vehicle_make_model}`, `{permit_number}`, `{active_visitor_pass}`, `{visitor_pass_code}`, `{visitor_pass_expires}` resolve accurately |
| AC8 | 🟡 PENDING | Streamlit UI renders Spots Directory, Vehicles, Visitor Passes, Violations, Metrics, and Session Quick Pass widget |
| AC9 | 🟡 PENDING | 100% CI parity: local pytest (>=80% coverage), ruff clean, mypy clean, secret scan clean, real E2E API run, and remote GitHub Actions CI green |

---

## 3. Decision Log

| # | Decision | Options considered | Repository evidence |
|---|----------|--------------------|---------------------|
| D1 | Branch `phase/v0.44.0-parking-management` created from `main` | Continue on previous phase branch | Follows Git branch lifecycle rules |
| D2 | Modularize parking domain logic in dedicated `api/parking.py` | Add directly into `db_utils.py` | Follows domain patterns established by `api/amenities.py`, `api/packages.py`, `api/vendors.py`, `api/inspections.py` |
| D3 | Maintain pre-existing untracked files (`uv.lock`, `write_pages.py`) untouched | Stage or delete them | Hard Rule #1: Protect user work and Git history |

---

## 4. CI & Validation Log

| Check | Command | Result |
|-------|---------|--------|
| Baseline CI (remote, main) | `gh run list --branch main` | ✅ Run #41270519200 passed (PR #15 merged) |
| Local lint baseline | `python -m ruff check api/ app/ tests/ scripts/` | ✅ Clean (0 issues) |
| Local typecheck baseline | `python -m mypy api/ app/ scripts/` | ✅ Clean (0 issues in 35 source files) |
