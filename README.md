# Customer Support RAG Agent (v0.41.0)

A local-first customer support assistant for real estate and property management workflows. The app combines a FastAPI backend, a Streamlit chat UI, SQLite chat/document metadata, and a local Chroma vector store backed by OpenAI embeddings.

## Features

- Resident Move-In/Move-Out Inspections, Turnover Punchlists & Security Deposit Accounting Engine (`POST /inspections`, `GET /inspections`, `GET /inspections/metrics`, `GET /inspections/{id}`, `PATCH /inspections/{id}`, `DELETE /inspections/{id}`, `POST /inspections/{id}/complete`, `POST /inspections/{id}/convert-to-work-order`, `POST /inspections/{id}/publish-document`, `POST /sessions/{id}/create-inspection`, `GET /tenants/{id}/inspections`, `GET /units/{id}/inspections`): end-to-end turnover management tracking condition checklists by room and item (`inspections` table in SQLite), damage condition ratings, estimated vs. actual repair deductions, security deposit accounting with net refund calculations, key tracking, and direct conversion of punchlist deficiencies into maintenance work orders (`work_orders`). Synthesizes structured Markdown inspection condition statements and indexes them into Chroma vector storage (`publish_inspection_document`), triggers real-time webhooks (`inspection.scheduled`, `inspection.completed`, `inspection.deposit_deductions_assessed`, `inspection.keys_returned`), injects verified condition context into conversational prompt grounding (`[RESIDENT INSPECTIONS, MOVE-IN/OUT & DEPOSIT SETTLEMENT]`), and auto-resolves macro variables (`{inspection_type}`, `{inspection_status}`, `{inspection_date}`, `{total_estimated_deductions}`, `{net_deposit_refund}`, `{keys_returned}`).
- Maintenance Vendor Directory, Work Order Dispatch & Vendor Performance Metrics (`POST /vendors`, `GET /vendors`, `GET /vendors/metrics`, `GET /vendors/{id}`, `PATCH /vendors/{id}`, `DELETE /vendors/{id}`, `GET /vendors/{id}/dispatches`, `GET /work-orders/{id}/dispatches`, `POST /work-orders/{id}/dispatch-vendor`, `POST /vendor-dispatches/{id}/complete`): self-contained `vendors` and `vendor_dispatches` SQLite tables with seeded sample vendors, trade/status filters, dispatch validation (unknown/inactive vendors, closed work orders and duplicate active dispatches are rejected), automatic `assigned_to` and `scheduled` work-order transitions, completion with final cost and 1-5 rating, vendor performance metrics (completion rate, average rating, total spend), webhooks `vendor.dispatched` and `vendor.job_completed`, RAG prompt context grounding for dispatched contractors, and auto-resolving vendor macro variables (`{vendor_name}`, `{vendor_trade}`, `{vendor_phone}`, `{vendor_hourly_rate}`, `{vendor_dispatch_status}`, `{vendor_agreed_cost}`). Typed client helpers live in `app/api_utils.py`.
- Streamlit Vendor Operations Board & Inline Work Order Dispatch: dedicated interactive tabs inside the "🛠️ Maintenance & Work Orders" sidebar expander for browsing contractors by trade/status with hourly rates and ratings, registering new vendors with form validation, inline 1-click vendor dispatching on open work orders with agreed cost and scheduled date, inline dispatch completion with 1-5 star ratings and resolution notes, and portfolio contractor performance & spend KPIs.
- Streamlit Move-In/Out Inspections Board & 1-Click Session Inspection Scheduling Widget: live "📋 Move-In/Out Inspections" card directly inside the active session resident card for 1-click move-in/out and punchlist inspection scheduling with auto-resolved tenant/unit details, plus a dedicated "📋 Move-In/Out & Inspections" sidebar panel with tabbed navigation: filterable inspection records with 1-click status lifecycle actions (`▶️ Start`, `✅ Complete & Settle Deposit`, `🗑️ Delete`), inline punchlist deficiency viewer with 1-click `🛠️ WO` maintenance dispatch, 1-click Markdown report RAG indexing, manual inspection scheduling form, and portfolio turnover KPI dashboard.
- Lease Renewal Offers, Addenda, Digital Agreements & E-Sign Engine (`POST /lease-renewals`, `GET /lease-renewals`, `GET /lease-renewals/metrics`, `GET /lease-renewals/{id}`, `PATCH /lease-renewals/{id}`, `DELETE /lease-renewals/{id}`, `POST /lease-renewals/{id}/sign`, `POST /lease-renewals/{id}/publish`, `POST /sessions/{id}/create-lease-renewal`, `GET /tenants/{id}/lease-renewals`): full leasing lifecycle tracking renewal offers and digital agreements (`lease_renewals` table in SQLite) with proposed rent, term months (6, 12, 18, 24), start/end dates, concession incentives, security deposit adjustments, offer expiration deadlines, and status workflow (`draft`, `offered`, `accepted`, `signed`, `declined`, `expired`). Supports atomic digital e-signing (`sign_lease_renewal`) that automatically advances tenant lease dates and updates active rent in `tenants`, automated legal Markdown agreement synthesis and RAG vector store publishing (`publish_lease_renewal_document`), portfolio renewal conversion analytics, and real-time webhook events (`lease_renewal.offered`, `lease_renewal.accepted`, `lease_renewal.signed`, `lease_renewal.declined`). Active support sessions automatically ground pending/offered renewal proposals into prompt context (`[LEASE RENEWAL OFFERS & AGREEMENTS]`), and macro variables auto-resolve (`{renewal_id}`, `{renewal_proposed_rent}`, `{renewal_current_rent}`, `{renewal_term_months}`, `{renewal_status}`, `{renewal_start_date}`, `{renewal_end_date}`, `{renewal_expires_at}`, `{renewal_concession}`).
- Streamlit Lease Renewals Board & 1-Click Session Offer Widget: live "📝 Lease Renewal & Agreements" card inside active session metadata featuring 1-click renewal proposal generation with automatic 5% default rent calculation, terms, and concession inputs, plus inline digital e-signing; and a dedicated "📝 Lease Renewals & Documents" sidebar panel with interactive tabbed navigation for browsing renewal offers with status and term filters, manual renewal creation, 1-click agreement indexing into RAG, 1-click digital signing, and portfolio renewal conversion analytics.
- Resident Billing, Rent Ledgers, Invoices & Payment Operations Engine (`POST /billing/transactions`, `GET /billing/transactions`, `GET /billing/metrics`, `GET /billing/transactions/{id}`, `PATCH /billing/transactions/{id}`, `DELETE /billing/transactions/{id}`, `POST /tenants/{id}/payments`, `GET /tenants/{id}/ledger`, `POST /sessions/{id}/record-payment`): complete financial ledger and accounting lifecycle linking resident profiles (`tenants`) and units (`units`) with transaction tracking across charges (`rent`, `security_deposit`, `late_fee`, `utility`, `parking_fee`, `pet_rent`, `maintenance_charge`) and payments (`ach`, `credit_card`, `debit_card`, `check`, `money_order`, `cashier_check`, `online_portal`). Supports atomic payment recording, tenant balance reconciliation, automatic overdue charge resolution, portfolio financial metrics, and real-time webhook alerting (`billing.payment_received`, `billing.charge_posted`, `billing.late_fee_assessed`, `billing.overdue_escalated`). Active sessions automatically ground financial statements into conversational RAG context (`[RESIDENT FINANCIAL LEDGER & RENT BALANCE]`), and macro variables auto-resolve (`{overdue_balance}`, `{last_payment_amount}`, `{last_payment_date}`, `{last_payment_method}`).
- Streamlit Billing Board & 1-Click Resident Payment Widget: live "💳 Record Resident Payment" widget directly inside the active session resident card for 1-click invoice settlements and balance payoffs, plus a dedicated "💰 Billing & Rent Ledgers" sidebar panel with live financial KPIs (Billed, Collected, Outstanding, Collection Rate %), searchable filterable transaction ledger with status transitions (`Mark Paid`, `Waive`, `Delete`), resident payment processing form, and charge posting assessment form.
- Conversational customer support over uploaded PDF, DOCX, HTML, MD, TXT, and CSV documents.
- Maintenance Work Orders, Service Requests & Resident Dispatch Engine (`POST /work-orders`, `GET /work-orders`, `GET /work-orders/metrics`, `GET /work-orders/{id}`, `PATCH /work-orders/{id}`, `DELETE /work-orders/{id}`, `POST /sessions/{id}/create-work-order`, `GET /units/{id}/work-orders`, `GET /tenants/{id}/work-orders`): persistent maintenance repair tracking (`work_orders` table in SQLite) connected to property units and residents, tracking category (`plumbing`, `electrical`, `hvac`, `appliance`, `pest_control`, `structural`, `general`), priority (`low`, `medium`, `high`, `emergency`), status (`submitted`, `scheduled`, `in_progress`, `completed`, `cancelled`), entry permissions (`permission_granted`, `call_first`, `resident_must_be_present`), contractor/staff assignment, scheduled dates, and estimated vs. actual repair costs. Chat turns automatically ground open work orders into prompt context (`[ACTIVE MAINTENANCE WORK ORDERS]`), macro variables auto-resolve (`{open_work_orders_count}`, `{latest_work_order_id}`), and real-time webhook events (`work_order.created`, `work_order.emergency_escalated`, `work_order.status_changed`) alert operations and dispatch teams immediately.
- Streamlit Maintenance Board & 1-Click Resident Dispatch Widget: live "🛠️ Dispatch Work Order" expander directly on the active session resident card with 1-click conversion of conversational support sessions into persistent work orders with auto-resolved unit/tenant IDs, open work order unit warnings, plus a dedicated "🛠️ Maintenance & Work Orders" sidebar panel with live KPI cards (Total, Open, In Progress, Emergency), searchable filterable board with 1-click status transitions (`Start`, `Done`, `Delete`), new service request creation form, and cost tracking dashboard.
- Tenant Profiles, Property Unit Directory & Context Grounding Engine (`POST /units`, `GET /units`, `GET /units/{id}`, `PATCH /units/{id}`, `DELETE /units/{id}`, `POST /tenants`, `GET /tenants`, `GET /tenants/{id}`, `PATCH /tenants/{id}`, `DELETE /tenants/{id}`, `POST /sessions/{id}/link-tenant`, `GET /sessions/{id}/tenant-context`, `GET /tenants/{id}/support-history`): persistent property unit directory (`units`) tracking building, floor, parking spot, gate access code, and monthly rent, resident profiles (`tenants`) with lease start/end dates, current balance due, and emergency contacts, and support session-to-tenant linking (`session_labels`). Chat turns (`/chat` and `/chat/stream`) are automatically grounded with verified lease context, and canned macro variables (`{customer_name}`, `{unit_id}`, `{monthly_rent}`, `{balance_due}`) auto-resolve seamlessly.
- Streamlit Resident Context Card & Property Directory: live resident profile card in session metadata displaying lease dates, status, rent, balance due, and 1-click resident unlinking or linking, plus a dedicated "🏢 Tenant & Property Directory" sidebar panel with interactive tabs for managing tenants, property units, and resident support ticket histories.
- Knowledge Base Gap Detection, FAQ Article Drafting & Self-Service Deflection Engine (`POST /knowledge/gaps`, `GET /knowledge/gaps`, `PATCH /knowledge/gaps/{id}`, `POST /knowledge/gaps/scan`, `POST /knowledge/articles`, `POST /sessions/{id}/draft-article`, `GET /knowledge/articles`, `POST /knowledge/articles/{id}/publish`, `GET /knowledge/analytics`): closes the knowledge loop between customer support operations and the RAG corpus. Automatically scans escalated and low-CSAT conversations for unanswered questions, deduplicates recurring queries with frequency tracking (`knowledge_gaps`), synthesizes structured Markdown FAQ/KB drafts from resolved sessions (`knowledge_articles`), and publishes articles into the searchable vector library with 1 click while automatically resolving linked gaps and dispatching webhook notifications (`knowledge.gap_detected`, `knowledge.article_published`).
- Streamlit Knowledge Base Gaps & Article Studio: sidebar expander with live self-service coverage KPIs (total gaps, resolution rate %, published articles count, estimated ticket deflections), on-demand session gap scanner, interactive knowledge gap triage queue with dismissal, and article draft studio with 1-click RAG publishing, plus a 1-click "📝 Draft Article" button directly in the active session resolution card.
- Multi-Criteria CSAT Feedback, Review Queues & Agent Performance Scorecards Engine (`POST /feedback/csat`, `GET /feedback/queue`, `PATCH /feedback/{id}/review`, `GET /feedback/csat-summary`, `GET /feedback/agent-scorecards`): 1–5 star multi-criteria CSAT surveys (overall satisfaction, resolution satisfaction, agent helpfulness, response speed), automated low-CSAT (`<= 2` stars) follow-up triage and `feedback.low_csat` webhook alerting, operator review workflow (`pending_review`, `followup_required`, `reviewed`, `resolved`) with reviewer notes, and per-agent / per-tier CSAT performance scorecards.
- Streamlit 5-Star CSAT Survey Widget & Operator Scorecards Dashboard: expandable 1–5 star multi-criteria CSAT survey widget in the chat interface, plus a dedicated sidebar panel for multi-criteria CSAT KPIs, per-agent performance scorecards, and interactive operator feedback review queue management.
- Customer Support Agent Assignment & Tiered Escalation Routing (`GET /agents`, `POST /agents`, `GET /agents/{id}`, `PATCH /agents/{id}`, `DELETE /agents/{id}`, `GET /agents/workload`, `POST /sessions/{id}/assign`, `POST /sessions/{id}/auto-assign`, `GET /sessions/{id}/assignment-history`): support agent profiles with tiered skill routing (`tier_1` Frontline & Concierge, `tier_2` Maintenance & Operations, `tier_3` Property Leadership), manual assignment and least-loaded automated routing, audit history logs, and live team workload distribution metrics.
- Operating Business Hours & Calendar Schedule Engine (`GET /business-hours/status`): deterministic weekly operating calendar calculation (default Mon-Fri 09:00–18:00 UTC) with automatic deadline advancement across nights and weekends for business-hours SLA policies (`use_business_hours`).
- Streamlit Support Agent Directory & Workload Dashboard: interactive sidebar panel showcasing active agent capacity, tier distribution, new agent registration, session queue filtering (Unassigned, Escalated Tier 2/3), manual assignment / auto-routing buttons, and audit trail viewers.
- SLA Policies, Priority Triage & Automated Escalation Engine (`GET /sla/policies`, `POST /sla/policies`, `PATCH /sla/policies/{id}`, `DELETE /sla/policies/{id}`, `GET /sessions/{id}/sla`, `POST /sla/evaluate-alerts`, `GET /sla/analytics`): configurable tier-based SLA targets by priority (`urgent`, `high`, `medium`, `low`) and category, tracking first response and resolution deadlines with configurable warning thresholds. Automated background alert evaluation dispatches `sla.approaching_breach` and `sla.breached` webhooks and automatically escalates breached sessions.
- Streamlit Priority Triage & Real-Time SLA Management: priority badge filters and indicators (`urgent`, `high`, `medium`, `low`) in session history and resolution tools, real-time active session SLA countdown tracker with color-coded health indicators (`healthy`, `approaching_breach`, `breached`, `met`), on-demand alert trigger, and dedicated SLA policy creation and compliance metrics dashboard.
- Automated AI macro suggestions & query intent classification engine (`POST /macros/suggest`, `GET /sessions/{id}/macro-suggestions`): real-time intent taxonomy classification (`maintenance_emergency`, `maintenance_routine`, `rent_payment`, `lease_renewal`, `move_out`, `general_inquiry`), automated extraction of domain entities (`unit_id`, `customer_name`), and multi-factor ranking matching tenant inquiries to canned responses with confidence scores, match rationales, and variable auto-population.
- Streamlit Smart Suggestions & Query Match Tester: real-time proactive macro recommendation cards surfaced in active support sessions with 1-click application, plus an interactive query testing widget for evaluating customer inquiry matching on the fly.
- Support canned responses & action macros engine (`POST /macros`, `GET /macros`, `GET /macros/categories`, `GET /macros/{id}`, `PATCH /macros/{id}`, `DELETE /macros/{id}`, `POST /macros/{id}/render`, `POST /sessions/{id}/apply-macro`): pre-approved response templates with category organization, shortcut triggers (`/rent-pay`, `/emerg-maint`, `/lease-renew`, `/move-out`), dynamic variable substitution (`{customer_name}`, `{session_id}`, `{unit_id}`, `{agent_name}`, `{date}`, `{support_contact}`), and automated session actions (status transitions to `resolved` or `escalated` with webhook triggers, tag assignment, conversation injection).
- Streamlit Quick Responses & Macros panel: browse pre-seeded property management templates with category filtering, fill dynamic template variables with auto-filled defaults, preview rendered output, apply responses into active chat sessions with 1 click, and create custom macro templates directly from the UI.
- Webhook dispatch & escalation alerting engine (`POST /webhooks`, `GET /webhooks`, `PATCH /webhooks/{id}`, `DELETE /webhooks/{id}`, `POST /webhooks/{id}/ping`, `GET /webhooks/deliveries`): automated real-time dispatching with HMAC-SHA256 signature verification (`X-Webhook-Signature`, `X-Webhook-Timestamp`, `X-Webhook-Event`) and delivery audit logging on session escalations (`session.escalated`), resolutions (`session.resolved`), and negative CSAT feedback (`feedback.negative`).
- Streamlit Webhooks & Alerts management panel: register endpoints with custom event filtering and HMAC secrets, test connectivity with one-click test pings, toggle active state, and monitor recent delivery status codes.
- Support conversation summarization & sentiment engine (`POST /sessions/{id}/summarize`): automated dialogue summarization with key points, detected sentiment (positive/neutral/negative), suggested tags, and offline fallback; actionable via the Streamlit session resolution panel.
- Support triage analytics & operations dashboard (`GET /sessions/triage-analytics`): aggregated operational KPIs (resolution rate %, escalation rate %, average turns per session, status distributions, and top issue tags) surfaced in the Streamlit sidebar.
- Session resolution notes & lifecycle metadata (`PATCH /sessions/{id}`): record resolution summaries and agent notes in persistent SQLite metadata alongside session status and tags.
- Enriched multi-format conversation export (`GET /sessions/{id}/export?format=markdown|json|csv`): Markdown, JSON, and CSV exports embed session status, tags, summary, and resolution notes alongside conversation transcripts.
- Exact-duplicate uploads rejected (`409`) via content hashing.
- Retrieval augmented generation with bounded chat history awareness
  (`MAX_HISTORY_TURNS`).
