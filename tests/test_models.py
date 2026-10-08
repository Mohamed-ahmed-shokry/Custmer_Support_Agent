from datetime import datetime

import pytest
from api.pydantic_models import (
    DEFAULT_MODEL,
    ChunkingStrategy,
    CollectionAnalyticsResponse,
    CollectionRechunkRequest,
    CollectionRechunkResponse,
    DocumentDetailResponse,
    DocumentRechunkItem,
    MacroApplyRequest,
    MacroApplyResponse,
    MacroCategoriesResponse,
    MacroCreateRequest,
    MacroRenderRequest,
    MacroRenderResponse,
    MacroResponse,
    MacroSuggestionItem,
    MacroSuggestRequest,
    MacroSuggestResponse,
    MacroUpdateRequest,
    ModelName,
    QueryInput,
    QueryResponse,
    RechunkDocumentRequest,
    SessionInfo,
    SessionMacroSuggestionsResponse,
    SessionSLAStatusResponse,
    SessionSummaryRequest,
    SessionSummaryResponse,
    SLAAlertEvaluateResponse,
    SLAAlertItem,
    SLAComplianceAnalyticsResponse,
    SLAPoliciesListResponse,
    SLAPolicyCreateRequest,
    SLAPolicyResponse,
    SLAPolicyUpdateRequest,
    SourceInfo,
    SupportTriageAnalyticsResponse,
    TagCount,
    UpdateSessionRequest,
    WebhookCreateRequest,
    WebhookDeliveryLogItem,
    WebhookDeliveryLogsResponse,
    WebhookPingResponse,
    WebhookResponse,
    WebhookUpdateRequest,
    model_from_value,
)
from pydantic import ValidationError


def test_query_input_rejects_empty_question():
    with pytest.raises(ValidationError):
        QueryInput(question="")


def test_query_input_rejects_whitespace_question():
    with pytest.raises(ValidationError):
        QueryInput(question="   ")


def test_model_from_value_accepts_supported_model():
    assert model_from_value("gpt-4o") == ModelName.GPT4_O


def test_model_from_value_falls_back_for_unknown_model():
    assert model_from_value("unknown") == DEFAULT_MODEL


def test_query_input_uses_configured_default_model(monkeypatch):
    monkeypatch.setattr("api.pydantic_models.settings.default_model", "gpt-4o")

    assert QueryInput(question="How do I request maintenance?").model == ModelName.GPT4_O


def test_query_input_normalizes_collections():
    query = QueryInput(question="Hi?", collections=["Clients-Acme", "  DEFAULT  "])

    assert query.collections == ["clients-acme", "default"]


def test_query_input_rejects_invalid_collection():
    with pytest.raises(ValidationError):
        QueryInput(question="Hi?", collections=["bad name!"])


def test_query_response_accepts_sources():
    response = QueryResponse(
        answer="Answer",
        session_id="session-1",
        model=ModelName.GPT4_O_MINI,
        sources=[SourceInfo(filename="guide.pdf", preview="Relevant text")],
    )

    assert response.sources[0].filename == "guide.pdf"
    assert response.sources[0].preview == "Relevant text"


def test_rechunk_document_request_defaults():
    req = RechunkDocumentRequest()
    expected_chunk_size = 1000
    expected_chunk_overlap = 200
    assert req.chunking_strategy == ChunkingStrategy.RECURSIVE
    assert req.chunk_size == expected_chunk_size
    assert req.chunk_overlap == expected_chunk_overlap


def test_rechunk_document_request_custom():
    expected_size = 640
    expected_overlap = 80
    req = RechunkDocumentRequest(
        chunking_strategy=ChunkingStrategy.SEMANTIC,
        chunk_size=expected_size,
        chunk_overlap=expected_overlap,
    )
    assert req.chunking_strategy == ChunkingStrategy.SEMANTIC
    assert req.chunk_size == expected_size
    assert req.chunk_overlap == expected_overlap


def test_rechunk_document_request_validation():
    with pytest.raises(ValidationError):
        RechunkDocumentRequest(chunk_size=50)  # below 100

    with pytest.raises(ValidationError):
        RechunkDocumentRequest(chunk_size=5000)  # above 4000

    with pytest.raises(ValidationError):
        RechunkDocumentRequest(chunk_overlap=-1)  # negative overlap

    with pytest.raises(ValidationError):
        RechunkDocumentRequest(chunk_size=500, chunk_overlap=500)  # overlap >= size


