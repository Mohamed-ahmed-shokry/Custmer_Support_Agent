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
    "sha256 TEXT, upload_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)

_CREATE_SESSION_LABELS_TABLE = (
    "CREATE TABLE IF NOT EXISTS session_labels "
    "(session_id TEXT PRIMARY KEY, label TEXT NOT NULL)"
)

MAX_SESSION_LABEL_LENGTH = 80

_INSERT_APP_LOG = (
    "INSERT INTO application_logs (session_id, user_query, gpt_response, model) "
    "VALUES (?, ?, ?, ?)"
)

_SELECT_CHAT_HISTORY = (
    "SELECT user_query, gpt_response FROM application_logs "
    "WHERE session_id = ? ORDER BY created_at ASC, id ASC"
)

_INSERT_DOC_RECORD = "INSERT INTO document_store (filename, collection, sha256) VALUES (?, ?, ?)"
_SELECT_DOC_BY_HASH = (
    "SELECT id, filename, collection, upload_timestamp FROM document_store "
    "WHERE sha256 = ? ORDER BY id ASC LIMIT 1"
)

_SELECT_DOC_RECORD = (
    "SELECT id, filename, collection, upload_timestamp FROM document_store WHERE id = ?"
)

_DELETE_DOC_RECORD = "DELETE FROM document_store WHERE id = ?"
_DELETE_DOCS_BY_COLLECTION = "DELETE FROM document_store WHERE collection = ?"
_RENAME_COLLECTION = "UPDATE document_store SET collection = ? WHERE collection = ?"

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
    "WHERE l2.session_id = l1.session_id ORDER BY l2.id ASC LIMIT 1) AS preview, "
    "(SELECT label FROM session_labels WHERE session_id = l1.session_id) AS label "
    "FROM application_logs l1 GROUP BY l1.session_id ORDER BY last_active DESC"
)

_DELETE_SESSION = "DELETE FROM application_logs WHERE session_id = ?"
_DELETE_SESSION_LABEL = "DELETE FROM session_labels WHERE session_id = ?"
_UPSERT_SESSION_LABEL = (
    "INSERT INTO session_labels (session_id, label) VALUES (?, ?) "
    "ON CONFLICT(session_id) DO UPDATE SET label = excluded.label"
)
_SESSION_HAS_LOGS = "SELECT 1 FROM application_logs WHERE session_id = ? LIMIT 1"


def normalize_session_label(value: str | None) -> str:
    """Validate a session label, raising ValueError if blank or too long."""
    label = (value or "").strip()
    if not label:
        raise ValueError("Session label must not be blank.")
    if len(label) > MAX_SESSION_LABEL_LENGTH:
        raise ValueError(
            f"Session label must be at most {MAX_SESSION_LABEL_LENGTH} characters."
        )
    return label

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


def truncate_history(messages, max_turns):
    """Keep only the most recent turns (a turn is one human+AI pair)."""
    if max_turns is None or max_turns <= 0:
        return messages
    return messages[-2 * max_turns :]


def create_document_store():
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_DOC_STORE_TABLE)
        conn.commit()


def migrate_document_store():
    """Add newer columns to pre-existing databases (no-op otherwise)."""
    with closing(get_db_connection()) as conn:
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(document_store)")]
        if "collection" not in columns:
            conn.execute(
                "ALTER TABLE document_store "
                "ADD COLUMN collection TEXT NOT NULL DEFAULT 'default'"
            )
        if "sha256" not in columns:
            conn.execute("ALTER TABLE document_store ADD COLUMN sha256 TEXT")
        conn.commit()


def insert_document_record(filename, collection=DEFAULT_COLLECTION, sha256=None):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(_INSERT_DOC_RECORD, (filename, collection, sha256))
        file_id = cursor.lastrowid
        conn.commit()
        return file_id


def get_document_by_hash(sha256):
    """Return the earliest document with identical content, if any."""
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(_SELECT_DOC_BY_HASH, (sha256,))
        document = cursor.fetchone()
        return dict(document) if document else None


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


def delete_documents_by_collection(collection):
    """Delete every document record in a collection, returning the count."""
    with closing(get_db_connection()) as conn:
        cursor = conn.execute(_DELETE_DOCS_BY_COLLECTION, (collection,))
        deleted = cursor.rowcount
        conn.commit()
        return deleted


def rename_collection(old, new):
    """Move every document record to another collection, returning the count."""
    with closing(get_db_connection()) as conn:
        cursor = conn.execute(_RENAME_COLLECTION, (new, old))
        renamed = cursor.rowcount
        conn.commit()
        return renamed


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


def get_library_stats():
    """Return library totals without loading any rows."""
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        documents = cursor.execute("SELECT COUNT(*) FROM document_store").fetchone()[0]
        collections = cursor.execute(
            "SELECT COUNT(DISTINCT collection) FROM document_store"
        ).fetchone()[0]
        sessions = cursor.execute(
            "SELECT COUNT(DISTINCT session_id) FROM application_logs"
        ).fetchone()[0]
        messages = cursor.execute("SELECT COUNT(*) FROM application_logs").fetchone()[0]
        return {
            "documents": documents,
            "collections": collections,
            "sessions": sessions,
            "messages": messages,
        }


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
        conn.execute(_DELETE_SESSION_LABEL, (session_id,))
        conn.commit()
        return deleted


def create_session_labels():
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_SESSION_LABELS_TABLE)
        conn.commit()


def rename_session(session_id, label):
    """Label a session that has chat history; returns False when unknown."""
    with closing(get_db_connection()) as conn:
        exists = conn.execute(_SESSION_HAS_LOGS, (session_id,)).fetchone() is not None
        if not exists:
            return False
        conn.execute(_UPSERT_SESSION_LABEL, (session_id, label))
        conn.commit()
        return True


# Initialize the database tables
create_application_logs()
create_document_store()
migrate_document_store()
create_session_labels()
