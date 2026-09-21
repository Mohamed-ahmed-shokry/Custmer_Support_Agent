import sqlite3
from contextlib import closing

from api import db_utils


def initialize_temp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "nested" / "test.db"
    monkeypatch.setattr(db_utils, "DB_NAME", str(db_path))
    db_utils.create_application_logs()
    db_utils.create_document_store()
    db_utils.create_session_labels()
    db_utils.migrate_session_labels()
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
    assert meta == {"session_id": "session-1", "label": None, "status": "active", "tags": ""}

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
