.PHONY: install api app test lint typecheck verify secret-scan

PYTHON ?= python
PYTEST ?= $(PYTHON) -m pytest

install:
	$(PYTHON) -m pip install -r requirements.txt

api:
	uvicorn api.main:app --reload

app:
	streamlit run app/streamlit_app.py

test:
	$(PYTEST)

lint:
	$(PYTHON) -m ruff check api/ app/ tests/

typecheck:
	$(PYTHON) -m mypy api/ app/

verify: lint typecheck test

secret-scan:
	rg -n --hidden -S -g '!.git/**' 'sk-[A-Za-z0-9_-]+|lsv2_[A-Za-z0-9_-]+|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|ghp_[0-9A-Za-z]{36}|github_pat_[0-9A-Za-z_]+'