- Streaming answers over Server-Sent Events (`POST /chat/stream`) with a
  non-streaming fallback (`POST /chat`).
- Retrieval filters per request: `file_ids`, `source_filename`, `use_hybrid`
  (BM25 + vector hybrid with graceful vector-only fallback), and
  `collections` to scope answers to document collections.
- Opt-in query expansion (`expand_query`): LLM reformulations fused with
  reciprocal-rank fusion; enable via the sidebar toggle or
  `USE_QUERY_EXPANSION`.
- Opt-in lexical rerank (`rerank`): term-overlap reordering that composes
  with filters, hybrid, and expansion; sidebar toggle or `USE_RERANK`.
- Opt-in cross-encoder rerank (`use_cross_encoder_rerank`): semantic reordering
  using a cross-encoder model (e.g., `cross-encoder/ms-marco-MiniLM-L-6-v2`);
  takes precedence over lexical rerank; enable via sidebar toggle or
  `USE_CROSS_ENCODER_RERANK` and configure model via `CROSS_ENCODER_MODEL`.
- Document chunk inspection & re-chunking (`GET /docs/{id}`, `POST /docs/{id}/rechunk`):
  view chunk counts, previews, and persistent chunking options (strategy, size, overlap);
  re-chunk documents in place without re-uploading via the API or Streamlit inspector widget.