def test_document_detail_response_chunking_fields():
    expected_size = 800
    expected_overlap = 150
    resp = DocumentDetailResponse(
        id=1,
        filename="test.pdf",
        chunk_count=3,
        chunking_strategy="semantic",
        chunk_size=expected_size,
        chunk_overlap=expected_overlap,
    )
    assert resp.chunking_strategy == "semantic"
    assert resp.chunk_size == expected_size
    assert resp.chunk_overlap == expected_overlap

    resp_default = DocumentDetailResponse(id=2, filename="test2.pdf", chunk_count=0)
    assert resp_default.chunking_strategy is None
    assert resp_default.chunk_size is None
    assert resp_default.chunk_overlap is None


def test_collection_rechunk_request_defaults_and_custom():
    default_req = CollectionRechunkRequest()
    expected_default_size = 1000
    expected_default_overlap = 200
    assert default_req.chunking_strategy == ChunkingStrategy.RECURSIVE
    assert default_req.chunk_size == expected_default_size
    assert default_req.chunk_overlap == expected_default_overlap

    expected_custom_size = 600
    expected_custom_overlap = 80
    custom_req = CollectionRechunkRequest(
        chunking_strategy=ChunkingStrategy.SEMANTIC,
        chunk_size=expected_custom_size,
        chunk_overlap=expected_custom_overlap,
    )
    assert custom_req.chunking_strategy == ChunkingStrategy.SEMANTIC
    assert custom_req.chunk_size == expected_custom_size
    assert custom_req.chunk_overlap == expected_custom_overlap


def test_collection_rechunk_request_validation():
    with pytest.raises(ValidationError):
        CollectionRechunkRequest(chunk_size=50)

    with pytest.raises(ValidationError):
        CollectionRechunkRequest(chunk_size=5000)

    with pytest.raises(ValidationError):
        CollectionRechunkRequest(chunk_overlap=-1)

    with pytest.raises(ValidationError):
        CollectionRechunkRequest(chunk_size=400, chunk_overlap=400)


def test_collection_rechunk_response():
    expected_docs = 5
    expected_rechunked = 4
    expected_skipped = 1
    expected_failed = 0
    expected_chunks = 28
    item1 = DocumentRechunkItem(
        file_id=1,
        filename="doc1.txt",
        status="rechunked",
        chunk_count=10,
    )
    item2 = DocumentRechunkItem(
        file_id=2,
        filename="doc2.txt",
        status="skipped",
        chunk_count=0,
        error_message="No stored source text",
    )
    resp = CollectionRechunkResponse(
        message="Re-chunked collection legal",
        collection="legal",
        strategy="semantic",
        chunk_size=500,
        chunk_overlap=50,
        total_documents=expected_docs,
        rechunked_documents=expected_rechunked,
        skipped_documents=expected_skipped,
        failed_documents=expected_failed,
        total_chunks_created=expected_chunks,
        items=[item1, item2],
    )
    assert resp.collection == "legal"
    expected_items_count = 2
    assert resp.total_documents == expected_docs
    assert resp.rechunked_documents == expected_rechunked
    assert len(resp.items) == expected_items_count
    assert resp.items[0].status == "rechunked"
    assert resp.items[1].error_message == "No stored source text"


def test_collection_analytics_response():
    expected_docs = 3
    expected_chunks = 15
    expected_avg = 450.5
    expected_min = 120
    expected_max = 980
    expected_median = 430.0
    expected_semantic_count = 5
    resp = CollectionAnalyticsResponse(
        collection="kb",
        total_documents=expected_docs,
        total_chunks=expected_chunks,
        avg_chunk_length=expected_avg,
        min_chunk_length=expected_min,
        max_chunk_length=expected_max,
        median_chunk_length=expected_median,
        strategy_distribution={"recursive": 10, "semantic": expected_semantic_count},
        length_histogram={"<200": 1, "200-500": 8, "500-1000": 6},
    )
    assert resp.collection == "kb"
    assert resp.total_documents == expected_docs
    assert resp.total_chunks == expected_chunks
    assert resp.avg_chunk_length == expected_avg
    assert resp.strategy_distribution["semantic"] == expected_semantic_count


def test_session_info_summary_and_resolution_notes():
    now = datetime.now()
    default_info = SessionInfo(session_id="s1", message_count=2, last_active=now)
    assert default_info.summary is None
    assert default_info.resolution_notes is None
    assert default_info.status == "active"

    custom_info = SessionInfo(
        session_id="s2",
        message_count=4,
        last_active=now,
        status="resolved",
        summary="Customer resolved fee discrepancy.",
        resolution_notes="Refund processed successfully.",
    )
    assert custom_info.summary == "Customer resolved fee discrepancy."
    assert custom_info.resolution_notes == "Refund processed successfully."


