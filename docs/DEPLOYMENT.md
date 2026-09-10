# Deployment Guide

## Pre-flight checklist

- Copy `.env.example` to `.env` and set `OPENAI_API_KEY`.
- For any multi-user exposure, also set `API_KEY`,
  `RATE_LIMIT_PER_MIN`, and `TOKEN_DAILY_BUDGET_EST` (see `docs/API.md`).
- Confirm persistent storage for `/data` (`CHROMA_PERSIST_DIR` and
  `SQLITE_DB_PATH` both live there in containers).

## Environments

| Concern | Local | Staging | Production |
|---|---|---|---|
| Compose files | `docker-compose.yml` | `docker-compose.yml` | `docker-compose.yml` + `docker-compose.prod.yml` |
| API workers | 1 (reload) | 1 | 2 |
| Log format | `text` | `json` | `json` |
| Auth | off | `API_KEY` on | `API_KEY` on |
| Rate limit / quotas | off | on, generous | on, tuned from `/metrics.json` |
| Ingress | localhost | private network | TLS reverse proxy only |
| Backups | none | volume snapshots | volume snapshots + tested restore |

## Docker Compose (development)

```powershell
Copy-Item .env.example .env
docker compose up --build
```

- API: `http://localhost:8000` (`/docs` serves OpenAPI/Swagger).
- UI: `http://localhost:8501`.
- Data persists in the `rag-data` volume.

## Docker Compose (production overlay)

```powershell
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

The overlay switches the API to 2 uvicorn workers, JSON logs, restart
policies, and memory/CPU limits. Put a TLS-terminating reverse proxy in
front and restrict ingress to it.

## Kubernetes

Apply the generic manifests, then create the secret referenced by the
Deployment (values from your `.env`):

```bash
kubectl apply -f k8s/deployment.yaml
kubectl create secret generic rag-agent-secrets \
  --from-literal=OPENAI_API_KEY='<key>' \
  --from-literal=API_KEY='<key>' \
  --dry-run=client -o yaml | kubectl apply -f -
```

- Liveness: `GET /health/live`; readiness: `GET /health/ready`.
- Metrics: scrape `/metrics` (Prometheus text) or read `/metrics.json`.
- Storage: the `rag-data` PVC holds Chroma + SQLite; back it up with your
  cluster's volume-snapshot tooling.

## First-run verification

1. `GET /health/ready` returns `{"ready": true, ...}`.
2. Upload a document through the UI or `POST /upload-doc`.
3. Ask a question grounded in that document via `POST /chat`.
4. Check `GET /metrics.json` for request counters and latency averages.
