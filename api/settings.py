import os
from dotenv import load_dotenv


load_dotenv()


class Settings:
    app_name = "Customer Support RAG Agent"
    app_version = "0.2.0"
    api_base_url = os.getenv("APP_API_BASE_URL", "http://localhost:8000").rstrip("/")
    chroma_persist_dir = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
    sqlite_db_path = os.getenv("SQLITE_DB_PATH", "rag_app.db")
    default_model = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")
    retriever_k = int(os.getenv("RETRIEVER_K", "5"))


settings = Settings()
