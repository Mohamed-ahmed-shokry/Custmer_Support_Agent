import sqlite3
from contextlib import closing
from pathlib import Path

from api.settings import settings

DB_NAME = settings.sqlite_db_path

def get_db_connection():
    db_path = Path(DB_NAME)
    if db_path.parent != Path("."):
        db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def create_application_logs():
    with closing(get_db_connection()) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS application_logs
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         session_id TEXT,
                         user_query TEXT,
                         gpt_response TEXT,
                         model TEXT,
                         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()

def insert_application_logs(session_id, user_query, gpt_response, model):
    with closing(get_db_connection()) as conn:
        conn.execute('INSERT INTO application_logs (session_id, user_query, gpt_response, model) VALUES (?, ?, ?, ?)',
                     (session_id, user_query, gpt_response, model))
        conn.commit()

def get_chat_history(session_id):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT user_query, gpt_response FROM application_logs WHERE session_id = ? ORDER BY created_at ASC, id ASC', (session_id,))
        messages = []
        for row in cursor.fetchall():
            messages.extend([
                {"role": "human", "content": row['user_query']},
                {"role": "ai", "content": row['gpt_response']}
            ])
        return messages

def create_document_store():
    with closing(get_db_connection()) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS document_store
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         filename TEXT,
                         upload_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()

def insert_document_record(filename):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO document_store (filename) VALUES (?)', (filename,))
        file_id = cursor.lastrowid
        conn.commit()
        return file_id

def get_document_record(file_id):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, filename, upload_timestamp FROM document_store WHERE id = ?', (file_id,))
        document = cursor.fetchone()
        return dict(document) if document else None

def delete_document_record(file_id):
    with closing(get_db_connection()) as conn:
        cursor = conn.execute('DELETE FROM document_store WHERE id = ?', (file_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted

def get_all_documents():
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, filename, upload_timestamp FROM document_store ORDER BY upload_timestamp DESC, id DESC')
        documents = cursor.fetchall()
        return [dict(doc) for doc in documents]

# Initialize the database tables
create_application_logs()
create_document_store()