def test_update_session_request_summary_and_notes():
    # At least one field required
    with pytest.raises(ValidationError):
        UpdateSessionRequest()

    # Valid with only summary
    req1 = UpdateSessionRequest(summary="  New summary  ")
    assert req1.summary == "New summary"

    # Valid with only resolution_notes
    req2 = UpdateSessionRequest(resolution_notes="  New notes  ")
    assert req2.resolution_notes == "New notes"

    # Reject overly long summary or notes
    with pytest.raises(ValidationError):
        UpdateSessionRequest(summary="x" * 2001)

    with pytest.raises(ValidationError):
        UpdateSessionRequest(resolution_notes="y" * 2001)


def test_session_summary_request_and_response():
    req_def = SessionSummaryRequest()
    assert req_def.model is None
    assert req_def.save_summary is True

    req_custom = SessionSummaryRequest(model="gpt-4o", save_summary=False)
    assert req_custom.model == "gpt-4o"
    assert req_custom.save_summary is False

    resp = SessionSummaryResponse(
        session_id="s1",
        summary="User asked about lease.",
        key_points=["Customer inquiry: lease terms"],
        sentiment="positive",
        suggested_tags=["lease"],
        saved=True,
    )
    assert resp.session_id == "s1"
    assert resp.sentiment == "positive"
    assert resp.saved is True


def test_support_triage_analytics_response():

    expected_total = 10
    expected_active = 4
    expected_resolved = 4
    expected_escalated = 1
    expected_closed = 1
    expected_res_rate = 50.0
    expected_esc_rate = 10.0
    expected_turns = 2.5
    expected_tag_count = 5

    resp = SupportTriageAnalyticsResponse(
        total_sessions=expected_total,
        active_count=expected_active,
        resolved_count=expected_resolved,
        escalated_count=expected_escalated,
        closed_count=expected_closed,
        resolution_rate=expected_res_rate,
        escalation_rate=expected_esc_rate,
        avg_turns_per_session=expected_turns,
        top_tags=[TagCount(tag="lease", count=expected_tag_count)],
    )
    assert resp.total_sessions == expected_total
    assert resp.resolution_rate == expected_res_rate
    assert resp.top_tags[0].tag == "lease"
    assert resp.top_tags[0].count == expected_tag_count


def test_webhook_create_request_validation():
    req = WebhookCreateRequest(url="https://example.com/alerts")
    assert req.url == "https://example.com/alerts"
    assert req.events == "*"
    assert req.secret == ""
    assert req.is_active is True

    custom_req = WebhookCreateRequest(
        url="http://localhost:9000/webhook",
        events=["session.resolved", "session.escalated"],
        secret="  secret-key  ",
        is_active=False,
    )
    assert custom_req.events == "session.escalated, session.resolved"
    assert custom_req.secret == "secret-key"
    assert custom_req.is_active is False

    with pytest.raises(ValidationError):
        WebhookCreateRequest(url="not-a-valid-url")

    with pytest.raises(ValidationError):
        WebhookCreateRequest(url="https://example.com", events="unknown.event")


def test_webhook_update_request_validation():
    req = WebhookUpdateRequest(
        url="https://example.com/new-url",
        events="session.escalated",
        secret="new-secret",
        is_active=True,
        reset_failures=True,
    )
    assert req.url == "https://example.com/new-url"
    assert req.events == "session.escalated"
    assert req.secret == "new-secret"
    assert req.is_active is True
    assert req.reset_failures is True

    empty_update = WebhookUpdateRequest()
    assert empty_update.url is None
    assert empty_update.events is None
    assert empty_update.secret is None
    assert empty_update.is_active is None
    assert empty_update.reset_failures is False

    with pytest.raises(ValidationError):
        WebhookUpdateRequest(url="ftp://example.com/hook")


