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


class Settings:
    def __init__(self):
        self.app_name = "Customer Support RAG Agent"
        self.app_version = "0.2.0"
        self.api_base_url = os.getenv("APP_API_BASE_URL", "http://localhost:8000").rstrip("/")
        self.chroma_persist_dir = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
        self.sqlite_db_path = os.getenv("SQLITE_DB_PATH", "rag_app.db")
        self.default_model = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")
        self.retriever_k = get_positive_int_env("RETRIEVER_K", 5)


settings = Settings()
