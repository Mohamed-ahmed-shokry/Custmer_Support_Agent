# v0.38.0 Progress Record: Lease Renewal Offers, Addenda, Digital Agreements & E-Sign Engine

**Phase Branch**: `phase/v0.38.0-lease-renewals-documents`  
**Status**: 🟡 IN PROGRESS  
**Target Version**: 0.38.0  

---

## 1. Task Breakdown & Execution Status

- [ ] **Task 1**: `ROADMAP.md` v0.38.0 plan specification and `docs/PROGRESS.md` initialization
- [ ] **Task 2**: Database schema, table creation, default seed data, and CRUD operations for `lease_renewals` in `api/db_utils.py` + unit tests in `tests/test_db_utils.py`
- [ ] **Task 3**: Digital signing and tenant lease update logic in `api/db_utils.py` + unit tests in `tests/test_db_utils.py`
- [ ] **Task 4**: Agreement Markdown synthesis and RAG document publishing in `api/lease_renewals.py` + unit tests in `tests/test_lease_renewals.py`
- [ ] **Task 5**: Context grounding engine integration for lease renewals in `api/tenant_context.py` + unit tests in `tests/test_tenant_context.py`
- [ ] **Task 6**: Pydantic request/response schemas in `api/pydantic_models.py` + unit tests in `tests/test_models.py`
- [ ] **Task 7**: FastAPI endpoints for lease renewals, signing, and session offer creation in `api/main.py` + route tests in `tests/test_api_routes.py`
- [ ] **Task 8**: Streamlit client API helpers in `app/api_utils.py` + unit tests in `tests/test_app_api_utils.py`
- [ ] **Task 9**: Streamlit UI components in `app/sidebar.py` (session renewal offer widget & "📝 Lease Renewals & Documents" panel) + UI tests in `tests/test_app_ui.py`
- [ ] **Task 10**: Documentation updates (`docs/API.md`, `README.md`) and version bump to `0.38.0` (`pyproject.toml`, `api/settings.py`)
- [ ] **Task 11**: Final verification gate (`pytest` >= 80% coverage, `ruff check`, `mypy`), progress record completion, and draft PR delivery

---

## 2. Acceptance Criteria Status

| # | Acceptance Criterion | Status | Evidence |
|---|----------------------|--------|----------|
| AC1 | `lease_renewals` SQLite table is created, pre-seeded with defaults, and supported with full CRUD, filtering, signing, and portfolio metrics in `api/db_utils.py` | ⏳ PENDING | Will verify via unit tests in `tests/test_db_utils.py` |
| AC2 | `sign_lease_renewal()` records digital signature and automatically updates tenant's `lease_start`, `lease_end`, and `monthly_rent` in `tenants` | ⏳ PENDING | Will verify in `tests/test_db_utils.py` |
| AC3 | `api/lease_renewals.py` synthesizes structured Markdown renewal agreements and publishes them into `document_store` and Chroma | ⏳ PENDING | Will verify in `tests/test_lease_renewals.py` |
| AC4 | `api/tenant_context.py` augments grounding prompt context with `[LEASE RENEWAL OFFERS & AGREEMENTS]` and auto-resolves renewal macro variables | ⏳ PENDING | Will verify in `tests/test_tenant_context.py` |
| AC5 | Webhook events `lease_renewal.offered`, `lease_renewal.accepted`, `lease_renewal.signed`, and `lease_renewal.declined` trigger correctly on renewal events | ⏳ PENDING | Will verify in `tests/test_db_utils.py` and `tests/test_api_routes.py` |
| AC6 | Pydantic schemas in `api/pydantic_models.py` validate renewal creation, updates, signing, and summary responses | ⏳ PENDING | Will verify in `tests/test_models.py` |
| AC7 | FastAPI endpoints `/lease-renewals/*`, `/sessions/{id}/create-lease-renewal`, and `/tenants/{id}/lease-renewals` are wired and tested | ⏳ PENDING | Will verify in `tests/test_api_routes.py` |
| AC8 | Client helpers in `app/api_utils.py` provide typed methods with `X-API-Key` forwarding and resilient error handling | ⏳ PENDING | Will verify in `tests/test_app_api_utils.py` |
| AC9 | Streamlit UI in `app/sidebar.py` provides the 1-click renewal offer generator in session card and the "📝 Lease Renewals & Documents" management panel | ⏳ PENDING | Will verify in `tests/test_app_ui.py` |
| AC10 | Documentation (`README.md`, `docs/API.md`, `ROADMAP.md`, `docs/PROGRESS.md`) and version bump to `0.38.0` (`pyproject.toml`, `api/settings.py`) are complete | ⏳ PENDING | Will verify across updated documentation files |
| AC11 | Full verification suite (`pytest` with >= 80% coverage, `ruff check`, `mypy`) passes with zero regressions | ⏳ PENDING | Baseline 100% green; will re-verify at completion gate |

---

## 3. Decision Log

- **Decision 1 (2026-10-17)**: Select **v0.38.0 — Lease Renewal Offers, Addenda, Digital Agreements & E-Sign Engine** as the development phase.
  - *Context*: Following v0.35.0 (Tenant & Property Directory), v0.36.0 (Maintenance Work Orders & Dispatch), and v0.37.0 (Resident Billing & Ledgers), lease expirations, renewal inquiries, rate negotiations, and agreement execution represent the remaining top operational customer support workflow in property management.
  - *Alternatives considered*: Voice call transcription ingestion (requires external audio processing models) or third-party CRM sync (breaks zero-external-dependency contract).
  - *Rationale*: A local-first lease renewal lifecycle engine (`lease_renewals`) complete with contract synthesis, e-signature recording, automatic tenant lease term update, RAG context grounding, and knowledge store publishing closes the loop on property management leasing operations cleanly and deterministically.
  - *Blast radius & Reversibility*: Additive SQLite table `lease_renewals`, additive webhook events (`lease_renewal.*`), additive context block `[LEASE RENEWAL OFFERS & AGREEMENTS]`, new `api/lease_renewals.py` module, and isolated `/lease-renewals/*` endpoints.

---

## 4. Validation Commands & Results

- **Baseline Check (v0.37.0 on main)**:
  - `python -m ruff check api/ app/ tests/ scripts/` -> ✅ Passed (`All checks passed!`)
  - `python -m mypy api/ app/ scripts/` -> ✅ Passed (`Success: no issues found in 26 source files`)
  - `python -m pytest -q` -> ✅ Passed (`374 passed, 2 skipped, 3 warnings, 99.58% coverage`)