- Batch collection re-chunking & chunk analytics (`POST /collections/{name}/rechunk`, `GET /collections/{name}/analytics`):
  batch re-chunk entire collections with uniform chunking strategies and windowing parameters; inspect chunk length distributions, histograms, and strategy breakdowns via the API or Streamlit Collection Insights widget.
- Bulk document deletion (`POST /delete-docs`) with batch selection mode in the UI.
- Bulk session deletion (`POST /delete-sessions`) with cascading removal of chat history and feedback, plus batch deletion mode in the UI sidebar.
- Multi-format conversation export (`GET /sessions/{id}/export?format=markdown|json|csv`) with instant UI downloads as Markdown (`.md`), JSON (`.json`), or CSV (`.csv`).
- Feedback review panel & commenting: `POST /feedback` records optional user comments; `GET /feedback` and `GET /sessions/{id}/feedback` power an administrative sidebar panel with rating filters and session deep-linking.
- Dynamic runtime configuration discovery (`GET /config`) allowing frontends to automatically discover supported models, export formats, and upload limits.
- Session discovery & keyword search (`GET /sessions/search`) filtering past
  conversations across questions and responses in the UI.
- Multi-strategy retrieval evaluation harness (`scripts/eval_retrieval.py`)
  supporting hybrid, rerank, collection filters, and structured JSON exports.