def test_webhook_response_models():
    hook_id = 42
    resp = WebhookResponse(
        id=hook_id,
        url="https://example.com/hook",
        events="session.escalated",
        secret="whsec_123",
        is_active=True,
        failure_count=0,
        created_at="2026-10-01T00:00:00Z",
    )
    assert resp.id == hook_id
    assert resp.url == "https://example.com/hook"
    assert resp.is_active is True

    log_id = 101
    log_item = WebhookDeliveryLogItem(
        id=log_id,
        webhook_id=hook_id,
        event="session.escalated",
        url="https://example.com/hook",
        status_code=200,
        success=True,
        payload_preview='{"session_id": "s1"}',
        delivered_at="2026-10-01T00:00:05Z",
    )
    assert log_item.id == log_id
    assert log_item.success is True

    logs_resp = WebhookDeliveryLogsResponse(items=[log_item], total=1)
    assert logs_resp.total == 1
    assert len(logs_resp.items) == 1

    ping_resp = WebhookPingResponse(
        webhook_id=hook_id,
        url="https://example.com/hook",
        event="ping",
        status_code=200,
        success=True,
    )
    assert ping_resp.webhook_id == hook_id
    assert ping_resp.success is True


def test_macro_create_request_validation():
    req = MacroCreateRequest(
        title="  Lease Renewal  ",
        shortcut="lease-renewal",
        category="  Leasing  ",
        content="Hello {customer_name}, please renew.",
        tags=["leasing", "renewal"],
        status_action="active",
    )
    assert req.title == "Lease Renewal"
    assert req.shortcut == "/lease-renewal"
    assert req.category == "Leasing"
    assert req.content == "Hello {customer_name}, please renew."
    assert req.tags == ["leasing", "renewal"]
    assert req.status_action == "active"

    # Validation errors
    with pytest.raises(ValidationError):
        MacroCreateRequest(title="", shortcut="/valid", content="content")

    with pytest.raises(ValidationError):
        MacroCreateRequest(title="Valid", shortcut="", content="content")

    with pytest.raises(ValidationError):
        MacroCreateRequest(title="Valid", shortcut="/valid", content="")

    with pytest.raises(ValidationError):
        MacroCreateRequest(
            title="Valid",
            shortcut="/valid",
            content="content",
            status_action="invalid_status",
        )


def test_macro_update_request_validation():
    req = MacroUpdateRequest(
        title="  Updated Title  ",
        shortcut="new-sc",
        category="Billing",
        content="New content",
        tags=["billing"],
        status_action="resolved",
    )
    assert req.title == "Updated Title"
    assert req.shortcut == "/new-sc"
    assert req.category == "Billing"
    assert req.content == "New content"
    assert req.status_action == "resolved"

    empty_req = MacroUpdateRequest()
    assert empty_req.title is None
    assert empty_req.shortcut is None
    assert empty_req.status_action is None


def test_macro_response_auto_extracts_variables():
    macro_id = 10
    resp = MacroResponse(
        id=macro_id,
        title="Maintenance Notice",
        shortcut="/maint",
        category="Maintenance",
        content="Hello {customer_name}, unit {unit_id} scheduled for {date}.",
        tags=["maintenance"],
        status_action="active",
    )
    assert resp.id == macro_id
    assert resp.variables == ["customer_name", "date", "unit_id"]


def test_macro_render_request_and_response():
    req = MacroRenderRequest(variables={"customer_name": "Sarah"}, fallback_defaults=True)
    assert req.variables["customer_name"] == "Sarah"
    assert req.fallback_defaults is True

    macro_id = 5
    resp = MacroRenderResponse(
        macro_id=macro_id,
        rendered_content="Hello Sarah, your lease is ready.",
        unresolved_variables=[],
        status_action="active",
    )
    assert resp.macro_id == macro_id
    assert "Hello Sarah" in resp.rendered_content
    assert resp.status_action == "active"


def test_macro_apply_request_validation():
    # Valid with macro_id
    macro_id = 7
    req1 = MacroApplyRequest(macro_id=macro_id)
    assert req1.macro_id == macro_id

    # Valid with shortcut
    req2 = MacroApplyRequest(shortcut="/rent-pay")
    assert req2.shortcut == "/rent-pay"

    # Invalid without either
    with pytest.raises(ValidationError):
        MacroApplyRequest()


def test_macro_apply_response():
    macro_id = 12
    resp = MacroApplyResponse(
        session_id="sess-abc",
        macro_id=macro_id,
        macro_title="Rent Payment",
        rendered_content="Payment details...",
        applied_status="resolved",
        applied_tags=["billing"],
    )
    assert resp.session_id == "sess-abc"
    assert resp.macro_id == macro_id
    assert resp.applied_status == "resolved"
    assert resp.applied_tags == ["billing"]


