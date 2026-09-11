import sqlite3
from contextlib import closing

from api import db_utils


def initialize_temp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "nested" / "test.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(db_path))
    db_utils.create_application_logs()
    db_utils.create_document_store()
    db_utils.create_session_labels()
    db_utils.create_feedback()
    return db_path


def test_database_helpers_create_parent_directory(monkeypatch, tmp_path):
    db_path = initialize_temp_db(monkeypatch, tmp_path)

    assert db_path.exists()


def test_chat_history_is_returned_in_insert_order(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    db_utils.insert_application_logs("session-1", "First question", "First answer", "gpt-4o-mini")
    db_utils.insert_application_logs("session-1", "Second question", "Second answer", "gpt-4o-mini")
    db_utils.insert_application_logs("session-2", "Other question", "Other answer", "gpt-4o-mini")

    assert db_utils.get_chat_history("session-1") == [
        {"role": "human", "content": "First question"},
        {"role": "ai", "content": "First answer"},
        {"role": "human", "content": "Second question"},
        {"role": "ai", "content": "Second answer"},
    ]


def test_get_all_sessions_returns_counts(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    assert db_utils.get_all_sessions() == []

    db_utils.insert_application_logs("session-1", "Q1", "A1", "gpt-4o-mini")
    db_utils.insert_application_logs("session-1", "Q2", "A2", "gpt-4o-mini")
    db_utils.insert_application_logs("session-2", "Q3", "A3", "gpt-4o-mini")

    sessions = {s["session_id"]: s["message_count"] for s in db_utils.get_all_sessions()}
    assert sessions == {"session-1": 2, "session-2": 1}


def test_get_all_sessions_includes_first_question_preview(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    db_utils.insert_application_logs("session-1", "First question here", "A1", "gpt-4o-mini")
    db_utils.insert_application_logs("session-1", "Second question", "A2", "gpt-4o-mini")
    long_question = "Q" * 200
    db_utils.insert_application_logs("session-2", long_question, "A3", "gpt-4o-mini")

    previews = {s["session_id"]: s["preview"] for s in db_utils.get_all_sessions()}
    assert previews["session-1"] == "First question here"
    assert previews["session-2"] == "Q" * 79 + "…"


def test_prune_sessions_before_cutoff(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    db_utils.insert_application_logs("old-session", "Q1", "A1", "gpt-4o-mini")
    db_utils.insert_application_logs("new-session", "Q2", "A2", "gpt-4o-mini")
    db_utils.rename_session("old-session", "Old label")
    db_utils.insert_feedback("old-session", 1)
    with closing(db_utils.get_db_connection()) as conn:
        conn.execute(
            "UPDATE application_logs SET created_at = '2020-01-01 00:00:00' "
            "WHERE session_id = 'old-session'"
        )
        conn.commit()

    assert db_utils.prune_sessions_before("2021-01-01T00:00:00") == 1
    remaining = [s["session_id"] for s in db_utils.get_all_sessions()]
    assert remaining == ["new-session"]
    assert db_utils.prune_sessions_before("2021-01-01T00:00:00") == 0


def test_delete_session_removes_history(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    db_utils.insert_application_logs("session-1", "Q1", "A1", "gpt-4o-mini")

    assert db_utils.delete_session("session-1") is True
    assert db_utils.delete_session("session-1") is False
    assert db_utils.get_chat_history("session-1") == []


def test_rename_session_labels_known_session(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    db_utils.insert_application_logs("session-1", "Q1", "A1", "gpt-4o-mini")

    assert db_utils.rename_session("session-1", "Lease questions") is True
    assert db_utils.rename_session("missing", "Other") is False

    labels = {s["session_id"]: s["label"] for s in db_utils.get_all_sessions()}
    assert labels == {"session-1": "Lease questions"}


def test_rename_session_rejects_bad_labels():
    for bad in [None, "", "   ", "x" * 81]:
        try:
            db_utils.normalize_session_label(bad)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {bad!r}")
    assert db_utils.normalize_session_label("  Lease Qs  ") == "Lease Qs"


def test_delete_session_removes_label(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    db_utils.insert_application_logs("session-1", "Q1", "A1", "gpt-4o-mini")
    db_utils.rename_session("session-1", "Lease questions")

    assert db_utils.delete_session("session-1") is True
    assert db_utils.get_all_sessions() == []


def test_delete_documents_by_collection(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    db_utils.insert_document_record("a.pdf", "clients-acme")
    db_utils.insert_document_record("b.pdf", "clients-acme")
    db_utils.insert_document_record("c.pdf", "default")

    expected_deleted = 2
    assert db_utils.delete_documents_by_collection("clients-acme") == expected_deleted
    assert db_utils.delete_documents_by_collection("clients-acme") == 0
    assert [d["filename"] for d in db_utils.get_all_documents()] == ["c.pdf"]


def test_truncate_history_keeps_recent_turns():
    messages = [{"role": "human", "content": f"Q{i}"} for i in range(6)]

    assert db_utils.truncate_history(messages, 2) == messages[-4:]
    assert db_utils.truncate_history(messages, 10) == messages
    assert db_utils.truncate_history(messages, 0) == messages
    assert db_utils.truncate_history(messages, None) == messages
    assert db_utils.truncate_history([], 2) == []


def test_get_library_stats_counts_without_loading_rows(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    assert db_utils.get_library_stats() == {
        "documents": 0,
        "collections": 0,
        "sessions": 0,
        "messages": 0,
        "feedback_up": 0,
        "feedback_down": 0,
    }

    db_utils.insert_document_record("a.pdf", "acme")
    db_utils.insert_document_record("b.pdf", "acme")
    db_utils.insert_application_logs("s1", "Q1", "A1", "gpt-4o-mini")
    db_utils.insert_application_logs("s1", "Q2", "A2", "gpt-4o-mini")
    db_utils.insert_application_logs("s2", "Q3", "A3", "gpt-4o-mini")
    db_utils.insert_feedback("s1", 1)
    db_utils.insert_feedback("s2", -1)

    assert db_utils.get_library_stats() == {
        "documents": 2,
        "collections": 1,
        "sessions": 2,
        "messages": 3,
        "feedback_up": 1,
        "feedback_down": 1,
    }


def test_rename_collection_moves_records(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    db_utils.insert_document_record("a.pdf", "clients-acme")
    db_utils.insert_document_record("b.pdf", "default")

    assert db_utils.rename_collection("clients-acme", "clients-globex") == 1
    assert db_utils.rename_collection("missing", "other") == 0
    assert db_utils.get_all_collections() == ["clients-globex", "default"]


def test_feedback_records_and_counts_ratings(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    assert db_utils.count_feedback(1) == 0

    db_utils.insert_feedback("session-1", 1)
    db_utils.insert_feedback("session-1", 1)
    db_utils.insert_feedback("session-2", -1)

    expected_upvotes = 2
    assert db_utils.count_feedback(1) == expected_upvotes
    assert db_utils.count_feedback(-1) == 1


def test_feedback_rejects_invalid_ratings(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    for bad in [0, 2, -2]:
        try:
            db_utils.insert_feedback("session-1", bad)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {bad!r}")


def test_document_record_defaults_to_default_collection(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    file_id = db_utils.insert_document_record("lease.pdf")

    assert db_utils.get_document_record(file_id)["collection"] == "default"


def test_documents_filter_by_collection(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    db_utils.insert_document_record("a.pdf", "clients-acme")
    db_utils.insert_document_record("b.pdf", "clients-globex")
    db_utils.insert_document_record("c.pdf", "clients-acme")

    assert [d["filename"] for d in db_utils.get_all_documents("clients-acme")] == [
        "c.pdf",
        "a.pdf",
    ]
    assert db_utils.get_all_collections() == ["clients-acme", "clients-globex"]


def test_normalize_collection_accepts_and_rejects(monkeypatch, tmp_path):
    assert db_utils.normalize_collection(None) == "default"
    assert db_utils.normalize_collection("  Clients_Acme-1 ") == "clients_acme-1"
    for bad in ["has space!", "semi;colon", "a" * 65, "-leading"]:
        try:
            db_utils.normalize_collection(bad)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {bad!r}")


def test_migrate_document_store_adds_collection_column(monkeypatch, tmp_path):
    db_path = tmp_path / "legacy.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(db_path))
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE document_store (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "filename TEXT, upload_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.execute("INSERT INTO document_store (filename) VALUES ('legacy.pdf')")
    conn.commit()
    conn.close()

    db_utils.migrate_document_store()

    assert db_utils.get_document_record(1)["collection"] == "default"


def test_document_lookup_by_hash(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    assert db_utils.get_document_by_hash("abc123") is None

    file_id = db_utils.insert_document_record("lease.pdf", "default", "abc123")

    match = db_utils.get_document_by_hash("abc123")
    assert match["id"] == file_id
    assert match["filename"] == "lease.pdf"


def test_document_record_lifecycle(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    first_id = db_utils.insert_document_record("first.pdf")
    second_id = db_utils.insert_document_record("second.pdf")

    assert db_utils.get_document_record(first_id)["filename"] == "first.pdf"
    assert [document["id"] for document in db_utils.get_all_documents()] == [second_id, first_id]
    assert db_utils.delete_document_record(first_id) is True
    assert db_utils.delete_document_record(first_id) is False
    assert db_utils.get_document_record(first_id) is None