- Document collections group uploads, retrieval, and the UI picker, with
  automatic migration for pre-v0.6.0 databases; whole collections can be
  removed (`DELETE /collections/{name}`, `default` protected).
- Retrieval inspection without chat cost (`POST /search` returns ranked
  chunks with metadata).
- Configurable chunking (recursive, sentence-aware semantic, markdown-aware) plus
  chunk-size/overlap validation, persistent source preservation, and a configurable
  upload size cap.
- Source-aware answers with document metadata returned by the API.
- Streamlit document upload, listing, deletion, chat controls, and a past-sessions switcher with previews, rename, session deletion, and quota display.
- Answer feedback (thumbs up/down under each answer, stored for future eval).
- Dark-mode UI theme (`.streamlit/config.toml`, shipped in the image).
- Logs (to stderr, optionally `LOG_PATH`) redact emails, phone numbers, and
  SSN-like patterns.
- Local SQLite logging for sessions and document records.
- Observability: `X-Request-ID` tracing, `/health/live`, `/health/ready`,
  `/metrics` (Prometheus text) and `/metrics.json` with per-route latency
  averages, approximate token-usage counters, and feedback totals,
  `LOG_FORMAT`/`LOG_LEVEL`. The Streamlit sidebar shows a backend metrics panel.
- Releases: pushing a `v*` tag runs the full verification suite and creates
  a GitHub release.