def test_macro_categories_response():
    expected_categories = 3
    resp = MacroCategoriesResponse(categories=["Billing", "General", "Leasing"])
    assert len(resp.categories) == expected_categories
    assert "Billing" in resp.categories


def test_macro_suggest_request_validation():
    expected_top_k = 5
    expected_min_score = 0.4
    req = MacroSuggestRequest(
        query="water leak in unit 4",
        session_id="s123",
        category="Maintenance",
        top_k=expected_top_k,
        min_score=expected_min_score,
    )
    assert req.query == "water leak in unit 4"
    assert req.session_id == "s123"
    assert req.category == "Maintenance"
    assert req.top_k == expected_top_k
    assert req.min_score == expected_min_score

    # Strips whitespace
    req_strip = MacroSuggestRequest(query="  urgent help  ")
    assert req_strip.query == "urgent help"

    # Reject empty or whitespace query
    with pytest.raises(ValidationError):
        MacroSuggestRequest(query="")

    with pytest.raises(ValidationError):
        MacroSuggestRequest(query="   ")

    # Reject invalid top_k bounds
    with pytest.raises(ValidationError):
        MacroSuggestRequest(query="valid query", top_k=0)

    with pytest.raises(ValidationError):
        MacroSuggestRequest(query="valid query", top_k=11)

    # Reject invalid min_score bounds
    with pytest.raises(ValidationError):
        MacroSuggestRequest(query="valid query", min_score=-0.1)

    with pytest.raises(ValidationError):
        MacroSuggestRequest(query="valid query", min_score=1.5)


def test_macro_suggestion_item_and_response():
    expected_score = 0.92
    item = MacroSuggestionItem(
        macro_id=1,
        title="Emergency Dispatch",
        shortcut="/emerg-maint",
        category="Maintenance",
        content="Dispatched for {unit_id}",
        score=expected_score,
        match_reasons=["Matched emergency intent"],
        detected_intent="maintenance_emergency",
        status_action="escalated",
        tags=["urgent"],
        suggested_variables={"unit_id": "Unit 4B"},
        rendered_preview="Dispatched for Unit 4B",
    )
    assert item.macro_id == 1
    assert item.score == expected_score
    assert item.suggested_variables["unit_id"] == "Unit 4B"

    # Reject score out of bounds
    with pytest.raises(ValidationError):
        MacroSuggestionItem(
            macro_id=1,
            title="T",
            shortcut="/s",
            category="C",
            content="C",
            score=1.2,
        )

    # Test MacroSuggestResponse
    suggest_resp = MacroSuggestResponse(
        query="Help leak",
        detected_intent="maintenance_emergency",
        intent_confidence=0.88,
        extracted_variables={"unit_id": "Unit 4B"},
        suggestions=[item],
        total_matches=1,
    )
    assert suggest_resp.query == "Help leak"
    assert suggest_resp.total_matches == 1
    assert len(suggest_resp.suggestions) == 1

    # Test SessionMacroSuggestionsResponse
    sess_resp = SessionMacroSuggestionsResponse(
        session_id="sess-xyz",
        latest_query="Help leak",
        detected_intent="maintenance_emergency",
        extracted_variables={"unit_id": "Unit 4B"},
        suggestions=[item],
        total_matches=1,
    )
    assert sess_resp.session_id == "sess-xyz"
    assert sess_resp.total_matches == 1
    assert sess_resp.suggestions[0].shortcut == "/emerg-maint"


def test_session_priority_validation_in_models():
    # SessionInfo default priority is medium
    now = datetime.now()
    sess = SessionInfo(
        session_id="s1",
        message_count=1,
        last_active=now,
    )
    assert sess.priority == "medium"

    # UpdateSessionRequest accepts valid priority
    req = UpdateSessionRequest(priority="urgent")
    assert req.priority == "urgent"

    # UpdateSessionRequest accepts uppercase and normalizes to lowercase
    req_upper = UpdateSessionRequest(priority="HIGH")
    assert req_upper.priority == "high"

    # Reject invalid priority
    with pytest.raises(ValidationError):
        UpdateSessionRequest(priority="invalid_prio")


