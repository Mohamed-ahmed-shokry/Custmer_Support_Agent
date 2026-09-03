import sqlite3
from contextlib import closing
from pathlib import Path

from api.settings import settings

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
    "filename TEXT, upload_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)

_INSERT_APP_LOG = (
    "INSERT INTO application_logs (session_id, user_query, gpt_response, model) "
    "VALUES (?, ?, ?, ?)"
)

_SELECT_CHAT_HISTORY = (
    "SELECT user_query, gpt_response FROM application_logs "
    "WHERE session_id = ? ORDER BY created_at ASC, id ASC"
)

_INSERT_DOC_RECORD = "INSERT INTO document_store (filename) VALUES (?)"

_SELECT_DOC_RECORD = (
    "SELECT id, filename, upload_timestamp FROM document_store WHERE id = ?"
)

_DELETE_DOC_RECORD = "DELETE FROM document_store WHERE id = ?"

_SELECT_ALL_DOCS = (
    "SELECT id, filename, upload_timestamp FROM document_store "
    "ORDER BY upload_timestamp DESC, id DESC"
)


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


def insert_document_record(filename):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(_INSERT_DOC_RECORD, (filename,))
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


def get_all_documents():
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(_SELECT_ALL_DOCS)
        documents = cursor.fetchall()
        return [dict(doc) for doc in documents]


# Initialize the database tables
create_application_logs()
create_document_store()
