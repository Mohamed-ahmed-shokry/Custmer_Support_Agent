# Contributing

## Setup

Use Python 3.11 or 3.12 when possible (3.14 works via lazy `langchain`
imports — see `docs/ARCHITECTURE.md`).

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
pre-commit install
Copy-Item .env.example .env
```

`pre-commit install` wires the hooks in `.pre-commit-config.yaml`
(ruff lint --fix, ruff format check, mypy) to run on every commit; CI runs
the same commands on every push.

## Workflow

- Keep changes small; commit and push each logical step.
- Before pushing, run:

```powershell
python -m pytest
python -m ruff check api/ app/ tests/ scripts/
python -m mypy api/ app/ scripts/
```

- `python -m pytest` also enforces an 80% coverage floor across `api/` and
  `app/` (configured in `pyproject.toml`).
- `ruff` is the sole formatter: `python -m ruff format` (auto-format) and
  `python -m ruff check --fix`; re-run tests after editing.
- New behavior needs tests: API routes in `tests/`, and Streamlit client
  behavior in `tests/test_app_ui.py` / `tests/test_app_api_utils.py` (using
  the `FakeStreamlit` helper in `tests/fake_streamlit.py`). Update docs
  (`README.md`, `docs/API.md`) when endpoints change.
- UI-facing changes that touch the chat, sidebar, upload, or sessions flows
  should also get a Playwright step. The suite lives in `tests/e2e/` (`-m e2e`,
  opt-in) and needs a running API + UI; see the "Browser end-to-end tests"
  section of `README.md`. Tests there self-skip when a model or embeddings
  provider is unavailable, so they stay green without credits.

## Compatibility rules

- Do **not** add top-level imports of `langchain.chains`,
  `langchain.retrievers`, or other legacy modules in `api/main.py` or
  `api/chroma_utils.py` — they break collection on Python 3.14. Use
  function-level (lazy) imports with a vector-search fallback.
- Test mocks for `get_rag_chain_for_model` must accept
  `(model, *args, **kwargs)` since retrieval flags are forwarded as kwargs.
- Never commit `.env`, `*.db`, `*.log`, or `chroma_db/` (already gitignored).
  Run the repo's secret scan before pushing if you touched configs.