- Opt-in security: `API_KEY` (`X-API-Key` header), per-IP rate limiting
  (`RATE_LIMIT_PER_MIN`), and daily token quotas (`TOKEN_DAILY_BUDGET_EST`);
  health/metrics/docs paths stay public.
- Safe Git defaults that keep secrets, logs, databases, and vector stores out of commits.

## Architecture

```text
Streamlit UI -> FastAPI API -> LangChain RAG chain -> Chroma vector store
                            -> SQLite metadata/log store
                            -> OpenAI chat and embedding models
```

Important paths:

- `api/`: FastAPI app, schemas, database helpers, Chroma indexing, and RAG chain.
- `app/`: Streamlit UI and API client helpers.
- `docs/`: sample document corpus for local testing.
- `.env.example`: safe runtime configuration template.

## Setup

Use Python 3.11 or 3.12 for the smoothest dependency support.

1. Create and activate a virtual environment.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

2. Install dependencies.

```powershell
python -m pip install -r requirements.txt
```

3. Create a local `.env` from the example and add your own keys.

```powershell
Copy-Item .env.example .env
```

Required:

- `OPENAI_API_KEY`

Optional:

- `LANGCHAIN_TRACING_V2`
- `LANGCHAIN_API_KEY`
- `LANGCHAIN_PROJECT`
- `APP_API_BASE_URL`
- `CHROMA_PERSIST_DIR`
- `SQLITE_DB_PATH`
- `DEFAULT_MODEL`
- `RETRIEVER_K`
- `MAX_HISTORY_TURNS` (default `10`)
- `USE_HYBRID_RETRIEVER` (default `false`)
- `HYBRID_BM25_WEIGHT` / `HYBRID_VECTOR_WEIGHT` (default `0.5` each)
- `USE_QUERY_EXPANSION` (default `false`)
- `USE_RERANK` (default `false`)
- `EXPANSION_COUNT` (default `3`)
- `MAX_UPLOAD_MB` (default `25`)
- `MAX_BULK_FILES` (default `10`)
- `LOG_FORMAT` (`text` or `json`, default `text`)
- `LOG_LEVEL` (default `INFO`)
- `API_KEY` (empty = auth disabled; when set, send `X-API-Key`)
- `RATE_LIMIT_PER_MIN` (default `0` = off)
- `TOKEN_DAILY_BUDGET_EST` (default `0` = off)

