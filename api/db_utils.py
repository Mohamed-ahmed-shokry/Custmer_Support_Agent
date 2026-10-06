import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path
from typing import Any

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

_CREATE_DOC_SOURCES_TABLE = (
    "CREATE TABLE IF NOT EXISTS document_sources "
    "(file_id INTEGER PRIMARY KEY REFERENCES document_store(id) ON DELETE CASCADE, "
    "source_text TEXT NOT NULL, "
    "strategy TEXT NOT NULL DEFAULT 'recursive', "
    "chunk_size INTEGER NOT NULL DEFAULT 1000, "
    "chunk_overlap INTEGER NOT NULL DEFAULT 200, "
    "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)

_INSERT_DOC_SOURCE = (
    "INSERT INTO document_sources "
    "(file_id, source_text, strategy, chunk_size, chunk_overlap) VALUES (?, ?, ?, ?, ?) "
    "ON CONFLICT(file_id) DO UPDATE SET "
    "source_text=excluded.source_text, strategy=excluded.strategy, "
    "chunk_size=excluded.chunk_size, chunk_overlap=excluded.chunk_overlap, "
    "updated_at=CURRENT_TIMESTAMP"
)

_SELECT_DOC_SOURCE = (
    "SELECT file_id, source_text, strategy, chunk_size, chunk_overlap, updated_at "
    "FROM document_sources WHERE file_id = ?"
)
_SELECT_DOC_SOURCES_BY_COLLECTION = (
    "SELECT ds.file_id, ds.source_text, ds.strategy, ds.chunk_size, "
    "ds.chunk_overlap, ds.updated_at, d.filename, d.collection "
    "FROM document_sources ds "
    "JOIN document_store d ON ds.file_id = d.id "
    "WHERE d.collection = ? "
    "ORDER BY ds.file_id ASC"
)

_DELETE_DOC_SOURCE = "DELETE FROM document_sources WHERE file_id = ?"
_DELETE_DOC_SOURCES_BY_COLLECTION = (
    "DELETE FROM document_sources "
    "WHERE file_id IN (SELECT id FROM document_store WHERE collection = ?)"
)

_CREATE_SESSION_LABELS_TABLE = (
    "CREATE TABLE IF NOT EXISTS session_labels "
    "(session_id TEXT PRIMARY KEY, label TEXT NOT NULL, "
    "status TEXT NOT NULL DEFAULT 'active', "
    "tags TEXT NOT NULL DEFAULT '', "
    "summary TEXT DEFAULT '', "
    "resolution_notes TEXT DEFAULT '')"
)

_CREATE_FEEDBACK_TABLE = (
    "CREATE TABLE IF NOT EXISTS feedback "
    "(id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "session_id TEXT NOT NULL, rating INTEGER NOT NULL, "
    "comment TEXT, "
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)

_INSERT_FEEDBACK = "INSERT INTO feedback (session_id, rating, comment) VALUES (?, ?, ?)"

_SELECT_FEEDBACK_COUNT = "SELECT COUNT(*) FROM feedback WHERE rating = ?"

_CREATE_WEBHOOKS_TABLE = (
    "CREATE TABLE IF NOT EXISTS webhooks ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "url TEXT NOT NULL, "
    "events TEXT NOT NULL DEFAULT '*', "
    "secret TEXT DEFAULT '', "
    "is_active INTEGER NOT NULL DEFAULT 1, "
    "failure_count INTEGER NOT NULL DEFAULT 0, "
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)

_CREATE_WEBHOOK_DELIVERY_LOGS_TABLE = (
    "CREATE TABLE IF NOT EXISTS webhook_delivery_logs ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "webhook_id INTEGER NOT NULL REFERENCES webhooks(id) ON DELETE CASCADE, "
    "event TEXT NOT NULL, "
    "url TEXT NOT NULL, "
    "status_code INTEGER, "
    "success INTEGER NOT NULL, "
    "payload_preview TEXT, "
    "error_message TEXT, "
    "delivered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)

_INSERT_WEBHOOK = (
    "INSERT INTO webhooks (url, events, secret, is_active, failure_count) "
    "VALUES (?, ?, ?, ?, 0)"
)
_SELECT_WEBHOOK_BY_ID = (
    "SELECT id, url, events, secret, is_active, failure_count, created_at "
    "FROM webhooks WHERE id = ?"
)
_DELETE_WEBHOOK = "DELETE FROM webhooks WHERE id = ?"
_DELETE_WEBHOOK_LOGS_BY_WEBHOOK = "DELETE FROM webhook_delivery_logs WHERE webhook_id = ?"
_INSERT_WEBHOOK_DELIVERY = (
    "INSERT INTO webhook_delivery_logs "
    "(webhook_id, event, url, status_code, success, payload_preview, error_message) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)
_INCREMENT_WEBHOOK_FAILURE = (
    "UPDATE webhooks SET failure_count = failure_count + 1 WHERE id = ?"
)
_RESET_WEBHOOK_FAILURE = (
    "UPDATE webhooks SET failure_count = 0 WHERE id = ?"
)

_CREATE_SUPPORT_MACROS_TABLE = (
    "CREATE TABLE IF NOT EXISTS support_macros ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "title TEXT NOT NULL, "
    "shortcut TEXT NOT NULL UNIQUE, "
    "category TEXT NOT NULL DEFAULT 'General', "
    "content TEXT NOT NULL, "
    "tags TEXT NOT NULL DEFAULT '', "
    "status_action TEXT, "
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
    "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)
_CREATE_MACRO_CATEGORY_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_support_macros_category ON support_macros(category)"
)
_CREATE_MACRO_SHORTCUT_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_support_macros_shortcut ON support_macros(shortcut)"
)

_INSERT_SUPPORT_MACRO = (
    "INSERT INTO support_macros (title, shortcut, category, content, tags, status_action) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)
_SELECT_MACRO_BY_ID = (
    "SELECT id, title, shortcut, category, content, tags, status_action, created_at, updated_at "
    "FROM support_macros WHERE id = ?"
)
_SELECT_MACRO_BY_SHORTCUT = (
    "SELECT id, title, shortcut, category, content, tags, status_action, created_at, updated_at "
    "FROM support_macros WHERE LOWER(shortcut) = LOWER(?)"
)
_DELETE_SUPPORT_MACRO = "DELETE FROM support_macros WHERE id = ?"
_SELECT_MACRO_CATEGORIES = (
    "SELECT DISTINCT category FROM support_macros ORDER BY category ASC"
)

MAX_MACRO_TITLE_LENGTH = 100
MAX_MACRO_SHORTCUT_LENGTH = 50
MAX_MACRO_CATEGORY_LENGTH = 50
MAX_MACRO_CONTENT_LENGTH = 4000
MAX_MACRO_TAGS_LENGTH = 200

VALID_WEBHOOK_EVENTS = {
    "*",
    "session.escalated",
    "session.resolved",
    "feedback.negative",
    "ping",
}
MAX_WEBHOOK_URL_LENGTH = 500
MAX_WEBHOOK_SECRET_LENGTH = 256
MAX_DELIVERY_PREVIEW_LENGTH = 500
MAX_DELIVERY_ERROR_LENGTH = 500

MAX_SESSION_LABEL_LENGTH = 80
VALID_SESSION_STATUSES = {"active", "resolved", "escalated", "closed"}
MAX_SESSION_TAGS_LENGTH = 200
MAX_SESSION_SUMMARY_LENGTH = 2000
MAX_RESOLUTION_NOTES_LENGTH = 2000

_INSERT_APP_LOG = (
    "INSERT INTO application_logs (session_id, user_query, gpt_response, model) VALUES (?, ?, ?, ?)"
)

_SELECT_CHAT_HISTORY = (
    "SELECT user_query, gpt_response FROM application_logs "
    "WHERE session_id = ? ORDER BY created_at ASC, id ASC"
)
_SELECT_LATEST_USER_QUERY = (
    "SELECT user_query FROM application_logs "
    "WHERE session_id = ? ORDER BY id DESC LIMIT 1"
)

_INSERT_DOC_RECORD = "INSERT INTO document_store (filename, collection, sha256) VALUES (?, ?, ?)"
_SELECT_DOC_BY_HASH = (
    "SELECT id, filename, collection, upload_timestamp FROM document_store "
    "WHERE sha256 = ? ORDER BY id ASC LIMIT 1"
)
_SELECT_DOC_BY_ID = (
    "SELECT id, filename, collection, upload_timestamp, sha256 FROM document_store "
    "WHERE id = ? LIMIT 1"
)
_SELECT_DOC_RECORD = _SELECT_DOC_BY_ID
_DELETE_DOC_RECORD = "DELETE FROM document_store WHERE id = ?"
_SELECT_ALL_DOCS = (
    "SELECT id, filename, collection, upload_timestamp FROM document_store ORDER BY id DESC"
)
_SELECT_DOCS_BY_COLLECTION = (
    "SELECT id, filename, collection, upload_timestamp FROM document_store "
    "WHERE collection = ? ORDER BY id DESC"
)
_RENAME_COLLECTION = "UPDATE document_store SET collection = ? WHERE collection = ?"
_DELETE_DOCS_BY_COLLECTION = "DELETE FROM document_store WHERE collection = ?"

_SELECT_ALL_COLLECTIONS = "SELECT DISTINCT collection FROM document_store ORDER BY collection"

_SELECT_ALL_SESSIONS_BASE = (
    "SELECT l1.session_id, COUNT(*) AS message_count, "
    "MAX(l1.created_at) AS last_active, "
    "(SELECT l2.user_query FROM application_logs l2 "
    "WHERE l2.session_id = l1.session_id ORDER BY l2.id ASC LIMIT 1) AS preview, "
    "(SELECT label FROM session_labels WHERE session_id = l1.session_id) AS label, "
    "COALESCE("
    "(SELECT status FROM session_labels WHERE session_id = l1.session_id), 'active'"
    ") AS status, "
    "COALESCE((SELECT tags FROM session_labels WHERE session_id = l1.session_id), '') AS tags, "
    "COALESCE("
    "(SELECT summary FROM session_labels WHERE session_id = l1.session_id), ''"
    ") AS summary, "
    "COALESCE("
    "(SELECT resolution_notes FROM session_labels WHERE session_id = l1.session_id), ''"
    ") AS resolution_notes "
    "FROM application_logs l1 GROUP BY l1.session_id"
)
_SELECT_ALL_SESSIONS = _SELECT_ALL_SESSIONS_BASE + " ORDER BY last_active DESC"

_SEARCH_SESSIONS = (
    "SELECT l1.session_id, COUNT(*) AS match_count, "
    "MAX(l1.created_at) AS last_active, "
    "(SELECT l2.user_query FROM application_logs l2 "
    "WHERE l2.session_id = l1.session_id ORDER BY l2.id ASC LIMIT 1) AS preview, "
    "(SELECT label FROM session_labels WHERE session_id = l1.session_id) AS label, "
    "COALESCE("
    "(SELECT status FROM session_labels WHERE session_id = l1.session_id), 'active'"
    ") AS status, "
    "COALESCE((SELECT tags FROM session_labels WHERE session_id = l1.session_id), '') AS tags, "
    "COALESCE("
    "(SELECT summary FROM session_labels WHERE session_id = l1.session_id), ''"
    ") AS summary, "
    "COALESCE("
    "(SELECT resolution_notes FROM session_labels WHERE session_id = l1.session_id), ''"
    ") AS resolution_notes "
    "FROM application_logs l1 "
    "WHERE l1.user_query LIKE ? OR l1.gpt_response LIKE ? "
    "GROUP BY l1.session_id ORDER BY last_active DESC LIMIT ?"
)

_SELECT_MATCHED_QUERIES = (
    "SELECT DISTINCT user_query FROM application_logs "
    "WHERE session_id = ? AND (user_query LIKE ? OR gpt_response LIKE ?) "
    "ORDER BY id ASC LIMIT 3"
)

_DELETE_SESSION = "DELETE FROM application_logs WHERE session_id = ?"
_DELETE_SESSION_LABEL = "DELETE FROM session_labels WHERE session_id = ?"
_DELETE_SESSION_FEEDBACK = "DELETE FROM feedback WHERE session_id = ?"
_STALE_SESSIONS = (
    "SELECT session_id FROM application_logs GROUP BY session_id HAVING MAX(created_at) < ?"
)
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
        raise ValueError(f"Session label must be at most {MAX_SESSION_LABEL_LENGTH} characters.")
    return label


def normalize_session_status(value: str | None) -> str:
    status = (value or "active").strip().lower()
    if status not in VALID_SESSION_STATUSES:
        raise ValueError(
            f"Invalid session status '{status}'. Must be one of: {sorted(VALID_SESSION_STATUSES)}."
        )
    return status


def normalize_session_tags(value: str | list[str] | None) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        tags_list = [t.strip().lower() for t in value if t and t.strip()]
        tags_str = ", ".join(sorted(set(tags_list)))
    else:
        tags_list = [t.strip().lower() for t in value.split(",") if t and t.strip()]
        tags_str = ", ".join(sorted(set(tags_list)))
    if len(tags_str) > MAX_SESSION_TAGS_LENGTH:
        raise ValueError(f"Session tags must be at most {MAX_SESSION_TAGS_LENGTH} characters.")
    return tags_str


def normalize_session_summary(value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.strip()
    if len(cleaned) > MAX_SESSION_SUMMARY_LENGTH:
        raise ValueError(
            f"Session summary must be at most {MAX_SESSION_SUMMARY_LENGTH} characters."
        )
    return cleaned


def normalize_resolution_notes(value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.strip()
    if len(cleaned) > MAX_RESOLUTION_NOTES_LENGTH:
        raise ValueError(
            f"Resolution notes must be at most {MAX_RESOLUTION_NOTES_LENGTH} characters."
        )
    return cleaned


def normalize_webhook_url(value: str | None) -> str:
    """Validate webhook URL, ensuring http/https scheme and reasonable length."""
    url = (value or "").strip()
    if not url:
        raise ValueError("Webhook URL must not be blank.")
    if len(url) > MAX_WEBHOOK_URL_LENGTH:
        raise ValueError(f"Webhook URL must be at most {MAX_WEBHOOK_URL_LENGTH} characters.")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("Webhook URL must start with 'http://' or 'https://'.")
    return url


def normalize_webhook_events(value: str | list[str] | None) -> str:
    """Validate subscribed events, returning comma-separated canonical string."""
    if value is None:
        return "*"
    if isinstance(value, list):
        raw_events = [ev.strip().lower() for ev in value if ev and ev.strip()]
    else:
        raw_events = [ev.strip().lower() for ev in value.split(",") if ev and ev.strip()]

    if not raw_events:
        return "*"
    if "*" in raw_events:
        return "*"

    for ev in raw_events:
        if ev not in VALID_WEBHOOK_EVENTS:
            raise ValueError(
                f"Invalid webhook event '{ev}'. Valid events are: {sorted(VALID_WEBHOOK_EVENTS)}."
            )

    return ", ".join(sorted(set(raw_events)))


def normalize_webhook_secret(value: str | None) -> str:
    """Validate optional HMAC secret string."""
    if value is None:
        return ""
    secret = value.strip()
    if len(secret) > MAX_WEBHOOK_SECRET_LENGTH:
        raise ValueError(
            f"Webhook secret must be at most {MAX_WEBHOOK_SECRET_LENGTH} characters."
        )
    return secret


def normalize_macro_title(value: str | None) -> str:
    """Validate macro title, raising ValueError if blank or too long."""
    title = (value or "").strip()
    if not title:
        raise ValueError("Macro title must not be blank.")
    if len(title) > MAX_MACRO_TITLE_LENGTH:
        raise ValueError(f"Macro title must be at most {MAX_MACRO_TITLE_LENGTH} characters.")
    return title


def normalize_macro_shortcut(value: str | None) -> str:
    """Validate macro shortcut, ensuring slash prefix and alphanumeric characters."""
    raw = (value or "").strip().lower()
    if not raw:
        raise ValueError("Macro shortcut must not be blank.")
    shortcut = raw if raw.startswith("/") else f"/{raw}"
    if len(shortcut) > MAX_MACRO_SHORTCUT_LENGTH:
        raise ValueError(
            f"Macro shortcut must be at most {MAX_MACRO_SHORTCUT_LENGTH} characters."
        )
    identifier = shortcut[1:]
    if not identifier or not all(c.isalnum() or c in "-_" for c in identifier):
        raise ValueError(
            "Macro shortcut must contain only alphanumeric characters, hyphens, and underscores."
        )
    return shortcut


def normalize_macro_category(value: str | None) -> str:
    """Validate macro category, defaulting to 'General' if blank."""
    category = (value or "").strip()
    if not category:
        return "General"
    if len(category) > MAX_MACRO_CATEGORY_LENGTH:
        raise ValueError(
            f"Macro category must be at most {MAX_MACRO_CATEGORY_LENGTH} characters."
        )
    return category


def normalize_macro_content(value: str | None) -> str:
    """Validate macro content, raising ValueError if blank or too long."""
    content = (value or "").strip()
    if not content:
        raise ValueError("Macro content must not be blank.")
    if len(content) > MAX_MACRO_CONTENT_LENGTH:
        raise ValueError(
            f"Macro content must be at most {MAX_MACRO_CONTENT_LENGTH} characters."
        )
    return content


def normalize_macro_status_action(value: str | None) -> str | None:
    """Validate optional status action against valid session statuses."""
    if not value or not str(value).strip():
        return None
    status = str(value).strip().lower()
    if status not in VALID_SESSION_STATUSES:
        valid_options = ", ".join(sorted(VALID_SESSION_STATUSES))
        raise ValueError(f"Invalid status_action '{value}'. Must be one of: {valid_options}")
    return status


PREVIEW_MAX_LENGTH = 80


def get_db_connection():
    db_path = Path(DB_NAME)
    if db_path.parent != Path("."):
        db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def ping_db() -> None:
    """Verify database connectivity with a cheap query (used by readiness)."""
    with closing(get_db_connection()) as conn:
        conn.execute("SELECT 1").fetchone()


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


def get_session_latest_user_query(session_id: str | None) -> str | None:
    """Return the most recent user query for a given session, or None if no queries exist."""
    if not session_id or not session_id.strip():
        return None
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(_SELECT_LATEST_USER_QUERY, (session_id.strip(),))
        row = cursor.fetchone()
        if row and row["user_query"]:
            return str(row["user_query"])
    return None


def truncate_history(messages, max_turns):
    """Keep only the most recent turns (a turn is one human+AI pair)."""
    if max_turns is None or max_turns <= 0:
        return messages
    return messages[-2 * max_turns :]


def create_document_store():
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_DOC_STORE_TABLE)
        conn.execute(_CREATE_DOC_SOURCES_TABLE)
        conn.commit()


def migrate_document_store():
    """Add newer columns to pre-existing databases (no-op otherwise)."""
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_DOC_SOURCES_TABLE)
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(document_store)")]
        if "collection" not in columns:
            conn.execute(
                "ALTER TABLE document_store ADD COLUMN collection TEXT NOT NULL DEFAULT 'default'"
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


def save_document_source(
    file_id,
    source_text,
    strategy="recursive",
    chunk_size=1000,
    chunk_overlap=200,
):
    """Insert or refresh the stored source text and chunking options for a document."""
    with closing(get_db_connection()) as conn:
        conn.execute(
            _INSERT_DOC_SOURCE,
            (file_id, source_text, strategy, chunk_size, chunk_overlap),
        )
        conn.commit()


def get_document_source(file_id):
    """Return the stored source row (with chunking options) for a document, if any."""
    with closing(get_db_connection()) as conn:
        cursor = conn.execute(_SELECT_DOC_SOURCE, (file_id,))
        source = cursor.fetchone()
        return dict(source) if source else None


def get_document_sources_by_collection(collection):
    """Return all stored document source rows and options for a given collection."""
    with closing(get_db_connection()) as conn:
        cursor = conn.execute(_SELECT_DOC_SOURCES_BY_COLLECTION, (collection,))
        return [dict(row) for row in cursor.fetchall()]


def delete_document_source(file_id):
    """Remove the stored source text for a document, returning whether a row existed."""
    with closing(get_db_connection()) as conn:
        cursor = conn.execute(_DELETE_DOC_SOURCE, (file_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted


def delete_document_sources_by_collection(collection):
    """Remove stored source rows for every document in a collection."""
    with closing(get_db_connection()) as conn:
        cursor = conn.execute(_DELETE_DOC_SOURCES_BY_COLLECTION, (collection,))
        deleted = cursor.rowcount
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


def get_collections_details() -> list[dict]:
    """Return aggregated metrics per document collection."""
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        rows = cursor.execute(
            "SELECT id, filename, collection, upload_timestamp "
            "FROM document_store ORDER BY collection ASC, id ASC"
        ).fetchall()

    collections_map: dict[str, dict] = {}
    for row in rows:
        col = row["collection"]
        if col not in collections_map:
            collections_map[col] = {
                "collection": col,
                "document_count": 0,
                "file_formats": {},
                "earliest_upload": None,
                "latest_upload": None,
            }
        data = collections_map[col]
        data["document_count"] += 1

        filename = row["filename"] or ""
        ext = Path(filename).suffix.lstrip(".").lower() or "unknown"
        data["file_formats"][ext] = data["file_formats"].get(ext, 0) + 1

        ts = str(row["upload_timestamp"]) if row["upload_timestamp"] else None
        if ts:
            if data["earliest_upload"] is None or ts < data["earliest_upload"]:
                data["earliest_upload"] = ts
            if data["latest_upload"] is None or ts > data["latest_upload"]:
                data["latest_upload"] = ts

    return list(collections_map.values())


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
        feedback_up = cursor.execute("SELECT COUNT(*) FROM feedback WHERE rating = 1").fetchone()[0]
        feedback_down = cursor.execute(
            "SELECT COUNT(*) FROM feedback WHERE rating = -1"
        ).fetchone()[0]
        return {
            "documents": documents,
            "collections": collections,
            "sessions": sessions,
            "messages": messages,
            "feedback_up": feedback_up,
            "feedback_down": feedback_down,
        }


def _truncate_preview(preview: str | None) -> str:
    if not preview:
        return ""
    preview = preview.strip()
    if len(preview) <= PREVIEW_MAX_LENGTH:
        return preview
    return preview[: PREVIEW_MAX_LENGTH - 1].rstrip() + "…"


def get_all_sessions(status: str | None = None, tag: str | None = None):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        query = f"SELECT * FROM ({_SELECT_ALL_SESSIONS_BASE}) ORDER BY last_active DESC"
        cursor.execute(query)
        sessions = cursor.fetchall()
        results = []
        for session in sessions:
            s_dict = dict(session)
            if status:
                clean_status = status.strip().lower()
                if s_dict.get("status", "active").lower() != clean_status:
                    continue
            if tag:
                clean_tag = tag.strip().lower()
                raw_tags = s_dict.get("tags", "") or ""
                row_tags = [t.strip().lower() for t in raw_tags.split(",") if t.strip()]
                if clean_tag not in row_tags:
                    continue
            if not s_dict.get("label"):
                s_dict["label"] = None
            s_dict["preview"] = _truncate_preview(s_dict.get("preview"))
            results.append(s_dict)
        return results


def search_sessions(query: str, limit: int = 20) -> list[dict]:
    """Search sessions matching query text in user_query or gpt_response."""
    cleaned = (query or "").strip()
    if not cleaned:
        return []
    pattern = f"%{cleaned}%"
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(_SEARCH_SESSIONS, (pattern, pattern, max(1, limit)))
        rows = cursor.fetchall()
        results = []
        for row in rows:
            sid = row["session_id"]
            q_cursor = conn.cursor()
            q_cursor.execute(_SELECT_MATCHED_QUERIES, (sid, pattern, pattern))
            matched_queries = [r["user_query"] for r in q_cursor.fetchall() if r["user_query"]]
            results.append(
                {
                    "session_id": sid,
                    "label": row["label"] if row["label"] else None,
                    "status": row["status"] if row["status"] else "active",
                    "tags": row["tags"] if row["tags"] else "",
                    "match_count": row["match_count"],
                    "preview": _truncate_preview(row["preview"]),
                    "last_active": row["last_active"],
                    "matched_queries": matched_queries,
                }
            )
        return results


def delete_session(session_id):
    with closing(get_db_connection()) as conn:
        cursor = conn.execute(_DELETE_SESSION, (session_id,))
        deleted = cursor.rowcount > 0
        conn.execute(_DELETE_SESSION_LABEL, (session_id,))
        conn.execute(_DELETE_SESSION_FEEDBACK, (session_id,))
        conn.commit()
        return deleted


def delete_sessions(session_ids: list[str]) -> dict[str, str]:
    """Delete multiple sessions cascade; returns map of session_id to status."""
    results: dict[str, str] = {}

    with closing(get_db_connection()) as conn:
        for session_id in session_ids:
            cursor = conn.execute(_DELETE_SESSION, (session_id,))
            if cursor.rowcount > 0:
                conn.execute(_DELETE_SESSION_LABEL, (session_id,))
                conn.execute(_DELETE_SESSION_FEEDBACK, (session_id,))
                results[session_id] = "deleted"
            else:
                label_cursor = conn.execute(_DELETE_SESSION_LABEL, (session_id,))
                feedback_cursor = conn.execute(_DELETE_SESSION_FEEDBACK, (session_id,))
                if label_cursor.rowcount > 0 or feedback_cursor.rowcount > 0:
                    results[session_id] = "deleted"
                else:
                    results[session_id] = "not_found"
        conn.commit()
    return results


def prune_sessions_before(cutoff_iso):
    """Delete sessions inactive since `cutoff_iso`, returning the count."""
    with closing(get_db_connection()) as conn:
        rows = conn.execute(_STALE_SESSIONS, (cutoff_iso,)).fetchall()
        stale_ids = [row["session_id"] for row in rows]
        for session_id in stale_ids:
            conn.execute(_DELETE_SESSION, (session_id,))
            conn.execute(_DELETE_SESSION_LABEL, (session_id,))
            conn.execute(_DELETE_SESSION_FEEDBACK, (session_id,))
        conn.commit()
        return len(stale_ids)


def create_session_labels():
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_SESSION_LABELS_TABLE)
        conn.commit()


def create_feedback():
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_FEEDBACK_TABLE)
        conn.commit()


def migrate_feedback():
    """Add newer columns to feedback table if missing (no-op otherwise)."""
    with closing(get_db_connection()) as conn:
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(feedback)")]
        if "comment" not in columns:
            conn.execute("ALTER TABLE feedback ADD COLUMN comment TEXT")
        conn.commit()


def insert_feedback(session_id, rating, comment=None):
    """Record a +1/-1 answer rating with optional comment; raises ValueError for other ratings."""
    if rating not in (1, -1):
        raise ValueError("Rating must be 1 or -1.")
    clean_comment = comment.strip() if comment and isinstance(comment, str) else None
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(_INSERT_FEEDBACK, (session_id, rating, clean_comment))
        feedback_id = cursor.lastrowid
        conn.commit()
        return feedback_id


def list_feedback(
    rating=None,
    session_id=None,
    limit=50,
    offset=0,
):
    """List feedback with optional filters and pagination, returning (items, total)."""
    query = "SELECT id, session_id, rating, comment, created_at FROM feedback"

    count_query = "SELECT COUNT(*) FROM feedback"
    clauses = []
    params = []

    if rating is not None:
        clauses.append("rating = ?")
        params.append(rating)
    if session_id is not None:
        clauses.append("session_id = ?")
        params.append(session_id)

    if clauses:
        where_clause = " WHERE " + " AND ".join(clauses)
        query += where_clause
        count_query += where_clause

    query += " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?"
    query_params = list(params) + [limit, offset]

    with closing(get_db_connection()) as conn:
        total = conn.execute(count_query, params).fetchone()[0]
        rows = conn.execute(query, query_params).fetchall()
        items = [dict(row) for row in rows]
        return items, total


def get_session_feedback(session_id):
    """Return all feedback records for a specific session ordered by created_at."""
    query = (
        "SELECT id, session_id, rating, comment, created_at FROM feedback "
        "WHERE session_id = ? ORDER BY created_at ASC, id ASC"
    )
    with closing(get_db_connection()) as conn:
        rows = conn.execute(query, (session_id,)).fetchall()
        return [dict(row) for row in rows]


def count_feedback(rating):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(_SELECT_FEEDBACK_COUNT, (rating,))
        return cursor.fetchone()[0]


def get_feedback_analytics(recent_comments_limit: int = 5) -> dict:
    """Aggregate customer satisfaction (CSAT) and feedback metrics."""
    with closing(get_db_connection()) as conn:
        stats_query = (
            "SELECT "
            "COUNT(*) AS total_feedback, "
            "COALESCE(SUM(CASE WHEN rating = 1 THEN 1 ELSE 0 END), 0) AS positive_feedback, "
            "COALESCE(SUM(CASE WHEN rating = -1 THEN 1 ELSE 0 END), 0) AS negative_feedback, "
            "COALESCE(SUM(CASE WHEN comment IS NOT NULL AND trim(comment) != '' "
            "THEN 1 ELSE 0 END), 0) AS total_comments "
            "FROM feedback"
        )
        row = conn.execute(stats_query).fetchone()
        total = row["total_feedback"] if row else 0
        positive = row["positive_feedback"] if row else 0
        negative = row["negative_feedback"] if row else 0
        comments_count = row["total_comments"] if row else 0

        satisfaction_rate = round((positive / total * 100), 1) if total > 0 else 0.0
        comment_rate = round((comments_count / total * 100), 1) if total > 0 else 0.0

        comments_query = (
            "SELECT id, session_id, rating, comment, created_at FROM feedback "
            "WHERE comment IS NOT NULL AND trim(comment) != '' "
            "ORDER BY created_at DESC, id DESC LIMIT ?"
        )
        comment_rows = conn.execute(comments_query, (recent_comments_limit,)).fetchall()
        recent_comments = [dict(r) for r in comment_rows]

        return {
            "total_feedback": total,
            "positive_feedback": positive,
            "negative_feedback": negative,
            "satisfaction_rate": satisfaction_rate,
            "total_comments": comments_count,
            "comment_rate": comment_rate,
            "recent_comments": recent_comments,
        }


def migrate_session_labels():
    """Add newer columns (status, tags, summary, notes) to session_labels if missing."""
    with closing(get_db_connection()) as conn:
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(session_labels)")]
        if "status" not in columns:
            conn.execute(
                "ALTER TABLE session_labels ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
            )
        if "tags" not in columns:
            conn.execute("ALTER TABLE session_labels ADD COLUMN tags TEXT NOT NULL DEFAULT ''")
        if "summary" not in columns:
            conn.execute("ALTER TABLE session_labels ADD COLUMN summary TEXT DEFAULT ''")
        if "resolution_notes" not in columns:
            conn.execute("ALTER TABLE session_labels ADD COLUMN resolution_notes TEXT DEFAULT ''")
        conn.commit()


def update_session_metadata(  # noqa: PLR0913, PLR0917
    session_id: str,
    label: str | None = None,
    status: str | None = None,
    tags: str | list[str] | None = None,
    summary: str | None = None,
    resolution_notes: str | None = None,
) -> bool:
    """Update metadata (label, status, tags, summary, notes) for a session with history."""
    clean_label = normalize_session_label(label) if label is not None else None
    clean_status = normalize_session_status(status) if status is not None else None
    clean_tags = normalize_session_tags(tags) if tags is not None else None
    clean_summary = normalize_session_summary(summary) if summary is not None else None
    clean_notes = (
        normalize_resolution_notes(resolution_notes) if resolution_notes is not None else None
    )

    with closing(get_db_connection()) as conn:
        exists = conn.execute(_SESSION_HAS_LOGS, (session_id,)).fetchone() is not None
        if not exists:
            return False

        cur = conn.execute(
            "SELECT label, status, tags, summary, resolution_notes FROM session_labels "
            "WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if cur is None:
            new_label = clean_label or ""
            new_status = clean_status or "active"
            new_tags = clean_tags or ""
            new_summary = clean_summary or ""
            new_notes = clean_notes or ""
            conn.execute(
                "INSERT INTO session_labels "
                "(session_id, label, status, tags, summary, resolution_notes) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, new_label, new_status, new_tags, new_summary, new_notes),
            )
        else:
            new_label = clean_label if clean_label is not None else cur["label"]
            new_status = clean_status if clean_status is not None else cur["status"]
            new_tags = clean_tags if clean_tags is not None else cur["tags"]
            new_summary = clean_summary if clean_summary is not None else (cur["summary"] or "")
            new_notes = clean_notes if clean_notes is not None else (cur["resolution_notes"] or "")
            conn.execute(
                "UPDATE session_labels "
                "SET label = ?, status = ?, tags = ?, summary = ?, resolution_notes = ? "
                "WHERE session_id = ?",
                (new_label, new_status, new_tags, new_summary, new_notes, session_id),
            )
        conn.commit()
        return True


def get_session_metadata(session_id: str) -> dict | None:
    """Fetch label, status, tags, summary, and notes for a session, or None if unknown."""
    with closing(get_db_connection()) as conn:
        exists = conn.execute(_SESSION_HAS_LOGS, (session_id,)).fetchone() is not None
        if not exists:
            return None
        row = conn.execute(
            "SELECT label, status, tags, summary, resolution_notes FROM session_labels "
            "WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return {
                "session_id": session_id,
                "label": None,
                "status": "active",
                "tags": "",
                "summary": "",
                "resolution_notes": "",
            }
        return {
            "session_id": session_id,
            "label": row["label"] if row["label"] else None,
            "status": row["status"] if row["status"] else "active",
            "tags": row["tags"] if row["tags"] else "",
            "summary": row["summary"] if row["summary"] else "",
            "resolution_notes": row["resolution_notes"] if row["resolution_notes"] else "",
        }


def get_support_triage_analytics() -> dict:
    """Compute operational triage metrics across all customer support sessions."""
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        query = f"SELECT session_id, message_count, status, tags FROM ({_SELECT_ALL_SESSIONS_BASE})"
        rows = cursor.execute(query).fetchall()

        total_sessions = len(rows)
        if total_sessions == 0:
            return {
                "total_sessions": 0,
                "active_count": 0,
                "resolved_count": 0,
                "escalated_count": 0,
                "closed_count": 0,
                "resolution_rate": 0.0,
                "escalation_rate": 0.0,
                "avg_turns_per_session": 0.0,
                "top_tags": [],
            }

        active_count = 0
        resolved_count = 0
        escalated_count = 0
        closed_count = 0
        total_messages = 0
        tag_counter: Counter[str] = Counter()

        for r in rows:
            st = (r["status"] or "active").lower()
            if st == "resolved":
                resolved_count += 1
            elif st == "escalated":
                escalated_count += 1
            elif st == "closed":
                closed_count += 1
            else:
                active_count += 1

            total_messages += int(r["message_count"] or 0)
            raw_tags = r["tags"] or ""
            if raw_tags:
                for tag in raw_tags.split(","):
                    clean = tag.strip().lower()
                    if clean:
                        tag_counter[clean] += 1

        resolution_rate = round(((resolved_count + closed_count) / total_sessions) * 100.0, 2)
        escalation_rate = round((escalated_count / total_sessions) * 100.0, 2)
        avg_turns = round(total_messages / total_sessions, 2)

        top_tags = [
            {"tag": tag, "count": count}
            for tag, count in tag_counter.most_common(10)
        ]

        return {
            "total_sessions": total_sessions,
            "active_count": active_count,
            "resolved_count": resolved_count,
            "escalated_count": escalated_count,
            "closed_count": closed_count,
            "resolution_rate": resolution_rate,
            "escalation_rate": escalation_rate,
            "avg_turns_per_session": avg_turns,
            "top_tags": top_tags,
        }


def rename_session(session_id, label):
    """Label a session that has chat history; returns False when unknown."""
    return update_session_metadata(session_id, label=label)


def create_webhooks():
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_WEBHOOKS_TABLE)
        conn.execute(_CREATE_WEBHOOK_DELIVERY_LOGS_TABLE)
        conn.commit()


def create_webhook(
    url: str,
    events: str | list[str] | None = "*",
    secret: str | None = None,
    is_active: bool = True,
) -> dict:
    """Register a new webhook subscription, returning the created webhook dict."""
    clean_url = normalize_webhook_url(url)
    clean_events = normalize_webhook_events(events)
    clean_secret = normalize_webhook_secret(secret)
    active_int = 1 if is_active else 0

    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(_INSERT_WEBHOOK, (clean_url, clean_events, clean_secret, active_int))
        webhook_id = cursor.lastrowid
        conn.commit()
        row = conn.execute(_SELECT_WEBHOOK_BY_ID, (webhook_id,)).fetchone()
        return {
            "id": row["id"],
            "url": row["url"],
            "events": row["events"] or "*",
            "secret": row["secret"] or "",
            "is_active": bool(row["is_active"]),
            "failure_count": row["failure_count"],
            "created_at": row["created_at"],
        }


def get_webhook(webhook_id: int) -> dict | None:
    """Retrieve a single webhook subscription by its ID."""
    with closing(get_db_connection()) as conn:
        row = conn.execute(_SELECT_WEBHOOK_BY_ID, (webhook_id,)).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "url": row["url"],
            "events": row["events"] or "*",
            "secret": row["secret"] or "",
            "is_active": bool(row["is_active"]),
            "failure_count": row["failure_count"],
            "created_at": row["created_at"],
        }


def list_webhooks(active_only: bool = False, event: str | None = None) -> list[dict]:
    """List webhook subscriptions with optional active and event filters."""
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, url, events, secret, is_active, failure_count, created_at "
            "FROM webhooks ORDER BY id ASC"
        )
        rows = cursor.fetchall()
        results = []
        for row in rows:
            r_active = bool(row["is_active"])
            if active_only and not r_active:
                continue
            r_events = row["events"] or "*"
            if event is not None:
                clean_event = event.strip().lower()
                event_set = {e.strip() for e in r_events.split(",") if e.strip()}
                if "*" not in event_set and clean_event not in event_set:
                    continue
            results.append(
                {
                    "id": row["id"],
                    "url": row["url"],
                    "events": r_events,
                    "secret": row["secret"] or "",
                    "is_active": r_active,
                    "failure_count": row["failure_count"],
                    "created_at": row["created_at"],
                }
            )
        return results


def update_webhook(  # noqa: PLR0913, PLR0917
    webhook_id: int,
    url: str | None = None,
    events: str | list[str] | None = None,
    secret: str | None = None,
    is_active: bool | None = None,
    reset_failures: bool = False,
) -> dict | None:
    """Update fields on an existing webhook subscription."""
    with closing(get_db_connection()) as conn:
        row = conn.execute(_SELECT_WEBHOOK_BY_ID, (webhook_id,)).fetchone()
        if row is None:
            return None

        new_url = normalize_webhook_url(url) if url is not None else row["url"]
        new_events = normalize_webhook_events(events) if events is not None else row["events"]
        new_secret = normalize_webhook_secret(secret) if secret is not None else row["secret"]
        new_is_active = (
            (1 if is_active else 0) if is_active is not None else row["is_active"]
        )
        new_failure_count = 0 if reset_failures else row["failure_count"]

        conn.execute(
            "UPDATE webhooks SET url = ?, events = ?, secret = ?, is_active = ?, "
            "failure_count = ? WHERE id = ?",
            (new_url, new_events, new_secret, new_is_active, new_failure_count, webhook_id),
        )
        conn.commit()

        return {
            "id": webhook_id,
            "url": new_url,
            "events": new_events,
            "secret": new_secret,
            "is_active": bool(new_is_active),
            "failure_count": new_failure_count,
            "created_at": row["created_at"],
        }


def delete_webhook(webhook_id: int) -> bool:
    """Delete a webhook subscription and its delivery logs."""
    with closing(get_db_connection()) as conn:
        conn.execute(_DELETE_WEBHOOK_LOGS_BY_WEBHOOK, (webhook_id,))
        cursor = conn.execute(_DELETE_WEBHOOK, (webhook_id,))
        conn.commit()
        return bool(cursor.rowcount > 0)


def record_webhook_delivery(  # noqa: PLR0913, PLR0917
    webhook_id: int,
    event: str,
    url: str,
    status_code: int | None,
    success: bool,
    payload_preview: str = "",
    error_message: str | None = None,
) -> int:
    """Record a delivery log attempt, updating failure_count on the webhook."""
    clean_preview = (payload_preview or "")[:MAX_DELIVERY_PREVIEW_LENGTH]
    clean_error = (error_message or "")[:MAX_DELIVERY_ERROR_LENGTH] if error_message else None
    success_int = 1 if success else 0

    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            _INSERT_WEBHOOK_DELIVERY,
            (
                webhook_id,
                event,
                url,
                status_code,
                success_int,
                clean_preview,
                clean_error,
            ),
        )
        log_id = cursor.lastrowid
        if success:
            conn.execute(_RESET_WEBHOOK_FAILURE, (webhook_id,))
        else:
            conn.execute(_INCREMENT_WEBHOOK_FAILURE, (webhook_id,))
        conn.commit()
        return int(log_id) if log_id is not None else 0


def get_webhook_delivery_logs(
    webhook_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Return paginated delivery audit logs, optionally filtered by webhook_id."""
    query = (
        "SELECT id, webhook_id, event, url, status_code, success, "
        "payload_preview, error_message, delivered_at "
        "FROM webhook_delivery_logs"
    )
    count_query = "SELECT COUNT(*) FROM webhook_delivery_logs"
    clauses = []
    params = []

    if webhook_id is not None:
        clauses.append("webhook_id = ?")
        params.append(webhook_id)

    if clauses:
        where_clause = " WHERE " + " AND ".join(clauses)
        query += where_clause
        count_query += where_clause

    query += " ORDER BY delivered_at DESC, id DESC LIMIT ? OFFSET ?"
    query_params = list(params) + [limit, offset]

    with closing(get_db_connection()) as conn:
        total = conn.execute(count_query, params).fetchone()[0]
        rows = conn.execute(query, query_params).fetchall()
        items = [
            {
                "id": row["id"],
                "webhook_id": row["webhook_id"],
                "event": row["event"],
                "url": row["url"],
                "status_code": row["status_code"],
                "success": bool(row["success"]),
                "payload_preview": row["payload_preview"] or "",
                "error_message": row["error_message"],
                "delivered_at": row["delivered_at"],
            }
            for row in rows
        ]
        return items, total


DEFAULT_MACROS: list[dict] = [
    {
        "title": "Lease Renewal Offer",
        "shortcut": "/lease-renewal",
        "category": "Leasing",
        "content": (
            "Hello {customer_name},\n\n"
            "We would love to extend your stay with us! Your current lease is eligible "
            "for renewal. Please review the renewal options sent to your email or let us know "
            "if you would like to discuss custom lease terms.\n\n"
            "Best regards,\n{agent_name}\nProperty Management Team"
        ),
        "tags": "leasing, renewal",
        "status_action": "active",
    },
    {
        "title": "Emergency Maintenance Dispatch",
        "shortcut": "/emerg-maint",
        "category": "Maintenance",
        "content": (
            "Hello {customer_name},\n\n"
            "Thank you for alerting us regarding the urgent maintenance issue at unit {unit_id}. "
            "An emergency work order has been created, and our on-call technician has been "
            "dispatched.\n\n"
            "If you experience active water flooding, gas odor, or total power loss, please "
            "immediately call our 24/7 emergency dispatch line at {support_contact}.\n\n"
            "Ticket Reference: {session_id}"
        ),
        "tags": "maintenance, urgent, emergency",
        "status_action": "escalated",
    },
    {
        "title": "Routine Maintenance Scheduled",
        "shortcut": "/maint-scheduled",
        "category": "Maintenance",
        "content": (
            "Hello {customer_name},\n\n"
            "Your maintenance request for unit {unit_id} has been received and scheduled "
            "with our facilities team. A technician is estimated to visit within 24-48 business "
            "hours. You will receive an SMS update prior to arrival.\n\n"
            "Thank you for your cooperation!"
        ),
        "tags": "maintenance, routine",
        "status_action": "active",
    },
    {
        "title": "Online Rent Payment Instructions",
        "shortcut": "/rent-pay",
        "category": "Billing",
        "content": (
            "Hello {customer_name},\n\n"
            "Rent payments can be submitted securely online through our resident portal at "
            "https://portal.propertymanager.com.\n\n"
            "Accepted payment methods include ACH direct debit (no convenience fee), "
            "credit card, and debit card. Rent is due on the 1st of each month with a grace "
            "period through the 5th.\n\n"
            "If you have any questions regarding your statement, please let us know."
        ),
        "tags": "billing, rent, payment",
        "status_action": "resolved",
    },
    {
        "title": "Move-Out Inspection & Deposit Timeline",
        "shortcut": "/move-out",
        "category": "Leasing",
        "content": (
            "Hello {customer_name},\n\n"
            "As your move-out date approaches, please note that a final walkthrough inspection "
            "will be conducted within 48 hours of key handover. Any refundable security deposit, "
            "accompanied by an itemized deduction statement, will be processed within 21 business "
            "days in accordance with state regulations.\n\n"
            "Please ensure you provide your forwarding mailing address."
        ),
        "tags": "move-out, deposit, inspection",
        "status_action": "resolved",
    },
    {
        "title": "General Inquiry Resolution",
        "shortcut": "/resolve",
        "category": "General",
        "content": (
            "Hello {customer_name},\n\n"
            "I am glad I could assist you with your inquiry today! Please don't hesitate to "
            "reach back out if there is anything else we can help you with.\n\n"
            "Have a wonderful day!\n{agent_name}"
        ),
        "tags": "general, closing",
        "status_action": "resolved",
    },
]


def _format_macro_row(row: sqlite3.Row) -> dict:
    raw_tags = row["tags"] or ""
    tags_list = [t.strip() for t in raw_tags.split(",") if t.strip()]
    return {
        "id": row["id"],
        "title": row["title"],
        "shortcut": row["shortcut"],
        "category": row["category"],
        "content": row["content"],
        "tags": tags_list,
        "status_action": row["status_action"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def seed_default_macros(force: bool = False) -> int:
    """Seed standard property management default macros if table is empty."""
    with closing(get_db_connection()) as conn:
        if not force:
            count = conn.execute("SELECT COUNT(*) FROM support_macros").fetchone()[0]
            if count > 0:
                return 0
        inserted = 0
        for item in DEFAULT_MACROS:
            existing = conn.execute(
                _SELECT_MACRO_BY_SHORTCUT, (item["shortcut"],)
            ).fetchone()
            if not existing:
                conn.execute(
                    _INSERT_SUPPORT_MACRO,
                    (
                        item["title"],
                        item["shortcut"],
                        item["category"],
                        item["content"],
                        normalize_session_tags(item.get("tags")),
                        item.get("status_action"),
                    ),
                )
                inserted += 1
        conn.commit()
        return inserted


def create_support_macros() -> None:
    """Create support_macros table and indices, seeding initial templates."""
    db_path = Path(DB_NAME)
    if db_path.parent != Path("."):
        db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_SUPPORT_MACROS_TABLE)
        conn.execute(_CREATE_MACRO_CATEGORY_INDEX)
        conn.execute(_CREATE_MACRO_SHORTCUT_INDEX)
        conn.commit()
    seed_default_macros()


def create_macro(  # noqa: PLR0913, PLR0917
    title: str,
    shortcut: str,
    content: str,
    category: str = "General",
    tags: str | list[str] | None = None,
    status_action: str | None = None,
) -> dict:
    """Register a new macro template."""
    norm_title = normalize_macro_title(title)
    norm_shortcut = normalize_macro_shortcut(shortcut)
    norm_category = normalize_macro_category(category)
    norm_content = normalize_macro_content(content)
    norm_tags = normalize_session_tags(tags)
    norm_status = normalize_macro_status_action(status_action)

    with closing(get_db_connection()) as conn:
        existing = conn.execute(_SELECT_MACRO_BY_SHORTCUT, (norm_shortcut,)).fetchone()
        if existing:
            raise ValueError(f"Macro shortcut '{norm_shortcut}' already exists.")
        cursor = conn.execute(
            _INSERT_SUPPORT_MACRO,
            (norm_title, norm_shortcut, norm_category, norm_content, norm_tags, norm_status),
        )
        macro_id = cursor.lastrowid
        conn.commit()
        row = conn.execute(_SELECT_MACRO_BY_ID, (macro_id,)).fetchone()
        return _format_macro_row(row)


def get_macro(macro_id: int) -> dict | None:
    """Retrieve a macro by ID."""
    with closing(get_db_connection()) as conn:
        row = conn.execute(_SELECT_MACRO_BY_ID, (macro_id,)).fetchone()
        return _format_macro_row(row) if row else None


def get_macro_by_shortcut(shortcut: str) -> dict | None:
    """Retrieve a macro by its trigger shortcut."""
    norm_shortcut = normalize_macro_shortcut(shortcut)
    with closing(get_db_connection()) as conn:
        row = conn.execute(_SELECT_MACRO_BY_SHORTCUT, (norm_shortcut,)).fetchone()
        return _format_macro_row(row) if row else None


def list_macros(
    category: str | None = None,
    tag: str | None = None,
    search: str | None = None,
) -> list[dict]:
    """List macros with optional filtering by category, tag, or search term."""
    query = (
        "SELECT id, title, shortcut, category, content, tags, "
        "status_action, created_at, updated_at "
        "FROM support_macros"
    )
    clauses = []
    params = []
    if category and category.strip():
        clauses.append("LOWER(category) = LOWER(?)")
        params.append(category.strip())
    if search and search.strip():
        term = f"%{search.strip()}%"
        clauses.append("(title LIKE ? OR shortcut LIKE ? OR content LIKE ?)")
        params.extend([term, term, term])
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY category ASC, title ASC"

    with closing(get_db_connection()) as conn:
        rows = conn.execute(query, params).fetchall()
        macros = [_format_macro_row(row) for row in rows]
        if tag and tag.strip():
            target_tag = tag.strip().lower()
            macros = [m for m in macros if any(target_tag == t.lower() for t in m["tags"])]
        return macros


def list_macro_categories() -> list[str]:
    """Return distinct categories across all registered macros."""
    with closing(get_db_connection()) as conn:
        rows = conn.execute(_SELECT_MACRO_CATEGORIES).fetchall()
        return [row["category"] for row in rows if row["category"]]


def update_macro(  # noqa: PLR0913, PLR0917
    macro_id: int,
    title: str | None = None,
    shortcut: str | None = None,
    category: str | None = None,
    content: str | None = None,
    tags: str | list[str] | None = None,
    status_action: str | None = None,
) -> dict | None:
    """Update macro template attributes."""
    updates: list[str] = []
    params: list[Any] = []
    if title is not None:
        updates.append("title = ?")
        params.append(normalize_macro_title(title))
    if shortcut is not None:
        norm_sc = normalize_macro_shortcut(shortcut)
        with closing(get_db_connection()) as conn:
            existing = conn.execute(
                "SELECT id FROM support_macros WHERE LOWER(shortcut) = LOWER(?) AND id != ?",
                (norm_sc, macro_id),
            ).fetchone()
            if existing:
                raise ValueError(f"Macro shortcut '{norm_sc}' is already taken.")
        updates.append("shortcut = ?")
        params.append(norm_sc)
    if category is not None:
        updates.append("category = ?")
        params.append(normalize_macro_category(category))
    if content is not None:
        updates.append("content = ?")
        params.append(normalize_macro_content(content))
    if tags is not None:
        updates.append("tags = ?")
        params.append(normalize_session_tags(tags))
    if status_action is not None:
        updates.append("status_action = ?")
        params.append(normalize_macro_status_action(status_action))

    if not updates:
        return get_macro(macro_id)

    updates.append("updated_at = CURRENT_TIMESTAMP")
    params.append(macro_id)
    sql = f"UPDATE support_macros SET {', '.join(updates)} WHERE id = ?"
    with closing(get_db_connection()) as conn:
        cursor = conn.execute(sql, params)
        if cursor.rowcount == 0:
            return None
        conn.commit()
        row = conn.execute(_SELECT_MACRO_BY_ID, (macro_id,)).fetchone()
        return _format_macro_row(row) if row else None


def delete_macro(macro_id: int) -> bool:
    """Delete a macro template by ID."""
    with closing(get_db_connection()) as conn:
        cursor = conn.execute(_DELETE_SUPPORT_MACRO, (macro_id,))
        conn.commit()
        return bool(cursor.rowcount and cursor.rowcount > 0)


# Initialize the database tables
create_application_logs()
create_document_store()
migrate_document_store()
create_session_labels()
migrate_session_labels()
create_feedback()
migrate_feedback()
create_webhooks()
create_support_macros()


