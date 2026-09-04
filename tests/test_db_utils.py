from api import db_utils


def initialize_temp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "nested" / "test.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(db_path))
    db_utils.create_application_logs()
    db_utils.create_document_store()
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


def test_document_record_lifecycle(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    first_id = db_utils.insert_document_record("first.pdf")
    second_id = db_utils.insert_document_record("second.pdf")

    assert db_utils.get_document_record(first_id)["filename"] == "first.pdf"
    assert [document["id"] for document in db_utils.get_all_documents()] == [second_id, first_id]
    assert db_utils.delete_document_record(first_id) is True
    assert db_utils.delete_document_record(first_id) is False
    assert db_utils.get_document_record(first_id) is None