## Run Locally

Start the API:

```powershell
uvicorn api.main:app --reload
```

Start the Streamlit app in another terminal:

```powershell
streamlit run app/streamlit_app.py
```

## Run with Docker

```powershell
Copy-Item .env.example .env
docker compose up --build
```

The API serves on `http://localhost:8000` and the UI on
`http://localhost:8501`. Data persists in the `rag-data` volume. See
`docs/RUNBOOK.md` for operations. For production-like defaults (2 workers,
JSON logs, resource limits, restarts), overlay the prod file:

```powershell
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

For a staging setup (single worker, debug logs, generous rate limit), swap
in the staging overlay instead:

```powershell
docker compose -f docker-compose.yml -f docker-compose.staging.yml up --build -d
```

## API quick reference

- `GET /health` — basic liveness with app name/version.
- `GET /health/live` — process liveness probe.
- `GET /health/ready` — readiness probe (SQLite + Chroma dir checks).
- `GET /metrics` / `GET /metrics.json` — in-memory request counters,
  latency averages, and estimated token usage.
- `POST /chat` — JSON answer with `sources`.
- `POST /chat/stream` — SSE stream (`data:` answer chunks,
  `event: sources` metadata, `event: error` on failure).
- `POST /upload-doc` — multipart upload with optional `chunking_strategy`,
  `chunk_size` (100–4000), `chunk_overlap` (< chunk size).
- `POST /upload-docs` — bulk upload with per-file results.
- `GET /list-docs`, `GET /docs/{id}`, `POST /docs/{id}/rechunk`, `POST /delete-doc`, `POST /delete-docs` — document metadata, chunk inspection, in-place re-chunking, and deletion.
- `GET /collections`, `PATCH`/`DELETE /collections/{name}` — collection lifecycle.
- `GET /config` — dynamic runtime configuration discovery (models, export formats, upload limits).
- `GET /stats` — library totals (documents, collections, sessions, messages).
- `POST /search` — ranked retrieval hits without chat cost.
- `GET /sessions`, `GET /sessions/{id}/history`, `DELETE /sessions/{id}` — past conversations.
- `POST /delete-sessions` — bulk session deletion with cascading history & feedback cleanup.
- `GET /sessions/{id}/export` — export conversation history (Markdown, JSON, or CSV).
- `GET /sessions/search` — search past conversations by keyword.
- `POST /feedback` — submit answer ratings (thumbs up/down) with optional text comments.
- `GET /feedback`, `GET /sessions/{id}/feedback` — list and filter feedback records.
- `POST /feedback/csat`, `GET /feedback/queue`, `PATCH /feedback/{id}/review`, `GET /feedback/csat-summary`, `GET /feedback/agent-scorecards` — 1–5 star multi-criteria CSAT surveys, operator review workflow queue, CSAT KPI summary, and per-agent performance scorecards.
- `POST /units`, `GET /units`, `POST /tenants`, `GET /tenants`, `POST /sessions/{id}/link-tenant` — property unit directory, resident profiles, and context grounding.
- `POST /work-orders`, `GET /work-orders`, `GET /work-orders/metrics`, `POST /sessions/{id}/create-work-order` — maintenance service requests and resident dispatch.
- `POST /billing/transactions`, `GET /billing/transactions`, `GET /billing/metrics`, `POST /tenants/{id}/payments`, `GET /tenants/{id}/ledger` — resident billing ledgers, charges, and payments.
- `POST /lease-renewals`, `GET /lease-renewals`, `GET /lease-renewals/metrics`, `POST /lease-renewals/{id}/sign`, `POST /lease-renewals/{id}/publish` — lease renewal proposals, digital e-signatures, and agreement synthesis.
- `DELETE /sessions?before=<ISO datetime>` — prune inactive sessions.
- `GET /quota` — daily token budget usage for the caller.

Full details: `docs/API.md`. Architecture notes: `docs/ARCHITECTURE.md`.
Contributor workflow: `docs/CONTRIBUTING.md`. Roadmap: `ROADMAP.md`.
Operations: `docs/RUNBOOK.md`. Deployment: `docs/DEPLOYMENT.md`.
Kubernetes: `k8s/deployment.yaml`.

## Manual retrieval eval

Upload the `docs/` corpus, then run:

```powershell
python scripts/eval_retrieval.py
```

It checks each `docs/eval/golden.json` question against the live vector
store (needs `OPENAI_API_KEY`; not run in CI). Compare expansion against
the baseline with:

```powershell
python scripts/eval_retrieval.py --compare
```

## Testing

```powershell
python -m pytest
python -m ruff check api/ app/ tests/ scripts/
python -m mypy api/ app/ scripts/
```

`pytest` also enforces an 80% coverage floor across `api/` and the
Streamlit client (`app/`), which is unit-tested via a fake Streamlit helper
in `tests/`.

### Browser end-to-end tests (Playwright, opt-in)

`tests/e2e/` holds a Playwright suite (`-m e2e`) that drives the real UI with
a headless Chromium against the live API + Streamlit app:

```powershell
# terminal 1 — API on :8000
$env:SQLITE_DB_PATH = "$pwd\rag_app.db"; $env:CHROMA_PERSIST_DIR = "$pwd\chroma_db"
python -m uvicorn api.main:app --port 8000
# terminal 2 — UI on :8501
python -m streamlit run app/streamlit_app.py --server.port 8501 --server.headless true
# terminal 3 — the suite
python -m pytest -m e2e --no-cov tests/e2e
```

The e2e tests are excluded from the default `pytest` run. LLM round-trip and
document-upload tests self-skip when the configured model/embeddings are
unreachable (e.g. an OpenAI key without credits), so the suite stays green on
a credit-less machine and keyless CI; set `OPENAI_API_KEY` to actually run the
model-backed paths. `make test-e2e` runs the same command.
