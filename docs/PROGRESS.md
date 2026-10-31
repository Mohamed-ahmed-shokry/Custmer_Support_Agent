# v0.43.0 Progress Record: Community Amenity Reservations & Common Area Bookings Engine

**Phase Branch**: phase/v0.43.0-amenity-reservations  
**Status**: 🟡 IN PROGRESS  
**Target Version**: 0.43.0  
**Plan**: see ROADMAP.md ("v0.43.0 plan")

---

## 1. Task Breakdown & Execution Status

- [x] **Task 1**: Update ROADMAP.md & initialize docs/PROGRESS.md with v0.43.0 plan
- [ ] **Task 2**: Amenity & reservation database engine (`api/amenities.py`) + tests in `tests/test_amenities.py`
- [ ] **Task 3**: Pydantic models & webhook event registration in `api/pydantic_models.py` and `api/db_utils.py`
- [ ] **Task 4**: FastAPI endpoints in `api/main.py` + route tests in `tests/test_amenity_routes.py`
- [ ] **Task 5**: Context grounding & macro variable resolution in `api/tenant_context.py` + tests in `tests/test_tenant_context.py`
- [ ] **Task 6**: Streamlit client API helpers in `app/api_utils.py` + unit tests in `tests/test_app_api_utils.py`
- [ ] **Task 7**: Streamlit UI components in `app/sidebar.py` (Reservations board, booking form, catalog, metrics, session widget) + tests in `tests/test_app_ui.py`
- [ ] **Task 8**: Documentation updates (`docs/API.md`, `README.md`) and version bump to `0.43.0` (`pyproject.toml`, `api/settings.py`)
- [ ] **Task 9**: Final verification gate (`pytest` >= 80% coverage, `ruff`, `mypy`, secret scan, real E2E run) & Draft PR delivery

---

## 2. Acceptance Criteria Status

| # | Status | Evidence |
|---|--------|----------|
| AC1 | 🟡 PENDING | `amenities` and `amenity_reservations` SQLite tables created idempotently with proper indices and pre-seeded default amenities |
| AC2 | 🟡 PENDING | Overlapping reservation conflict checking rejects double-bookings with HTTP 409 Conflict |
| AC3 | 🟡 PENDING | Total fees and security deposits automatically calculated based on duration hours and rates |
| AC4 | 🟡 PENDING | Reservation status transitions (`pending`, `confirmed`, `cancelled`, `completed`) trigger corresponding webhooks |
| AC5 | 🟡 PENDING | Summary metrics calculate reservations count, revenue, deposits held, and utilization breakdown |
| AC6 | 🟡 PENDING | Active resident chat prompt context automatically injects `[COMMUNITY AMENITY RESERVATIONS]` when bookings exist |
| AC7 | 🟡 PENDING | Canned macro variables `{amenity_name}`, `{reservation_start}`, `{reservation_end}`, `{reservation_status}`, `{reservation_fee}`, `{reservation_deposit}` resolve dynamically |
| AC8 | 🟡 PENDING | Streamlit UI renders Reservations Board, Book Amenity Form, Amenity Catalog, Metrics, and Session Quick Booking widget |
| AC9 | 🟡 PENDING | 100% CI parity: local pytest (>=80% coverage), ruff clean, mypy clean, secret scan clean, real E2E API run, and remote GitHub Actions CI green |

---

## 3. Decision Log

| # | Decision | Options considered | Repository evidence |
|---|----------|--------------------|---------------------|
| D1 | Branch `phase/v0.43.0-amenity-reservations` created from `main` | Continue on previous branch | Follows Git branch lifecycle rules |
| D2 | Modularize amenity reservation engine in dedicated `api/amenities.py` | Add directly into `db_utils.py` | Follows modular domain pattern (e.g. `api/packages.py`, `api/vendors.py`, `api/inspections.py`) |
| D3 | Maintain pre-existing untracked files (`uv.lock`, `write_pages.py`) untouched | Stage or delete them | Hard Rule #1: Protect user work and Git history |

---

## 4. CI & Validation Log

| Check | Command | Result |
|-------|---------|--------|
| Baseline CI (remote, main) | `gh run list --branch main` | ✅ Run #40998451624 passed (PR #14 merged) |
| Local lint baseline | `python -m ruff check api/ app/ tests/ scripts/` | ✅ Clean (0 issues) |
| Local typecheck baseline | `python -m mypy api/ app/ scripts/` | ✅ Clean (0 issues in 34 source files) |
