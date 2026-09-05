import os

from dotenv import load_dotenv

load_dotenv()


def get_positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        value = int(raw_value)
    except ValueError:
        return default

    return value if value > 0 else default


def get_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "y", "on"}


def get_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError:
        return default


class Settings:
    def __init__(self):
        self.app_name = "Customer Support RAG Agent"
        self.app_version = "0.6.0"
        self.api_base_url = os.getenv("APP_API_BASE_URL", "http://localhost:8000").rstrip("/")
        self.chroma_persist_dir = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
        self.sqlite_db_path = os.getenv("SQLITE_DB_PATH", "rag_app.db")
        self.default_model = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")
        self.retriever_k = get_positive_int_env("RETRIEVER_K", 5)
        self.use_hybrid_retriever = get_bool_env("USE_HYBRID_RETRIEVER", False)
        self.hybrid_bm25_weight = get_float_env("HYBRID_BM25_WEIGHT", 0.5)
        self.hybrid_vector_weight = get_float_env("HYBRID_VECTOR_WEIGHT", 0.5)
        self.max_upload_mb = get_positive_int_env("MAX_UPLOAD_MB", 25)
        self.log_format = os.getenv("LOG_FORMAT", "text").strip().lower()
        self.log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
        self.api_key = os.getenv("API_KEY", "")
        self.rate_limit_per_min = get_positive_int_env("RATE_LIMIT_PER_MIN", 0)
        self.token_daily_budget_est = get_positive_int_env("TOKEN_DAILY_BUDGET_EST", 0)


settings = Settings()
