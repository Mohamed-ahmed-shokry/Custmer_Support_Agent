# v0.41.0 Progress Record: Maintenance Vendor Operations Board, Work Order Dispatch UI & Grounded Vendor Macro Variables

**Phase Branch**: phase/v0.41.0-vendor-operations-ui  
**Status**: 🚧 IN PROGRESS  
**Target Version**: 0.41.0  
**Plan**: see ROADMAP.md ("v0.41.0 plan")

---

## 1. Task Breakdown & Execution Status

- [x] **Task 1**: Update ROADMAP.md (mark v0.40.0 complete, add v0.41.0 plan) & initialize docs/PROGRESS.md
- [x] **Task 2**: Grounding engine: vendor dispatch info in prompt context + tests in tests/test_tenant_context.py
- [x] **Task 3**: Macro variable resolution: vendor variables + tests in tests/test_tenant_context.py
- [x] **Task 4**: Streamlit UI: vendor directory tab + tests in tests/test_app_ui.py
- [x] **Task 5**: Streamlit UI: register vendor tab + tests in tests/test_app_ui.py
- [x] **Task 6**: Streamlit UI: work order inline vendor dispatch & completion + tests in tests/test_app_ui.py
- [x] **Task 7**: Streamlit UI: vendor performance KPIs tab + tests in tests/test_app_ui.py
- [ ] **Task 8**: Streamlit UI: integrate vendor navigation into maintenance board + tests in tests/test_app_ui.py
- [ ] **Task 9**: Documentation (docs/API.md, README.md) & version bump to 0.41.0
- [ ] **Task 10**: Final verification gate (pytest, ruff, mypy, remote CI green) & Draft PR delivery

---

## 2. Acceptance Criteria Status

See ROADMAP.md for numbered criteria; evidence is recorded here as tasks complete.

| # | Status | Evidence |
|---|--------|----------|
| AC1 | ✅ PASSED | Prompt context includes assigned vendor name, trade, dispatch status, and phone |
| AC2 | ✅ PASSED | Macro variables ({vendor_name}, {vendor_trade}, {vendor_phone}, etc.) resolved in templates |
| AC3 | ⏳ PENDING | Maintenance board vendor tabs navigation |
| AC4 | ✅ PASSED | Vendor directory tab renders cards, trade badges, rates, contact, and status toggles |
| AC5 | ✅ PASSED | Vendor registration form validates input and registers vendor via API |
| AC6 | ✅ PASSED | Open work orders provide 1-click active vendor dispatch via API |
| AC7 | ✅ PASSED | Dispatched work orders provide inline completion with final cost and 1-5 rating |
| AC8 | ✅ PASSED | Vendor performance KPIs tab renders portfolio KPIs and contractor scorecards |
| AC9 | ⏳ PENDING | 100% CI parity (tests, ruff, mypy) and remote CI green |

---

## 3. Decision Log

| # | Decision | Options considered | Repository evidence |
|---|----------|--------------------|---------------------|
| D1 | Branch phase/v0.41.0-vendor-operations-ui from origin/main | Continue on merged v0.40.0 branch | PR #12 is merged into main; clean branch follows git lifecycle |
| D2 | Embed Vendor operations directly inside the existing 🛠️ Maintenance & Work Orders sidebar expander | Create a new top-level sidebar expander | Follows single maintenance hub pattern; keeps sidebar uncluttered and co-locates work orders with contractor dispatching |
| D3 | Extract vendor dispatch context for grounding from work orders rather than requiring tenant-vendor DB tables | Add new tenant_vendor associations | In v0.40.0, work orders link to vendors through endor_dispatches and ssigned_to; querying via work order ID is clean and zero-migration |
| D4 | Maintain untouched pre-existing user files (uv.lock, write_pages.py) | Stage or delete them | Hard Rule #1: Protect user work and git history |

---

## 4. CI & Validation Log

| Check | Command | Result |
|-------|---------|--------|
| Baseline CI (remote, main) | gh run list --branch main | ✅ run 40046016269 success |