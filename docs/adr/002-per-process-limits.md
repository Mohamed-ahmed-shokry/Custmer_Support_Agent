# ADR-002: Per-process rate limits, quotas, and metrics

- Status: accepted
- Date: 2026-09-04
- Context: rate limiting (`api/security.py`), token quotas, and metrics
  (`api/observability.py`) keep state in process memory with no external
  store. The production compose overlay runs 2 uvicorn workers, so each
  process enforces its own budget and reports its own counters.
- Decision: keep in-memory enforcement (no Redis dependency) and treat the
  configured limits as per-process. Operators running multiple workers
  should divide the intended global budget across workers or accept
  approximately N-times headroom for N workers. Stale quota days and idle
  rate-limit windows are evicted on write so state stays bounded.
- Consequences: limits are approximate under multi-worker deployments;
  metrics from `/metrics` must be aggregated across replicas. Revisit with
  a shared store if exact global enforcement is ever required.
