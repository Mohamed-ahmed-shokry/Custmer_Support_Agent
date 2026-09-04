# syntax=docker/dockerfile:1

# Multi-stage build: slim runtime with dependencies pre-installed.
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

FROM base AS deps
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

FROM base AS runtime
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
COPY api/ ./api/
COPY app/ ./app/
COPY docs/CORPUS.md ./docs/CORPUS.md
COPY pyproject.toml pytest.ini ./
EXPOSE 8000
ENV APP_API_BASE_URL=http://localhost:8000 \
    CHROMA_PERSIST_DIR=/data/chroma_db \
    SQLITE_DB_PATH=/data/rag_app.db
VOLUME ["/data"]
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
