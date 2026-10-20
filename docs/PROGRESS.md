# v0.40.0 Progress Record: Maintenance Vendor Directory, Work Order Vendor Dispatch & Vendor Performance Metrics

**Phase Branch**: `phase/v0.40.0-maintenance-work-orders`  
**Status**: 🚧 IN PROGRESS  
**Target Version**: 0.40.0  
**Plan**: see `ROADMAP.md` ("v0.40.0 plan")

---

## 1. Task Breakdown & Execution Status

- [x] **Task 1**: ROADMAP v0.40.0 plan and `docs/PROGRESS.md` re-initialization
- [x] **Task 2**: `api/vendors.py` constants, table schema, bootstrap and seeds + tests
- [x] **Task 3**: Vendor validation helpers + create/get vendor + tests
- [x] **Task 4**: list/update/delete vendor + tests
- [x] **Task 5**: dispatch_vendor + tests
- [x] **Task 6**: complete_dispatch, list_dispatches + tests
- [x] **Task 7**: vendor summary metrics + tests
- [x] **Task 8**: webhook events registration + test
- [ ] **Task 9**: Pydantic models + tests
- [ ] **Task 10**: FastAPI routes + route lifecycle test
- [ ] **Task 11**: client helpers + tests
- [ ] **Task 12**: docs, version bump
- [ ] **Task 13**: final verification, e2e run, remote CI green, draft PR

---

## 2. Acceptance Criteria Status

See `ROADMAP.md` for the numbered criteria; evidence is recorded here as tasks complete.

| # | Status | Evidence |
|---|--------|----------|
| AC1-AC10 | ⏳ PENDING | — |

---

## 3. Decision Log

| # | Decision | Options considered | Repository evidence |
|---|----------|--------------------|---------------------|
| D1 | Branch from `origin/main` as `phase/v0.40.0-maintenance-work-orders` | Reuse the merged v0.39.0 branch | PR #11 for v0.39.0 is already merged into `main` |
| D2 | Phase = vendor directory and work-order dispatch | Streamlit UI work, macro variables, RAG grounding | v0.36.0 work orders have a free-text `assigned_to` only; vendor dispatch is the smallest end-to-end extension |
| D3 | New self-contained `api/vendors.py` module (own tables) instead of altering `work_orders` | Add `vendor_id` column + migration to `work_orders` | Avoids changing `WorkOrderItem` schema and migrations; `api/inspections.py` sets the module-per-feature precedent |
| D4 | Leave pre-existing untracked `uv.lock` and `write_pages.py` untouched | — | Not authored by the agent |

---

## 4. CI & Validation Log

| Check | Command | Result |
|-------|---------|--------|
| Baseline CI (remote, `main`) | `gh run list` | ✅ run 39156988777 success |
