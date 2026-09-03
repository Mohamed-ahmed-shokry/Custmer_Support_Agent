# Contributing

## Setup

Use Python 3.11 or 3.12 when possible (3.14 works via lazy `langchain`
imports — see `docs/ARCHITECTURE.md`).

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

## Workflow

- Keep changes small; commit and push each logical step.
- Before pushing, run:

```powershell
python -m pytest
python -m ruff check api/ app/ tests/
python -m mypy api/ app/
```

- `ruff --fix` and `black` are fine for formatting, but re-run tests after.
- New API behavior needs tests in `tests/test_api_routes.py` (or a focused
  module) plus docs updates (`README.md`, `docs/API.md` when endpoints change).

## Compatibility rules

- Do **not** add top-level imports of `langchain.chains`,
  `langchain.retrievers`, or other legacy modules in `api/main.py` or
  `api/chroma_utils.py` — they break collection on Python 3.14. Use
  function-level (lazy) imports with a vector-search fallback.
- Test mocks for `get_rag_chain_for_model` must accept
  `(model, *args, **kwargs)` since retrieval flags are forwarded as kwargs.
- Never commit `.env`, `*.db`, `*.log`, or `chroma_db/` (already gitignored).
  Run the repo's secret scan before pushing if you touched configs.