def test_sla_policy_create_request_validation():
    req = SLAPolicyCreateRequest(
        name="Urgent Lease SLA",
        priority="urgent",
        category="lease",
        response_time_minutes=30,
        resolution_time_minutes=120,
    )
    assert req.name == "Urgent Lease SLA"
    assert req.priority == "urgent"
    assert req.category == "lease"
    expected_resp = 30
    expected_resol = 120
    assert req.response_time_minutes == expected_resp
    assert req.resolution_time_minutes == expected_resol
    assert req.is_active is True

    # Empty name rejected
    with pytest.raises(ValidationError):
        SLAPolicyCreateRequest(
            name="",
            priority="urgent",
            response_time_minutes=30,
            resolution_time_minutes=120,
        )

    # Invalid priority rejected
    with pytest.raises(ValidationError):
        SLAPolicyCreateRequest(
            name="Test",
            priority="emergency",
            response_time_minutes=30,
            resolution_time_minutes=120,
        )

    # Zero or negative response time rejected
    with pytest.raises(ValidationError):
        SLAPolicyCreateRequest(
            name="Test",
            priority="urgent",
            response_time_minutes=0,
            resolution_time_minutes=120,
        )

    # Resolution time < response time rejected
    with pytest.raises(ValidationError):
        SLAPolicyCreateRequest(
            name="Test",
            priority="urgent",
            response_time_minutes=120,
            resolution_time_minutes=30,
        )


def test_sla_policy_update_request_validation():
    req = SLAPolicyUpdateRequest(
        name="Updated Name",
        response_time_minutes=45,
    )
    assert req.name == "Updated Name"
    expected_resp = 45
    assert req.response_time_minutes == expected_resp

    # Empty update raises validation error
    with pytest.raises(ValidationError):
        SLAPolicyUpdateRequest()

    # Resolution < response raises validation error
    with pytest.raises(ValidationError):
        SLAPolicyUpdateRequest(response_time_minutes=100, resolution_time_minutes=50)


def test_sla_policy_response_models():
    pol_id = 5
    resp = SLAPolicyResponse(
        id=pol_id,
        name="General SLA",
        priority="medium",
        category="general",
        response_time_minutes=240,
        resolution_time_minutes=1440,
        is_active=True,
        created_at="2026-10-08T00:00:00Z",
    )
    assert resp.id == pol_id
    assert resp.priority == "medium"
    assert resp.is_active is True

    list_resp = SLAPoliciesListResponse(items=[resp], total=1)
    assert list_resp.total == 1
    assert len(list_resp.items) == 1


def test_session_sla_status_response_model():
    status_resp = SessionSLAStatusResponse(
        session_id="sess-sla-1",
        priority="urgent",
        category="maintenance",
        status="active",
        policy_id=1,
        policy_name="Urgent Maintenance SLA",
        response_target_minutes=15,
        resolution_target_minutes=120,
        session_started_at="2026-10-08T10:00:00Z",
        response_due_at="2026-10-08T10:15:00Z",
        resolution_due_at="2026-10-08T12:00:00Z",
        response_met=False,
        resolution_met=False,
        response_breached=False,
        resolution_breached=False,
        response_approaching=True,
        resolution_approaching=False,
        breach_status="approaching_breach",
        minutes_to_response_deadline=5.0,
        minutes_to_resolution_deadline=110.0,
    )
    assert status_resp.session_id == "sess-sla-1"
    assert status_resp.breach_status == "approaching_breach"
    assert status_resp.response_approaching is True


def test_sla_alert_and_analytics_models():
    item = SLAAlertItem(
        session_id="sess-alert",
        priority="urgent",
        category="maintenance",
        event="sla.approaching_breach",
        breach_type="response",
        deadline_due_at="2026-10-08T10:15:00Z",
        minutes_remaining=4.5,
        webhooks_dispatched=2,
    )
    assert item.event == "sla.approaching_breach"
    expected_wh = 2
    assert item.webhooks_dispatched == expected_wh

    alert_eval = SLAAlertEvaluateResponse(
        total_sessions_checked=5,
        alerts_triggered=1,
        alerts=[item],
    )
    expected_sessions_checked = 5
    assert alert_eval.total_sessions_checked == expected_sessions_checked
    assert alert_eval.alerts_triggered == 1

    analytics = SLAComplianceAnalyticsResponse(
        total_tracked_sessions=10,
        compliance_rate=90.0,
        met_sessions=7,
        healthy_sessions=2,
        approaching_breach_sessions=1,
        breached_sessions=1,
        avg_first_response_minutes=12.5,
        priority_breakdown={"urgent": {"total": 2, "breached": 0}},
    )
    expected_total_sessions = 10
    assert analytics.total_tracked_sessions == expected_total_sessions
    expected_rate = 90.0
    assert analytics.compliance_rate == expected_rate


