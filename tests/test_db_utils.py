import sqlite3
from contextlib import closing

import pytest
from api import db_utils


def initialize_temp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "nested" / "test.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(db_path))
    db_utils.create_application_logs()
    db_utils.create_document_store()
    db_utils.create_session_labels()
    db_utils.migrate_session_labels()
    db_utils.create_feedback()
    db_utils.create_webhooks()
    db_utils.create_support_macros()
    db_utils.create_sla_policies()
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


def test_delete_sessions_cascade_and_reports(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    db_utils.insert_application_logs("session-1", "Q1", "A1", "gpt-4o-mini")
    db_utils.rename_session("session-1", "Lease questions")
    db_utils.insert_feedback("session-1", 1)

    db_utils.insert_application_logs("session-2", "Q2", "A2", "gpt-4o-mini")

    reports = db_utils.delete_sessions(["session-1", "session-2", "session-missing"])
    assert reports == {
        "session-1": "deleted",
        "session-2": "deleted",
        "session-missing": "not_found",
    }
    assert db_utils.get_chat_history("session-1") == []
    assert db_utils.get_chat_history("session-2") == []
    assert db_utils.get_all_sessions() == []
    assert db_utils.count_feedback(1) == 0


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


def test_feedback_with_comment_and_listing(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    db_utils.insert_feedback("session-1", 1, "Great answer!")
    db_utils.insert_feedback("session-1", -1, "Too brief.")
    db_utils.insert_feedback("session-2", 1, None)

    all_items, total = db_utils.list_feedback()
    expected_total = 3
    assert total == expected_total
    assert len(all_items) == expected_total

    pos_items, pos_total = db_utils.list_feedback(rating=1)
    expected_pos = 2
    assert pos_total == expected_pos
    assert len(pos_items) == expected_pos

    s1_items, s1_total = db_utils.list_feedback(session_id="session-1")
    assert s1_total == expected_pos
    assert len(s1_items) == expected_pos

    expected_page1 = 2
    expected_page2 = 1
    page1, _ = db_utils.list_feedback(limit=expected_page1, offset=0)
    assert len(page1) == expected_page1
    page2, _ = db_utils.list_feedback(limit=expected_page1, offset=expected_page1)
    assert len(page2) == expected_page2


def test_get_session_feedback(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    db_utils.insert_feedback("session-1", 1, "Helpful")
    db_utils.insert_feedback("session-2", -1, "Not helpful")
    db_utils.insert_feedback("session-1", -1, "Wait, incorrect info")

    s1_feedback = db_utils.get_session_feedback("session-1")
    expected_count = 2
    assert len(s1_feedback) == expected_count
    assert s1_feedback[0]["comment"] == "Helpful"
    assert s1_feedback[1]["comment"] == "Wait, incorrect info"

    assert db_utils.get_session_feedback("missing") == []


def test_migrate_feedback_adds_comment_column(monkeypatch, tmp_path):
    db_path = tmp_path / "legacy.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(db_path))
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute(
            "CREATE TABLE feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "session_id TEXT NOT NULL, rating INTEGER NOT NULL, "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.execute("INSERT INTO feedback (session_id, rating) VALUES ('s1', 1)")
        conn.commit()

    db_utils.migrate_feedback()

    with closing(db_utils.get_db_connection()) as conn:
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(feedback)")]
        assert "comment" in columns


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


def test_document_source_roundtrip_with_default_options(monkeypatch, tmp_path):
    expected_size = 1000
    expected_overlap = 200
    initialize_temp_db(monkeypatch, tmp_path)
    file_id = db_utils.insert_document_record("notes.txt")

    db_utils.save_document_source(file_id, "Source text here.")

    source = db_utils.get_document_source(file_id)
    assert source["file_id"] == file_id
    assert source["source_text"] == "Source text here."
    assert source["strategy"] == "recursive"
    assert source["chunk_size"] == expected_size
    assert source["chunk_overlap"] == expected_overlap


def test_document_source_saves_explicit_options(monkeypatch, tmp_path):
    expected_size = 400
    expected_overlap = 50
    initialize_temp_db(monkeypatch, tmp_path)
    file_id = db_utils.insert_document_record("notes.txt")

    db_utils.save_document_source(file_id, "Text.", "semantic", expected_size, expected_overlap)

    source = db_utils.get_document_source(file_id)
    assert source["strategy"] == "semantic"
    assert source["chunk_size"] == expected_size
    assert source["chunk_overlap"] == expected_overlap


def test_document_source_upsert_refreshes_options(monkeypatch, tmp_path):
    refreshed_size = 300
    refreshed_overlap = 30
    initialize_temp_db(monkeypatch, tmp_path)
    file_id = db_utils.insert_document_record("notes.txt")

    db_utils.save_document_source(file_id, "Original text.", "recursive", 1000, 200)
    db_utils.save_document_source(
        file_id, "Rewritten text.", "markdown", refreshed_size, refreshed_overlap
    )

    source = db_utils.get_document_source(file_id)
    assert source["source_text"] == "Rewritten text."
    assert source["strategy"] == "markdown"
    assert source["chunk_size"] == refreshed_size
    assert source["chunk_overlap"] == refreshed_overlap
    assert source["updated_at"] is not None


def test_document_source_missing_returns_none(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    assert db_utils.get_document_source(999) is None


def test_document_source_deletion(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)
    file_id = db_utils.insert_document_record("notes.txt")
    db_utils.save_document_source(file_id, "Text.")

    assert db_utils.delete_document_source(file_id) is True
    assert db_utils.get_document_source(file_id) is None
    assert db_utils.delete_document_source(file_id) is False


def test_delete_document_sources_by_collection(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)
    first_id = db_utils.insert_document_record("a.txt", "legal")
    second_id = db_utils.insert_document_record("b.txt", "legal")
    default_id = db_utils.insert_document_record("c.txt", "default")
    db_utils.save_document_source(first_id, "A.")
    db_utils.save_document_source(second_id, "B.")
    db_utils.save_document_source(default_id, "C.")

    expected_deleted = 2
    assert db_utils.delete_document_sources_by_collection("legal") == expected_deleted
    assert db_utils.get_document_source(first_id) is None
    assert db_utils.get_document_source(second_id) is None
    assert db_utils.get_document_source(default_id) is not None


def test_get_document_sources_by_collection(monkeypatch, tmp_path):
    expected_sources_count = 2
    expected_size = 500
    expected_overlap = 50
    initialize_temp_db(monkeypatch, tmp_path)
    first_id = db_utils.insert_document_record("a.txt", "hr")
    second_id = db_utils.insert_document_record("b.txt", "hr")
    other_id = db_utils.insert_document_record("c.txt", "sales")

    db_utils.save_document_source(
        first_id, "Source text A", "semantic", expected_size, expected_overlap
    )
    db_utils.save_document_source(second_id, "Source text B", "recursive", 800, 100)
    db_utils.save_document_source(other_id, "Source text C", "markdown", 1000, 200)

    hr_sources = db_utils.get_document_sources_by_collection("hr")
    assert len(hr_sources) == expected_sources_count
    assert hr_sources[0]["file_id"] == first_id
    assert hr_sources[0]["filename"] == "a.txt"
    assert hr_sources[0]["source_text"] == "Source text A"
    assert hr_sources[0]["strategy"] == "semantic"
    assert hr_sources[0]["chunk_size"] == expected_size
    assert hr_sources[0]["chunk_overlap"] == expected_overlap

    assert hr_sources[1]["file_id"] == second_id
    assert hr_sources[1]["filename"] == "b.txt"
    assert hr_sources[1]["source_text"] == "Source text B"
    assert hr_sources[1]["strategy"] == "recursive"

    empty_sources = db_utils.get_document_sources_by_collection("nonexistent")
    assert empty_sources == []


def test_migrate_document_store_creates_document_sources(monkeypatch, tmp_path):
    db_path = tmp_path / "legacy.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(db_path))
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE document_store (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "filename TEXT, upload_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.commit()
    conn.close()

    db_utils.migrate_document_store()

    file_id = db_utils.insert_document_record("legacy.pdf")
    db_utils.save_document_source(file_id, "Stored text.")
    assert db_utils.get_document_source(file_id)["source_text"] == "Stored text."


def test_search_sessions_matches_query_and_response(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    db_utils.insert_application_logs(
        "session-1", "How do I fix the plumbing?", "Call the plumber.", "gpt-4o-mini"
    )
    db_utils.insert_application_logs(
        "session-1", "What about electrical?", "Call the electrician.", "gpt-4o-mini"
    )
    db_utils.insert_application_logs(
        "session-2", "What are the pool hours?", "The pool is open 9 to 9.", "gpt-4o-mini"
    )
    db_utils.rename_session("session-1", "Maintenance Issues")

    results = db_utils.search_sessions("plumbing")
    assert len(results) == 1
    assert results[0]["session_id"] == "session-1"
    assert results[0]["label"] == "Maintenance Issues"
    assert results[0]["match_count"] == 1
    assert "How do I fix the plumbing?" in results[0]["matched_queries"]

    results = db_utils.search_sessions("electrician")
    assert len(results) == 1
    assert results[0]["session_id"] == "session-1"
    assert results[0]["match_count"] == 1

    assert db_utils.search_sessions("") == []
    assert db_utils.search_sessions("   ") == []
    assert db_utils.search_sessions("nonexistent term") == []


def test_normalize_session_status():
    assert db_utils.normalize_session_status(None) == "active"
    assert db_utils.normalize_session_status("") == "active"
    assert db_utils.normalize_session_status("  RESOLVED  ") == "resolved"
    assert db_utils.normalize_session_status("escalated") == "escalated"
    assert db_utils.normalize_session_status("closed") == "closed"

    try:
        db_utils.normalize_session_status("invalid-status")
        raise AssertionError("Should have raised ValueError")
    except ValueError as e:
        assert "Invalid session status" in str(e)


def test_normalize_session_tags():
    assert db_utils.normalize_session_tags(None) == ""
    assert db_utils.normalize_session_tags("") == ""
    assert db_utils.normalize_session_tags("  lease, maintenance , lease ") == "lease, maintenance"
    assert db_utils.normalize_session_tags(["urgent", "billing", "urgent"]) == "billing, urgent"

    try:
        db_utils.normalize_session_tags(", ".join(f"tag_{i}" for i in range(50)))
        raise AssertionError("Should have raised ValueError")
    except ValueError as e:
        assert "Session tags must be at most" in str(e)


def test_update_session_metadata_and_retrieval(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    # Missing session returns False / None
    assert db_utils.update_session_metadata("missing-session", label="Test") is False
    assert db_utils.get_session_metadata("missing-session") is None

    # Known session with logs
    db_utils.insert_application_logs("session-1", "Hi", "Hello", "gpt-4o-mini")

    # Initial metadata when not set
    meta = db_utils.get_session_metadata("session-1")
    assert meta == {
        "session_id": "session-1",
        "label": None,
        "status": "active",
        "tags": "",
        "summary": "",
        "resolution_notes": "",
        "priority": "medium",
    }

    # Update metadata incrementally
    assert (
        db_utils.update_session_metadata(
            "session-1", label="Tenant Chat", status="resolved", tags=["billing", "rent"]
        )
        is True
    )
    meta = db_utils.get_session_metadata("session-1")
    assert meta is not None
    assert meta["label"] == "Tenant Chat"
    assert meta["status"] == "resolved"
    assert meta["tags"] == "billing, rent"

    # Update only status
    assert db_utils.update_session_metadata("session-1", status="escalated") is True
    meta = db_utils.get_session_metadata("session-1")
    assert meta is not None
    assert meta["label"] == "Tenant Chat"  # preserved
    assert meta["status"] == "escalated"
    assert meta["tags"] == "billing, rent"  # preserved


def test_get_all_sessions_status_and_tag_filtering(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    db_utils.insert_application_logs("s1", "Q1", "A1", "gpt-4o-mini")
    db_utils.insert_application_logs("s2", "Q2", "A2", "gpt-4o-mini")
    db_utils.insert_application_logs("s3", "Q3", "A3", "gpt-4o-mini")

    db_utils.update_session_metadata("s1", label="S1", status="resolved", tags="lease,urgent")
    db_utils.update_session_metadata("s2", label="S2", status="active", tags="maintenance")
    db_utils.update_session_metadata("s3", label="S3", status="escalated", tags="urgent")

    # All sessions
    all_sessions = db_utils.get_all_sessions()
    expected_all_sessions = 3
    assert len(all_sessions) == expected_all_sessions
    s1 = next(s for s in all_sessions if s["session_id"] == "s1")
    assert s1["status"] == "resolved"
    assert s1["tags"] == "lease, urgent"

    # Filter by status
    resolved = db_utils.get_all_sessions(status="resolved")
    assert len(resolved) == 1
    assert resolved[0]["session_id"] == "s1"

    active = db_utils.get_all_sessions(status="active")
    assert len(active) == 1
    assert active[0]["session_id"] == "s2"

    # Filter by tag
    urgent = db_utils.get_all_sessions(tag="urgent")
    expected_urgent_count = 2
    assert len(urgent) == expected_urgent_count
    assert {s["session_id"] for s in urgent} == {"s1", "s3"}

    # Filter by both status and tag
    resolved_urgent = db_utils.get_all_sessions(status="resolved", tag="urgent")
    assert len(resolved_urgent) == 1
    assert resolved_urgent[0]["session_id"] == "s1"

    # Search sessions also includes status and tags
    search_res = db_utils.search_sessions("Q1")
    assert len(search_res) == 1
    assert search_res[0]["status"] == "resolved"
    assert search_res[0]["tags"] == "lease, urgent"


def test_migrate_session_labels_adds_columns(monkeypatch, tmp_path):
    db_path = tmp_path / "legacy.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(db_path))

    # Create legacy table without status and tags
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute(
            "CREATE TABLE session_labels (session_id TEXT PRIMARY KEY, label TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO session_labels (session_id, label) VALUES ('s1', 'Old Session')")
        conn.commit()

    # Run migration
    db_utils.migrate_session_labels()

    # Verify columns exist and legacy row has default status and tags
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM session_labels WHERE session_id = 's1'").fetchone()
        assert row["label"] == "Old Session"
        assert row["status"] == "active"
        assert row["tags"] == ""
        assert row["summary"] == ""
        assert row["resolution_notes"] == ""

    # Second migration call is idempotent
    db_utils.migrate_session_labels()


def test_get_feedback_analytics_empty_and_populated(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    # Empty table
    empty_analytics = db_utils.get_feedback_analytics()
    assert empty_analytics["total_feedback"] == 0
    assert empty_analytics["positive_feedback"] == 0
    assert empty_analytics["negative_feedback"] == 0
    assert empty_analytics["satisfaction_rate"] == 0.0
    assert empty_analytics["total_comments"] == 0
    assert empty_analytics["comment_rate"] == 0.0
    assert empty_analytics["recent_comments"] == []

    # Insert ratings with and without comments
    db_utils.insert_feedback("s1", rating=1, comment="Great answer!")
    db_utils.insert_feedback("s2", rating=1, comment=None)
    db_utils.insert_feedback("s3", rating=1, comment="Very helpful.")
    db_utils.insert_feedback("s4", rating=-1, comment="Incorrect response.")

    analytics = db_utils.get_feedback_analytics(recent_comments_limit=2)
    expected_total = 4
    expected_pos = 3
    expected_neg = 1
    expected_comments = 3
    expected_satisfaction = 75.0
    expected_comment_rate = 75.0
    expected_recent_count = 2

    assert analytics["total_feedback"] == expected_total
    assert analytics["positive_feedback"] == expected_pos
    assert analytics["negative_feedback"] == expected_neg
    assert analytics["satisfaction_rate"] == expected_satisfaction
    assert analytics["total_comments"] == expected_comments
    assert analytics["comment_rate"] == expected_comment_rate
    assert len(analytics["recent_comments"]) == expected_recent_count
    assert analytics["recent_comments"][0]["comment"] == "Incorrect response."


def test_get_collections_details_empty_and_populated(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    # Empty
    assert db_utils.get_collections_details() == []

    # Insert docs in different collections with various extensions
    db_utils.insert_document_record("lease.pdf", collection="legal")
    db_utils.insert_document_record("policy.docx", collection="legal")
    db_utils.insert_document_record("guide.txt", collection="help")
    db_utils.insert_document_record("README", collection="help")

    details = db_utils.get_collections_details()
    expected_collections_count = 2
    assert len(details) == expected_collections_count

    legal = next(c for c in details if c["collection"] == "legal")
    help_col = next(c for c in details if c["collection"] == "help")

    expected_legal_doc_count = 2
    expected_help_doc_count = 2
    assert legal["document_count"] == expected_legal_doc_count
    assert legal["file_formats"] == {"pdf": 1, "docx": 1}
    assert legal["earliest_upload"] is not None
    assert legal["latest_upload"] is not None

    assert help_col["document_count"] == expected_help_doc_count
    assert help_col["file_formats"] == {"txt": 1, "unknown": 1}


def test_normalize_session_summary_and_resolution_notes():
    assert db_utils.normalize_session_summary(None) == ""
    assert db_utils.normalize_session_summary("   ") == ""
    assert db_utils.normalize_session_summary(" Customer needs refund ") == "Customer needs refund"
    with pytest.raises(ValueError, match="Session summary must be at most"):
        db_utils.normalize_session_summary("a" * 2001)

    assert db_utils.normalize_resolution_notes(None) == ""
    assert db_utils.normalize_resolution_notes("   ") == ""
    assert db_utils.normalize_resolution_notes(" Issued refund via Stripe ") == (
        "Issued refund via Stripe"
    )
    with pytest.raises(ValueError, match="Resolution notes must be at most"):
        db_utils.normalize_resolution_notes("b" * 2001)


def test_session_metadata_summary_and_resolution_notes(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    # Unknown session returns False
    assert (
        db_utils.update_session_metadata(
            "unknown", summary="Summary text", resolution_notes="Notes text"
        )
        is False
    )

    # Session with logs
    db_utils.insert_application_logs("s1", "Issue query", "Issue solution", "gpt-4o")

    # Initial metadata without explicit labels
    meta = db_utils.get_session_metadata("s1")
    assert meta is not None
    assert meta["summary"] == ""
    assert meta["resolution_notes"] == ""
    assert meta["status"] == "active"

    # Update summary, notes, status, and tags
    ok = db_utils.update_session_metadata(
        "s1",
        label="Lease Invariant",
        status="resolved",
        tags=["lease", "refund"],
        summary="User asked about lease termination and refund.",
        resolution_notes="Approved early termination with no penalty.",
    )
    assert ok is True

    updated_meta = db_utils.get_session_metadata("s1")
    assert updated_meta is not None
    assert updated_meta["label"] == "Lease Invariant"
    assert updated_meta["status"] == "resolved"
    assert updated_meta["tags"] == "lease, refund"
    assert updated_meta["summary"] == "User asked about lease termination and refund."
    assert (
        updated_meta["resolution_notes"]
        == "Approved early termination with no penalty."
    )

    # Partial update preserves existing summary and notes
    db_utils.update_session_metadata("s1", status="closed")
    closed_meta = db_utils.get_session_metadata("s1")
    assert closed_meta is not None
    assert closed_meta["status"] == "closed"
    assert closed_meta["summary"] == "User asked about lease termination and refund."
    assert (
        closed_meta["resolution_notes"]
        == "Approved early termination with no penalty."
    )

    # Sessions listing reflects summary and resolution_notes
    all_sessions = db_utils.get_all_sessions()
    assert len(all_sessions) == 1
    assert all_sessions[0]["summary"] == "User asked about lease termination and refund."
    assert (
        all_sessions[0]["resolution_notes"]
        == "Approved early termination with no penalty."
    )


def test_get_support_triage_analytics(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    # Empty DB
    empty_res = db_utils.get_support_triage_analytics()
    assert empty_res["total_sessions"] == 0
    assert empty_res["active_count"] == 0
    assert empty_res["resolved_count"] == 0
    assert empty_res["escalated_count"] == 0
    assert empty_res["closed_count"] == 0
    assert empty_res["resolution_rate"] == 0.0
    assert empty_res["escalation_rate"] == 0.0
    assert empty_res["avg_turns_per_session"] == 0.0
    assert empty_res["top_tags"] == []

    # Insert 4 sessions:
    # s1: 2 turns (4 messages total in application_logs), resolved, tags: lease, urgent
    # s2: 1 turn, escalated, tags: urgent, billing
    # s3: 1 turn, closed, tags: lease
    # s4: 1 turn, active (default), no tags
    db_utils.insert_application_logs("s1", "Q1", "A1", "gpt-4o")
    db_utils.insert_application_logs("s1", "Q2", "A2", "gpt-4o")
    db_utils.insert_application_logs("s2", "Q3", "A3", "gpt-4o")
    db_utils.insert_application_logs("s3", "Q4", "A4", "gpt-4o")
    db_utils.insert_application_logs("s4", "Q5", "A5", "gpt-4o")

    db_utils.update_session_metadata("s1", status="resolved", tags="lease, urgent")
    db_utils.update_session_metadata("s2", status="escalated", tags="urgent, billing")
    db_utils.update_session_metadata("s3", status="closed", tags="lease")

    analytics = db_utils.get_support_triage_analytics()
    expected_total_sessions = 4
    expected_active_count = 1
    expected_resolved_count = 1
    expected_escalated_count = 1
    expected_closed_count = 1
    expected_resolution_rate = 50.0
    expected_escalation_rate = 25.0
    expected_avg_turns = 1.25
    expected_lease_tag_count = 2
    expected_urgent_tag_count = 2
    expected_billing_tag_count = 1

    assert analytics["total_sessions"] == expected_total_sessions
    assert analytics["active_count"] == expected_active_count
    assert analytics["resolved_count"] == expected_resolved_count
    assert analytics["escalated_count"] == expected_escalated_count
    assert analytics["closed_count"] == expected_closed_count
    assert analytics["resolution_rate"] == expected_resolution_rate
    assert analytics["escalation_rate"] == expected_escalation_rate
    assert analytics["avg_turns_per_session"] == expected_avg_turns

    tag_counts = {item["tag"]: item["count"] for item in analytics["top_tags"]}
    assert tag_counts["lease"] == expected_lease_tag_count
    assert tag_counts["urgent"] == expected_urgent_tag_count
    assert tag_counts["billing"] == expected_billing_tag_count


def test_normalize_webhook_url():
    assert (
        db_utils.normalize_webhook_url("  https://example.com/webhook  ")
        == "https://example.com/webhook"
    )
    assert (
        db_utils.normalize_webhook_url("http://localhost:8000/hook")
        == "http://localhost:8000/hook"
    )

    with pytest.raises(ValueError, match="Webhook URL must not be blank"):
        db_utils.normalize_webhook_url("")

    with pytest.raises(ValueError, match="Webhook URL must not be blank"):
        db_utils.normalize_webhook_url("   ")

    with pytest.raises(ValueError, match="Webhook URL must not be blank"):
        db_utils.normalize_webhook_url(None)

    with pytest.raises(ValueError, match="must start with 'http://' or 'https://'"):
        db_utils.normalize_webhook_url("ftp://example.com/hook")

    with pytest.raises(ValueError, match="must start with 'http://' or 'https://'"):
        db_utils.normalize_webhook_url("example.com/hook")

    with pytest.raises(ValueError, match="must be at most"):
        db_utils.normalize_webhook_url("https://example.com/" + "a" * 501)


def test_normalize_webhook_events():
    assert db_utils.normalize_webhook_events(None) == "*"
    assert db_utils.normalize_webhook_events("") == "*"
    assert db_utils.normalize_webhook_events([]) == "*"
    assert db_utils.normalize_webhook_events(["*"]) == "*"
    assert db_utils.normalize_webhook_events("session.escalated, *") == "*"
    assert (
        db_utils.normalize_webhook_events("session.resolved, session.escalated")
        == "session.escalated, session.resolved"
    )
    assert (
        db_utils.normalize_webhook_events(["session.resolved", "feedback.negative"])
        == "feedback.negative, session.resolved"
    )

    with pytest.raises(ValueError, match="Invalid webhook event 'unknown.event'"):
        db_utils.normalize_webhook_events("session.escalated, unknown.event")


def test_normalize_webhook_secret():
    assert db_utils.normalize_webhook_secret(None) == ""
    assert db_utils.normalize_webhook_secret("") == ""
    assert db_utils.normalize_webhook_secret("  my-secret-key  ") == "my-secret-key"

    with pytest.raises(ValueError, match="must be at most"):
        db_utils.normalize_webhook_secret("s" * 257)


def test_create_and_get_webhook(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    hook = db_utils.create_webhook(
        url="https://hooks.slack.com/services/123",
        events="session.escalated, feedback.negative",
        secret="whsec_123",
        is_active=True,
    )

    assert hook["id"] == 1
    assert hook["url"] == "https://hooks.slack.com/services/123"
    assert hook["events"] == "feedback.negative, session.escalated"
    assert hook["secret"] == "whsec_123"
    assert hook["is_active"] is True
    assert hook["failure_count"] == 0
    assert hook["created_at"] is not None

    fetched = db_utils.get_webhook(1)
    assert fetched == hook

    assert db_utils.get_webhook(999) is None


def test_list_webhooks_filtering(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    db_utils.create_webhook(
        url="https://example.com/all",
        events="*",
        is_active=True,
    )
    db_utils.create_webhook(
        url="https://example.com/escalated",
        events="session.escalated",
        is_active=True,
    )
    db_utils.create_webhook(
        url="https://example.com/inactive",
        events="feedback.negative",
        is_active=False,
    )

    all_hooks = db_utils.list_webhooks()
    expected_all_count = 3
    assert len(all_hooks) == expected_all_count

    active_hooks = db_utils.list_webhooks(active_only=True)
    expected_active_count = 2
    assert len(active_hooks) == expected_active_count
    assert [h["id"] for h in active_hooks] == [1, 2]

    escalated_hooks = db_utils.list_webhooks(event="session.escalated")
    expected_escalated_count = 2
    assert len(escalated_hooks) == expected_escalated_count
    assert [h["id"] for h in escalated_hooks] == [1, 2]

    feedback_hooks = db_utils.list_webhooks(active_only=True, event="feedback.negative")
    assert len(feedback_hooks) == 1
    assert feedback_hooks[0]["id"] == 1


def test_update_webhook(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    hook = db_utils.create_webhook(
        url="https://example.com/hook1",
        events="session.escalated",
        secret="secret1",
        is_active=True,
    )

    db_utils.record_webhook_delivery(
        webhook_id=hook["id"],
        event="session.escalated",
        url=hook["url"],
        status_code=500,
        success=False,
        error_message="Internal Server Error",
    )
    hook_after_fail = db_utils.get_webhook(hook["id"])
    assert hook_after_fail is not None
    assert hook_after_fail["failure_count"] == 1

    updated = db_utils.update_webhook(
        webhook_id=hook["id"],
        url="https://example.com/hook1-updated",
        events="session.resolved",
        secret="newsecret",
        is_active=False,
        reset_failures=True,
    )

    assert updated is not None
    assert updated["url"] == "https://example.com/hook1-updated"
    assert updated["events"] == "session.resolved"
    assert updated["secret"] == "newsecret"
    assert updated["is_active"] is False
    assert updated["failure_count"] == 0

    assert db_utils.update_webhook(999, url="https://example.com/nonexistent") is None


def test_delete_webhook_and_cascade_logs(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    hook = db_utils.create_webhook(url="https://example.com/delete-me")
    db_utils.record_webhook_delivery(
        webhook_id=hook["id"],
        event="ping",
        url=hook["url"],
        status_code=200,
        success=True,
    )

    logs_before, total_before = db_utils.get_webhook_delivery_logs(webhook_id=hook["id"])
    assert total_before == 1
    assert len(logs_before) == 1

    deleted = db_utils.delete_webhook(hook["id"])
    assert deleted is True

    assert db_utils.get_webhook(hook["id"]) is None
    logs_after, total_after = db_utils.get_webhook_delivery_logs(webhook_id=hook["id"])
    assert total_after == 0
    assert len(logs_after) == 0

    assert db_utils.delete_webhook(999) is False


def test_record_and_get_webhook_delivery_logs(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    h1 = db_utils.create_webhook(url="https://example.com/h1")
    h2 = db_utils.create_webhook(url="https://example.com/h2")

    log_id1 = db_utils.record_webhook_delivery(
        webhook_id=h1["id"],
        event="session.escalated",
        url=h1["url"],
        status_code=200,
        success=True,
        payload_preview='{"session_id": "s1"}',
    )
    log_id2 = db_utils.record_webhook_delivery(
        webhook_id=h1["id"],
        event="feedback.negative",
        url=h1["url"],
        status_code=502,
        success=False,
        payload_preview='{"session_id": "s2"}',
        error_message="Bad Gateway",
    )
    log_id3 = db_utils.record_webhook_delivery(
        webhook_id=h2["id"],
        event="session.resolved",
        url=h2["url"],
        status_code=200,
        success=True,
        payload_preview='{"session_id": "s3"}',
    )

    assert log_id1 > 0
    assert log_id2 > 0
    assert log_id3 > 0

    h1_hook = db_utils.get_webhook(h1["id"])
    h2_hook = db_utils.get_webhook(h2["id"])
    assert h1_hook is not None and h1_hook["failure_count"] == 1
    assert h2_hook is not None and h2_hook["failure_count"] == 0

    # Successful delivery resets failure count
    db_utils.record_webhook_delivery(
        webhook_id=h1["id"],
        event="ping",
        url=h1["url"],
        status_code=200,
        success=True,
    )
    h1_hook_reset = db_utils.get_webhook(h1["id"])
    assert h1_hook_reset is not None and h1_hook_reset["failure_count"] == 0

    # Get logs pagination and filter
    all_logs, total_count = db_utils.get_webhook_delivery_logs(limit=2, offset=0)
    expected_logs_total = 4
    expected_page_count = 2
    assert total_count == expected_logs_total
    assert len(all_logs) == expected_page_count

    h2_logs, h2_total = db_utils.get_webhook_delivery_logs(webhook_id=h2["id"])
    assert h2_total == 1
    assert len(h2_logs) == 1
    assert h2_logs[0]["event"] == "session.resolved"
    assert h2_logs[0]["success"] is True


def test_support_macros_seeded_on_init(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    macros = db_utils.list_macros()
    assert len(macros) == len(db_utils.DEFAULT_MACROS)
    shortcuts = [m["shortcut"] for m in macros]
    assert "/lease-renewal" in shortcuts
    assert "/emerg-maint" in shortcuts
    assert "/rent-pay" in shortcuts
    assert "/move-out" in shortcuts

    # Re-seeding does not duplicate
    added = db_utils.seed_default_macros()
    assert added == 0
    assert len(db_utils.list_macros()) == len(db_utils.DEFAULT_MACROS)


def test_create_and_get_macro(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    macro = db_utils.create_macro(
        title="Parking Pass Request",
        shortcut="/parking-pass",
        content="Hello {customer_name}, your parking pass for unit {unit_id} is ready.",
        category="Parking",
        tags=["parking", "amenities"],
        status_action="resolved",
    )

    assert macro["id"] > 0
    assert macro["title"] == "Parking Pass Request"
    assert macro["shortcut"] == "/parking-pass"
    assert macro["category"] == "Parking"
    assert "parking" in macro["tags"]
    assert macro["status_action"] == "resolved"

    by_id = db_utils.get_macro(macro["id"])
    assert by_id == macro

    by_shortcut = db_utils.get_macro_by_shortcut("/parking-pass")
    assert by_shortcut == macro

    # Case-insensitive shortcut lookup
    by_shortcut_upper = db_utils.get_macro_by_shortcut("PARKING-PASS")
    assert by_shortcut_upper == macro


def test_create_macro_validations(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    # Duplicate shortcut raises ValueError
    with pytest.raises(ValueError, match="already exists"):
        db_utils.create_macro(
            title="Duplicate",
            shortcut="/lease-renewal",
            content="Some text",
        )

    # Blank title
    with pytest.raises(ValueError, match="Macro title must not be blank"):
        db_utils.create_macro(title="", shortcut="/valid", content="Some text")

    # Blank shortcut
    with pytest.raises(ValueError, match="Macro shortcut must not be blank"):
        db_utils.create_macro(title="Valid", shortcut="", content="Some text")

    # Invalid shortcut characters
    with pytest.raises(ValueError, match="alphanumeric"):
        db_utils.create_macro(title="Valid", shortcut="/bad shortcut!", content="Some text")

    # Blank content
    with pytest.raises(ValueError, match="Macro content must not be blank"):
        db_utils.create_macro(title="Valid", shortcut="/valid-shortcut", content="")

    # Invalid status action
    with pytest.raises(ValueError, match="Invalid status_action"):
        db_utils.create_macro(
            title="Valid",
            shortcut="/valid-shortcut",
            content="Text",
            status_action="invalid_status",
        )


def test_list_macros_and_filters(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    # Filter by category
    min_leasing_count = 2
    leasing_macros = db_utils.list_macros(category="Leasing")
    assert all(m["category"] == "Leasing" for m in leasing_macros)
    assert len(leasing_macros) >= min_leasing_count

    # Filter by tag
    urgent_macros = db_utils.list_macros(tag="urgent")
    assert any(m["shortcut"] == "/emerg-maint" for m in urgent_macros)

    # Search filter across title, shortcut, or content
    search_results = db_utils.list_macros(search="portal")
    assert any(m["shortcut"] == "/rent-pay" for m in search_results)


def test_list_macro_categories(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    categories = db_utils.list_macro_categories()
    assert "Billing" in categories
    assert "General" in categories
    assert "Leasing" in categories
    assert "Maintenance" in categories


def test_update_macro(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    macro = db_utils.create_macro(
        title="Original Title",
        shortcut="/orig-sc",
        content="Original content",
        category="General",
        tags="orig, test",
        status_action="active",
    )

    updated = db_utils.update_macro(
        macro["id"],
        title="Updated Title",
        shortcut="/new-sc",
        category="UpdatedCat",
        content="New content",
        tags=["newtag1", "newtag2"],
        status_action="resolved",
    )

    assert updated is not None
    assert updated["title"] == "Updated Title"
    assert updated["shortcut"] == "/new-sc"
    assert updated["category"] == "UpdatedCat"
    assert updated["content"] == "New content"
    assert updated["tags"] == ["newtag1", "newtag2"]
    assert updated["status_action"] == "resolved"

    # Shortcut collision raises ValueError
    with pytest.raises(ValueError, match="already taken"):
        db_utils.update_macro(macro["id"], shortcut="/lease-renewal")

    # Nonexistent macro returns None
    assert db_utils.update_macro(99999, title="Nonexistent") is None


def test_delete_macro(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    macro = db_utils.create_macro(
        title="To Delete",
        shortcut="/to-delete",
        content="Will be deleted",
    )

    assert db_utils.delete_macro(macro["id"]) is True
    assert db_utils.get_macro(macro["id"]) is None
    assert db_utils.delete_macro(macro["id"]) is False


def test_get_session_latest_user_query(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    assert db_utils.get_session_latest_user_query(None) is None
    assert db_utils.get_session_latest_user_query("") is None
    assert db_utils.get_session_latest_user_query("   ") is None
    assert db_utils.get_session_latest_user_query("nonexistent-session") is None

    session_id = "sess-multi-turn"
    db_utils.insert_application_logs(session_id, "First query: hello", "Hi there", "gpt-4o")
    assert db_utils.get_session_latest_user_query(session_id) == "First query: hello"

    second_query = "Second query: I need a leak repaired"
    db_utils.insert_application_logs(
        session_id, second_query, "Dispatching tech", "gpt-4o"
    )
    assert db_utils.get_session_latest_user_query(session_id) == second_query


def test_normalize_session_priority():
    assert db_utils.normalize_session_priority(None) == "medium"
    assert db_utils.normalize_session_priority("") == "medium"
    assert db_utils.normalize_session_priority("  ") == "medium"
    assert db_utils.normalize_session_priority("Urgent") == "urgent"
    assert db_utils.normalize_session_priority("HIGH") == "high"
    assert db_utils.normalize_session_priority("Medium") == "medium"
    assert db_utils.normalize_session_priority("low") == "low"

    with pytest.raises(ValueError, match="Invalid session priority"):
        db_utils.normalize_session_priority("critical")


def test_migrate_session_labels_adds_priority_column(monkeypatch, tmp_path):
    db_path = tmp_path / "test_migrate.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(db_path))

    # Create table without priority column
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute(
            "CREATE TABLE session_labels (session_id TEXT PRIMARY KEY, label TEXT NOT NULL)"
        )
        conn.commit()

    db_utils.migrate_session_labels()

    with closing(sqlite3.connect(str(db_path))) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(session_labels)").fetchall()]
        assert "priority" in cols


def test_update_and_get_session_metadata_with_priority(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    session_id = "sess-prio-test"
    db_utils.insert_application_logs(session_id, "Need emergency fix", "On it", "gpt-4o")

    # Default metadata has medium priority
    meta = db_utils.get_session_metadata(session_id)
    assert meta is not None
    assert meta["priority"] == "medium"

    # Update to urgent priority
    updated = db_utils.update_session_metadata(session_id, priority="urgent")
    assert updated is True
    meta = db_utils.get_session_metadata(session_id)
    assert meta is not None
    assert meta["priority"] == "urgent"

    # Appears in all sessions
    all_sessions = db_utils.get_all_sessions()
    target = next((s for s in all_sessions if s["session_id"] == session_id), None)
    assert target is not None
    assert target["priority"] == "urgent"

    # Invalid priority raises ValueError
    with pytest.raises(ValueError, match="Invalid session priority"):
        db_utils.update_session_metadata(session_id, priority="extreme")


def test_create_sla_policies_seeds_defaults(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    policies = db_utils.list_sla_policies()
    assert len(policies) == len(db_utils.DEFAULT_SLA_POLICIES)

    urgent_maint = next(
        (p for p in policies if p["priority"] == "urgent" and p["category"] == "maintenance"),
        None,
    )
    assert urgent_maint is not None
    expected_resp = 15
    expected_resol = 120
    assert urgent_maint["response_time_minutes"] == expected_resp
    assert urgent_maint["resolution_time_minutes"] == expected_resol
    assert urgent_maint["is_active"] == 1


def test_create_and_get_sla_policy(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    resp_time = 45
    resol_time = 360
    policy_id = db_utils.create_sla_policy(
        name="Custom Billing SLA",
        priority="high",
        category="billing",
        response_time_minutes=resp_time,
        resolution_time_minutes=resol_time,
    )
    assert policy_id > 0

    policy = db_utils.get_sla_policy(policy_id)
    assert policy is not None
    assert policy["name"] == "Custom Billing SLA"
    assert policy["priority"] == "high"
    assert policy["category"] == "billing"
    assert policy["response_time_minutes"] == resp_time
    assert policy["resolution_time_minutes"] == resol_time

    # Validation errors
    with pytest.raises(ValueError, match="name must not be blank"):
        db_utils.create_sla_policy("", "high")

    with pytest.raises(ValueError, match="greater than zero"):
        db_utils.create_sla_policy("Test", "high", response_time_minutes=0)

    with pytest.raises(ValueError, match="greater than or equal to response_time_minutes"):
        db_utils.create_sla_policy(
            "Test", "high", response_time_minutes=60, resolution_time_minutes=30
        )


def test_get_matching_sla_policy_with_fallbacks(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    # Exact match: urgent / maintenance
    match1 = db_utils.get_matching_sla_policy("urgent", "maintenance")
    assert match1 is not None
    assert match1["priority"] == "urgent"
    assert match1["category"] == "maintenance"
    expected_resp_1 = 15
    assert match1["response_time_minutes"] == expected_resp_1

    # Fallback to general: urgent / unknown_cat -> urgent / general
    match2 = db_utils.get_matching_sla_policy("urgent", "unknown_category")
    assert match2 is not None
    assert match2["priority"] == "urgent"
    assert match2["category"] == "general"
    expected_resp_2 = 30
    assert match2["response_time_minutes"] == expected_resp_2

    # Fallback to medium / general
    match3 = db_utils.get_matching_sla_policy("medium", "random")
    assert match3 is not None
    assert match3["priority"] == "medium"
    assert match3["category"] == "general"


def test_list_and_update_and_delete_sla_policy(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    p_id = db_utils.create_sla_policy(
        name="Escrow Review SLA",
        priority="low",
        category="escrow",
        response_time_minutes=720,
        resolution_time_minutes=1440,
    )

    filtered = db_utils.list_sla_policies(category="escrow")
    assert len(filtered) == 1
    assert filtered[0]["id"] == p_id

    # Update
    updated_resp = 600
    updated_resol = 1200
    updated = db_utils.update_sla_policy(
        p_id,
        name="Escrow Rapid Review",
        response_time_minutes=updated_resp,
        resolution_time_minutes=updated_resol,
        is_active=0,
    )
    assert updated is True

    pol = db_utils.get_sla_policy(p_id)
    assert pol is not None
    assert pol["name"] == "Escrow Rapid Review"
    assert pol["response_time_minutes"] == updated_resp
    assert pol["is_active"] == 0

    # Active only filter excludes it
    assert len(db_utils.list_sla_policies(category="escrow", active_only=True)) == 0

    # Non-existent update
    assert db_utils.update_sla_policy(99999, name="Nope") is False

    # Delete
    assert db_utils.delete_sla_policy(p_id) is True
    assert db_utils.get_sla_policy(p_id) is None
    assert db_utils.delete_sla_policy(p_id) is False


def test_get_session_timestamps(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    # Empty session
    empty_ts = db_utils.get_session_timestamps("empty-session")
    assert empty_ts["session_start"] is None
    assert empty_ts["first_response_at"] is None
    assert empty_ts["total_turns"] == 0

    # Multi-turn session
    s_id = "sess-ts-1"
    db_utils.insert_application_logs(s_id, "Q1", "A1", "gpt-4o")
    db_utils.insert_application_logs(s_id, "Q2", "A2", "gpt-4o")

    ts = db_utils.get_session_timestamps(s_id)
    assert ts["session_start"] is not None
    assert ts["first_response_at"] is not None
    assert ts["last_activity"] is not None
    expected_turns = 2
    assert ts["total_turns"] == expected_turns
