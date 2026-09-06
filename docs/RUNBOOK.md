# Runbook

## Service won't start: `OPENAI_API_KEY` missing

- Symptom: chat/indexing calls fail with authentication errors.
- Fix: copy `.env.example` to `.env`, set `OPENAI_API_KEY`, restart the API.

## Uploads fail with 413

- Symptom: `File exceeds the N MB upload limit.`
- Fix: raise `MAX_UPLOAD_MB` or compress/split the source document.

## Indexing fails repeatedly

- Check `app.log` for `Indexing attempt x/3 failed`.
- Causes: no OpenAI credits/network, corrupt PDF, Chroma lock contention.
- Fix: verify billing + connectivity, retry the upload (writes use
  deterministic `{file_id}:{chunk}` IDs, so retries are idempotent).

## Readiness probe failing

- `GET /health/ready` returns 503 with per-check detail.
- `sqlite: error` → check `SQLITE_DB_PATH` is writable.
- `chroma_dir: error` → check `CHROMA_PERSIST_DIR` is writable.

## 401 / 429 responses

- 401: `API_KEY` is configured — clients must send `X-API-Key`.
  Health, metrics, and docs paths stay public.
- 429: `RATE_LIMIT_PER_MIN` exceeded — back off; raise the limit if the
  traffic is legitimate. Or the daily token budget is spent — check
  `GET /quota` and raise `TOKEN_DAILY_BUDGET_EST` if appropriate.

## Metrics review

- `GET /metrics.json`: counters plus `latency_avg_seconds_{chat,stream,upload,other}`
  and `prompt_tokens_est` / `completion_tokens_est`.
- Rising `chat_errors` with 502s → inspect the retrieval pipeline and
  OpenAI status; `upload_errors` → see indexing section above.

## Session management

- List past conversations with `GET /sessions` (includes a `preview` of the
  first question); reload one with `GET /sessions/{id}/history`.
- Remove one with `DELETE /sessions/{id}` (also available in the Streamlit
  sidebar). Deletion only clears chat history, never documents.
