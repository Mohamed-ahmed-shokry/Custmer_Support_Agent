# Phase Execution Progress: v0.45.0

## Phase Scope: Resident Pet Registry, Animal Policies, Vaccination Records & Service Animal Verification Engine
Comprehensive pet registry, vaccination health tracking, service/assistance animal (ESA) verification, community policy rules and fees, noise/barking complaint logging, conversational RAG grounding, and Streamlit management hub.

## Acceptance Criteria Status

- [ ] **AC1: SQLite Database Tables & Schema Migration (`api/pets.py`)**
  - Tables `resident_pets`, `pet_policies`, and `pet_incidents` bootstrapped with UUID/hex primary keys, foreign references to `units` and `tenants`, indexing on lookup keys, and pre-seeded default pet and policy.
- [ ] **AC2: Pydantic Validation Schemas & Enums (`api/pydantic_models.py`)**
  - Request/response schemas for pets, policies, infractions, and summary KPIs with full field validations.
- [ ] **AC3: FastAPI Endpoints & Webhook Dispatch (`api/main.py`, `api/db_utils.py`)**
  - RESTful endpoints for pets, policies, incidents, metrics, and webhook triggers for `pet.registered`, `pet_vaccination.expiring`, `pet_incident.logged`, and `pet_policy.updated`.
- [ ] **AC4: Active Session 1-Click Pet Registration (`api/main.py`)**
  - `POST /sessions/{id}/register-pet` grounds pet registration directly to the resident and unit linked to the current support session.
- [ ] **AC5: Conversational RAG Prompt Grounding (`api/tenant_context.py`)**
  - Prompt context formats resident pets and building policy rules under `[RESIDENT PETS & ANIMAL POLICIES]`.
- [ ] **AC6: Macro Variable Resolution (`api/tenant_context.py`)**
  - Template variables `{registered_pets_count}`, `{pet_names}`, `{primary_pet_breed}`, `{pet_vaccination_status}`, `{pet_rent_monthly}`, `{pet_deposit_amount}`, and `{service_animal_verified}` auto-resolve.
- [ ] **AC7: Typed Frontend API Client Helpers (`app/api_utils.py`)**
  - Client functions wrapping all pet endpoints with structured error handling.
- [ ] **AC8: Streamlit Sidebar Management Board & Session Widget (`app/sidebar.py`)**
  - Interactive "🐾 Pet Registry & Animal Policies" sidebar board (Pets Directory, Policies, Incidents, Vaccination Watch, KPIs) and "🐾 Quick Pet Registration" 1-click resident widget.
- [ ] **AC9: 100% Green Verification Gate & remote CI**
  - `ruff` clean, `mypy` clean, secret scan clean, 100% test pass rate with coverage >= 80%.

## Commit Log
