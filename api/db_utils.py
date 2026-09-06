import sqlite3
from contextlib import closing
from pathlib import Path

from api.collections import DEFAULT_COLLECTION, normalize_collection
from api.settings import settings

__all__ = ["DEFAULT_COLLECTION", "normalize_collection"]

DB_NAME = settings.sqlite_db_path

_CREATE_APP_LOGS_TABLE = (
    "CREATE TABLE IF NOT EXISTS application_logs "
    "(id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "session_id TEXT, user_query TEXT, gpt_response TEXT, "
    "model TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)

_CREATE_DOC_STORE_TABLE = (
    "CREATE TABLE IF NOT EXISTS document_store "
    "(id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "filename TEXT, collection TEXT NOT NULL DEFAULT 'default', "
    "upload_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)

_INSERT_APP_LOG = (
    "INSERT INTO application_logs (session_id, user_query, gpt_response, model) "
    "VALUES (?, ?, ?, ?)"
)

_SELECT_CHAT_HISTORY = (
    "SELECT user_query, gpt_response FROM application_logs "
    "WHERE session_id = ? ORDER BY created_at ASC, id ASC"
)

_INSERT_DOC_RECORD = "INSERT INTO document_store (filename, collection) VALUES (?, ?)"

_SELECT_DOC_RECORD = (
    "SELECT id, filename, collection, upload_timestamp FROM document_store WHERE id = ?"
)

_DELETE_DOC_RECORD = "DELETE FROM document_store WHERE id = ?"

_SELECT_ALL_DOCS = (
    "SELECT id, filename, collection, upload_timestamp FROM document_store "
    "ORDER BY upload_timestamp DESC, id DESC"
)

_SELECT_DOCS_BY_COLLECTION = (
    "SELECT id, filename, collection, upload_timestamp FROM document_store "
    "WHERE collection = ? ORDER BY upload_timestamp DESC, id DESC"
)

_SELECT_ALL_COLLECTIONS = "SELECT DISTINCT collection FROM document_store ORDER BY collection"

_SELECT_ALL_SESSIONS = (
    "SELECT l1.session_id, COUNT(*) AS message_count, "
    "MAX(l1.created_at) AS last_active, "
    "(SELECT l2.user_query FROM application_logs l2 "
    "WHERE l2.session_id = l1.session_id ORDER BY l2.id ASC LIMIT 1) AS preview "
    "FROM application_logs l1 GROUP BY l1.session_id ORDER BY last_active DESC"
)

_DELETE_SESSION = "DELETE FROM application_logs WHERE session_id = ?"

PREVIEW_MAX_LENGTH = 80


def get_db_connection():
    db_path = Path(DB_NAME)
    if db_path.parent != Path("."):
        db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def create_application_logs():
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_APP_LOGS_TABLE)
        conn.commit()


def insert_application_logs(session_id, user_query, gpt_response, model):
    with closing(get_db_connection()) as conn:
        conn.execute(_INSERT_APP_LOG, (session_id, user_query, gpt_response, model))
        conn.commit()


def get_chat_history(session_id):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(_SELECT_CHAT_HISTORY, (session_id,))
        messages = []
        for row in cursor.fetchall():
            messages.extend(
                [
                    {"role": "human", "content": row["user_query"]},
                    {"role": "ai", "content": row["gpt_response"]},
                ]
            )
        return messages


def create_document_store():
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_DOC_STORE_TABLE)
        conn.commit()


def migrate_document_store():
    """Add the collection column to pre-v0.6.0 databases (no-op otherwise)."""
    with closing(get_db_connection()) as conn:
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(document_store)")]
        if "collection" not in columns:
            conn.execute(
                "ALTER TABLE document_store "
                "ADD COLUMN collection TEXT NOT NULL DEFAULT 'default'"
            )
            conn.commit()


def insert_document_record(filename, collection=DEFAULT_COLLECTION):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(_INSERT_DOC_RECORD, (filename, collection))
        file_id = cursor.lastrowid
        conn.commit()
        return file_id


def get_document_record(file_id):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(_SELECT_DOC_RECORD, (file_id,))
        document = cursor.fetchone()
        return dict(document) if document else None


def delete_document_record(file_id):
    with closing(get_db_connection()) as conn:
        cursor = conn.execute(_DELETE_DOC_RECORD, (file_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted


def get_all_documents(collection=None):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        if collection is None:
            cursor.execute(_SELECT_ALL_DOCS)
        else:
            cursor.execute(_SELECT_DOCS_BY_COLLECTION, (collection,))
        documents = cursor.fetchall()
        return [dict(doc) for doc in documents]


def get_all_collections():
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(_SELECT_ALL_COLLECTIONS)
        return [row["collection"] for row in cursor.fetchall()]


def _truncate_preview(preview: str | None) -> str:
    if not preview:
        return ""
    preview = preview.strip()
    if len(preview) <= PREVIEW_MAX_LENGTH:
        return preview
    return preview[: PREVIEW_MAX_LENGTH - 1].rstrip() + "…"


def get_all_sessions():
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(_SELECT_ALL_SESSIONS)
        sessions = cursor.fetchall()
        return [
            {**dict(session), "preview": _truncate_preview(session["preview"])}
            for session in sessions
        ]


def delete_session(session_id):
    with closing(get_db_connection()) as conn:
        cursor = conn.execute(_DELETE_SESSION, (session_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted


# Initialize the database tables
create_application_logs()
create_document_store()
migrate_document_store()
