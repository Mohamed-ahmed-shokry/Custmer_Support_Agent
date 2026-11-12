from datetime import datetime

import pytest
from api.pydantic_models import (
    DEFAULT_MODEL,
    AccessControlMetricsResponse,
    AccessCredentialCreateRequest,
    AccessCredentialItem,
    AccessCredentialListResponse,
    AccessCredentialResponse,
    AccessCredentialUpdateRequest,
    AgentPerformanceScorecardsResponse,
    AgentScorecardItem,
    AgentWorkloadItem,
    AgentWorkloadResponse,
    AmenityCreateRequest,
    AmenityItem,
    AmenityMetricsResponse,
    AmenityResponse,
    AnnouncementAcknowledgeRequest,
    AnnouncementAcknowledgmentItem,
    AnnouncementAcknowledgmentListResponse,
    AnnouncementAcknowledgmentResponse,
    AnnouncementsMetricsResponse,
    AutoAssignRequest,
    BillingMetricsResponse,
    BillingTransactionCreateRequest,
    BillingTransactionItem,
    BillingTransactionListResponse,
    BillingTransactionResponse,
    BillingTransactionUpdateRequest,
    BusinessHoursStatusResponse,
    ChunkingStrategy,
    CollectionAnalyticsResponse,
    CollectionRechunkRequest,
    CollectionRechunkResponse,
    CommunityAnnouncementCreateRequest,
    CommunityAnnouncementItem,
    CommunityAnnouncementListResponse,
    CommunityAnnouncementResponse,
    CommunityAnnouncementUpdateRequest,
    CommunityIncidentCreateRequest,
    CommunityIncidentItem,
    CommunityIncidentListResponse,
    CommunityIncidentResponse,
    CommunityIncidentUpdateRequest,
    ConciergeRequestCreateRequest,
    ConciergeRequestItem,
    ConciergeRequestResponse,
    ConciergeRequestUpdateRequest,
    CSATFeedbackSubmitRequest,
    CSATSummaryResponse,
    DocumentDetailResponse,
    DocumentRechunkItem,
    FeedbackReviewItemResponse,
    FeedbackReviewQueueResponse,
    FeedbackReviewUpdateRequest,
    FreightElevatorBookingCreateRequest,
    FreightElevatorBookingItem,
    FreightElevatorBookingListResponse,
    FreightElevatorBookingResponse,
    GuestPassCreateRequest,
    GuestPassItem,
    GuestPassListResponse,
    GuestPassResponse,
    GuestPassUpdateRequest,
    IncidentMetricsResponse,
    InspectionCompleteRequest,
    InspectionCreateRequest,
    InspectionDocumentPublishRequest,
    InspectionDocumentPublishResponse,
    InspectionItemSchema,
    InspectionListResponse,
    InspectionMetricsResponse,
    InspectionRecord,
    InspectionResponse,
    InspectionUpdateRequest,
    InspectionWorkOrderConversionRequest,
    IntercomDirectoryCreateRequest,
    IntercomDirectoryItem,
    IntercomDirectoryListResponse,
    IntercomDirectoryResponse,
    IntercomDirectoryUpdateRequest,
    KnowledgeArticleCreateRequest,
    KnowledgeArticleItem,
    KnowledgeArticleListResponse,
    KnowledgeArticlePublishRequest,
    KnowledgeArticlePublishResponse,
    KnowledgeArticleUpdateRequest,
    KnowledgeBaseAnalyticsResponse,
    KnowledgeGapCreateRequest,
    KnowledgeGapItem,
    KnowledgeGapListResponse,
    KnowledgeGapScanResponse,
    KnowledgeGapUpdateRequest,
    LeaseRenewalCreateRequest,
    LeaseRenewalDocumentPublishRequest,
    LeaseRenewalDocumentPublishResponse,
    LeaseRenewalItem,
    LeaseRenewalListResponse,
    LeaseRenewalMetricsResponse,
    LeaseRenewalResponse,
    LeaseRenewalSignRequest,
    LeaseRenewalUpdateRequest,
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
    MoveChecklistItem,
    MoveChecklistToggleRequest,
    MoveLogisticsCreateRequest,
    MoveLogisticsItem,
    MoveLogisticsListResponse,
    MoveLogisticsMetricsResponse,
    MoveLogisticsResponse,
    MoveLogisticsUpdateRequest,
    PackageCarrier,
    PackageCreateRequest,
    PackageItem,
    PackageListResponse,
    PackageMetricsResponse,
    PackagePickupRequest,
    PackageResponse,
    PackageStatus,
    PackageUpdateRequest,
    ParkingMetricsResponse,
    ParkingSpotCreateRequest,
    ParkingSpotItem,
    ParkingSpotListResponse,
    ParkingSpotResponse,
    ParkingSpotUpdateRequest,
    ParkingViolationCreateRequest,
    ParkingViolationItem,
    ParkingViolationListResponse,
    ParkingViolationResponse,
    ParkingViolationUpdateRequest,
    PetCreateRequest,
    PetIncidentCreateRequest,
    PetIncidentItem,
    PetIncidentListResponse,
    PetIncidentResponse,
    PetIncidentUpdateRequest,
    PetItem,
    PetListResponse,
    PetMetricsResponse,
    PetPolicyCreateRequest,
    PetPolicyItem,
    PetPolicyListResponse,
    PetPolicyResponse,
    PetPolicyUpdateRequest,
    PetResponse,
    PetUpdateRequest,
    QueryInput,
    QueryResponse,
    RechunkDocumentRequest,
    ReservationCreateRequest,
    ReservationItem,
    ReservationResponse,
    SessionAcknowledgeAlertRequest,
    SessionAssignmentHistoryResponse,
    SessionAssignmentRecord,
    SessionAssignmentRequest,
    SessionCreateConciergeRequest,
    SessionDraftArticleRequest,
    SessionGenerateGuestPassRequest,
    SessionInfo,
    SessionInspectionCreateRequest,
    SessionIntakePackageRequest,
    SessionIssueViolationNoticeRequest,
    SessionMacroSuggestionsResponse,
    SessionRegisterPetRequest,
    SessionReportLostFobRequest,
    SessionReserveElevatorRequest,
    SessionScheduleMoveRequest,
    SessionSLAStatusResponse,
    SessionSubmitViolationAppealRequest,
    SessionSummaryRequest,
    SessionSummaryResponse,
    SessionTenantContextResponse,
    SessionTenantLinkRequest,
    SLAAlertEvaluateResponse,
    SLAAlertItem,
    SLAComplianceAnalyticsResponse,
    SLAPoliciesListResponse,
    SLAPolicyCreateRequest,
    SLAPolicyResponse,
    SLAPolicyUpdateRequest,
    SourceInfo,
    SupportAgentCreateRequest,
    SupportAgentListResponse,
    SupportAgentResponse,
    SupportAgentUpdateRequest,
    SupportTriageAnalyticsResponse,
    TagCount,
    TenantCreateRequest,
    TenantItem,
    TenantLedgerSummaryResponse,
    TenantListResponse,
    TenantPaymentRequest,
    TenantPaymentResponse,
    TenantResponse,
    TenantSupportHistoryResponse,
    TenantSupportHistorySessionItem,
    TenantUpdateRequest,
    UnitCreateRequest,
    UnitItem,
    UnitListResponse,
    UnitResponse,
    UnitUpdateRequest,
    UpdateSessionRequest,
    VehicleItem,
    VehicleListResponse,
    VehicleRegisterRequest,
    VehicleResponse,
    VehicleUpdateRequest,
    ViolationAppealCreateRequest,
    ViolationAppealItem,
    ViolationAppealListResponse,
    ViolationAppealResponse,
    ViolationAppealUpdateRequest,
    ViolationNoticeCreateRequest,
    ViolationNoticeItem,
    ViolationNoticeListResponse,
    ViolationNoticeResponse,
    ViolationNoticeUpdateRequest,
    VisitorPassCreateRequest,
    VisitorPassItem,
    VisitorPassListResponse,
    VisitorPassResponse,
    VisitorPassUpdateRequest,
    WebhookCreateRequest,
    WebhookDeliveryLogItem,
    WebhookDeliveryLogsResponse,
    WebhookPingResponse,
    WebhookResponse,
    WebhookUpdateRequest,
    WorkOrderCategory,
    WorkOrderCreateRequest,
    WorkOrderFromSessionRequest,
    WorkOrderItem,
    WorkOrderListResponse,
    WorkOrderMetricsResponse,
    WorkOrderPriority,
    WorkOrderResponse,
    WorkOrderStatus,
    WorkOrderUpdateRequest,
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


def test_session_info_and_update_with_assignment_fields():
    now = datetime(2026, 10, 11, 10, 0, 0)
    info = SessionInfo(
        session_id="s-assign-1",
        message_count=1,
        last_active=now,
        assigned_agent="sarah_concierge",
        escalation_tier="tier_2",
    )
    assert info.assigned_agent == "sarah_concierge"
    assert info.escalation_tier == "tier_2"

    # UpdateSessionRequest validations
    update_req = UpdateSessionRequest(
        assigned_agent="david_maintenance",
        escalation_tier="tier_1",
    )
    assert update_req.assigned_agent == "david_maintenance"
    assert update_req.escalation_tier == "tier_1"

    # Invalid escalation tier
    with pytest.raises(ValidationError):
        UpdateSessionRequest(escalation_tier="tier_99")


def test_sla_policy_with_business_hours_field():
    create_req = SLAPolicyCreateRequest(
        name="Business Hours Tier 1",
        priority="high",
        category="leasing",
        response_time_minutes=30,
        resolution_time_minutes=120,
        use_business_hours=True,
    )
    assert create_req.use_business_hours is True

    update_req = SLAPolicyUpdateRequest(use_business_hours=False)
    assert update_req.use_business_hours is False

    policy_resp = SLAPolicyResponse(
        id=1,
        name="Policy 1",
        priority="high",
        category="leasing",
        response_time_minutes=30,
        resolution_time_minutes=120,
        is_active=True,
        use_business_hours=True,
    )
    assert policy_resp.use_business_hours is True

    status_resp = SessionSLAStatusResponse(
        session_id="sess-sla-biz",
        priority="high",
        category="leasing",
        status="active",
        response_target_minutes=30,
        resolution_target_minutes=120,
        use_business_hours=True,
    )
    assert status_resp.use_business_hours is True


def test_support_agent_create_and_update_request():
    agent_req = SupportAgentCreateRequest(
        id="alex_turner",
        name="Alex Turner",
        email="alex@propertymanagement.test",
        tier="tier_2",
        department="maintenance",
    )
    assert agent_req.id == "alex_turner"
    assert agent_req.tier == "tier_2"
    assert agent_req.department == "maintenance"

    # Validation errors: empty id, bad email, bad tier
    with pytest.raises(ValidationError):
        SupportAgentCreateRequest(
            id="",
            name="Alex",
            email="alex@test.com",
        )

    with pytest.raises(ValidationError):
        SupportAgentCreateRequest(
            id="alex",
            name="Alex",
            email="invalid-email",
        )

    with pytest.raises(ValidationError):
        SupportAgentCreateRequest(
            id="alex",
            name="Alex",
            email="alex@test.com",
            tier="tier_invalid",
        )

    # SupportAgentUpdateRequest
    up_req = SupportAgentUpdateRequest(tier="tier_3", is_active=False)
    assert up_req.tier == "tier_3"
    assert up_req.is_active is False

    with pytest.raises(ValidationError):
        SupportAgentUpdateRequest()  # at least one field required


def test_support_agent_response_and_list():
    resp = SupportAgentResponse(
        id="agent_1",
        name="Agent One",
        email="agent1@test.com",
        tier="tier_1",
        department="general_leasing",
        is_active=True,
    )
    assert resp.id == "agent_1"
    assert resp.is_active is True

    list_resp = SupportAgentListResponse(items=[resp], total=1)
    assert list_resp.total == 1
    assert len(list_resp.items) == 1


def test_session_assignment_request_and_history():
    assign_req = SessionAssignmentRequest(
        agent_id="sarah_concierge",
        tier="tier_2",
        assigned_by="dispatcher",
        reason="Resident requested supervisor",
    )
    assert assign_req.agent_id == "sarah_concierge"
    assert assign_req.tier == "tier_2"
    assert assign_req.assigned_by == "dispatcher"

    with pytest.raises(ValidationError):
        SessionAssignmentRequest(tier="invalid_tier")

    auto_req = AutoAssignRequest(
        strategy="least_busy",
        target_tier="tier_1",
        department="general_leasing",
    )
    assert auto_req.strategy == "least_busy"
    assert auto_req.target_tier == "tier_1"

    rec = SessionAssignmentRecord(
        id=1,
        session_id="s123",
        assigned_by="system",
        previous_agent=None,
        new_agent="sarah_concierge",
        previous_tier="tier_1",
        new_tier="tier_2",
        reason="Escalated to Tier 2",
        assigned_at="2026-10-11T12:00:00",
    )
    hist_resp = SessionAssignmentHistoryResponse(session_id="s123", items=[rec], total=1)
    assert hist_resp.total == 1
    assert hist_resp.items[0].new_agent == "sarah_concierge"


def test_agent_workload_and_business_hours_response():
    agent = SupportAgentResponse(
        id="agent_1",
        name="Agent One",
        email="agent1@test.com",
        tier="tier_1",
        department="general_leasing",
        is_active=True,
    )
    workload_item = AgentWorkloadItem(
        agent=agent,
        active_sessions_count=3,
        resolved_sessions_count=12,
        total_sessions_count=15,
    )
    expected_active = 3
    assert workload_item.active_sessions_count == expected_active

    workload_resp = AgentWorkloadResponse(
        agents=[workload_item],
        total_active_sessions=3,
        unassigned_active_sessions=1,
        tier_distribution={"tier_1": 3},
    )
    assert workload_resp.total_active_sessions == expected_active
    assert workload_resp.unassigned_active_sessions == 1

    biz_resp = BusinessHoursStatusResponse(
        is_open=True,
        current_time="2026-10-12T10:00:00",
        next_open_at=None,
        timezone="UTC",
        schedule={"monday": "09:00 - 18:00"},
        day_name="Monday",
    )
    assert biz_resp.is_open is True
    assert biz_resp.day_name == "Monday"


def test_csat_feedback_submit_request_validations():
    # Valid model
    req = CSATFeedbackSubmitRequest(
        session_id="  sess-123  ",
        score=5,
        resolution_satisfaction=4,
        agent_helpfulness=5,
        response_speed=4,
        comment="  Great support experience!  ",
        assigned_agent="  agent_john  ",
        escalation_tier="tier_2",
    )
    assert req.session_id == "sess-123"
    assert req.score == 5  # noqa: PLR2004
    assert req.comment == "Great support experience!"
    assert req.assigned_agent == "agent_john"
    assert req.escalation_tier == "tier_2"

    # Unassigned agent turns into None
    req_unassigned = CSATFeedbackSubmitRequest(
        session_id="sess-456",
        score=3,
        assigned_agent="unassigned",
    )
    assert req_unassigned.assigned_agent is None

    # Score out of bounds
    with pytest.raises(ValidationError):
        CSATFeedbackSubmitRequest(session_id="sess-1", score=0)
    with pytest.raises(ValidationError):
        CSATFeedbackSubmitRequest(session_id="sess-1", score=6)

    # Empty session_id
    with pytest.raises(ValidationError):
        CSATFeedbackSubmitRequest(session_id="   ", score=5)


def test_csat_review_and_scorecard_models():
    # Review update request
    rev_req = FeedbackReviewUpdateRequest(
        review_status="followup_required",
        reviewer_notes="Customer requested follow-up",
        reviewed_by="supervisor_1",
    )
    assert rev_req.review_status == "followup_required"
    assert rev_req.reviewer_notes == "Customer requested follow-up"
    assert rev_req.reviewed_by == "supervisor_1"

    # Invalid review status raises ValueError
    with pytest.raises(ValueError):
        FeedbackReviewUpdateRequest(review_status="invalid_status")

    # Summary model
    summary = CSATSummaryResponse(
        total_responses=10,
        avg_csat_score=4.2,
        avg_resolution_score=4.0,
        avg_helpfulness_score=4.5,
        avg_speed_score=4.1,
        satisfaction_rate=80.0,
        dissatisfaction_rate=10.0,
        star_distribution={1: 1, 2: 0, 3: 1, 4: 3, 5: 5},
        pending_review_count=2,
        followup_required_count=1,
    )
    expected_tot = 10
    assert summary.total_responses == expected_tot
    assert summary.star_distribution[5] == 5  # noqa: PLR2004

    # Scorecard model
    scorecard = AgentScorecardItem(
        agent_id="agent_alice",
        tier="tier_1",
        total_ratings=5,
        avg_csat_score=4.8,
        avg_resolution_score=4.8,
        avg_helpfulness_score=5.0,
        avg_speed_score=4.6,
        positive_count=5,
        negative_count=0,
        satisfaction_rate=100.0,
    )
    scorecards_resp = AgentPerformanceScorecardsResponse(
        scorecards=[scorecard],
        total_agents=1,
    )
    assert scorecards_resp.total_agents == 1
    assert scorecards_resp.scorecards[0].agent_id == "agent_alice"

    # Review queue item & list
    item = FeedbackReviewItemResponse(
        id=1,
        session_id="sess-99",
        score=1,
        rating=-1,
        resolution_satisfaction=1,
        agent_helpfulness=2,
        response_speed=1,
        comment="Terrible speed",
        review_status="pending_review",
        assigned_agent="agent_bob",
        escalation_tier="tier_1",
        created_at="2026-10-12 10:00:00",
    )
    queue_resp = FeedbackReviewQueueResponse(items=[item], total=1, limit=50, offset=0)
    assert queue_resp.total == 1
    assert queue_resp.items[0].score == 1


def test_knowledge_base_pydantic_models():
    expected_freq = 3
    expected_total_gaps = 3
    expected_article_id = 42
    expected_chunk_size = 800
    expected_file_id = 12
    expected_gaps_count = 5
    expected_resolution_rate = 40.0

    # 1. KnowledgeGapCreateRequest valid & validation error
    gap_req = KnowledgeGapCreateRequest(
        query="  How to reserve freight elevator?  ",
        category="policy",
        source_type="unanswered_query",
        session_id="sess-100",
        priority="high",
        notes="Recurring inquiry",
    )
    assert gap_req.query == "  How to reserve freight elevator?  "
    assert gap_req.category == "policy"

    with pytest.raises(ValidationError):
        KnowledgeGapCreateRequest(query="")

    # 2. KnowledgeGapUpdateRequest
    up_req = KnowledgeGapUpdateRequest(status="resolved", priority="low", notes="Fixed")
    assert up_req.status == "resolved"
    assert up_req.priority == "low"

    # 3. KnowledgeGapItem and KnowledgeGapListResponse
    gap_item = KnowledgeGapItem(
        id=1,
        query="How to reserve freight elevator?",
        normalized_query="how to reserve freight elevator",
        category="general",
        frequency=expected_freq,
        priority="high",
        status="open",
    )
    list_resp = KnowledgeGapListResponse(items=[gap_item], total=1)
    assert list_resp.total == 1
    assert list_resp.items[0].frequency == expected_freq

    # 4. KnowledgeGapScanResponse
    scan_resp = KnowledgeGapScanResponse(
        scanned_sessions_count=10,
        gaps_created=2,
        gaps_incremented=1,
        total_gaps_identified=expected_total_gaps,
        gaps=[gap_item],
    )
    assert scan_resp.total_gaps_identified == expected_total_gaps

    # 5. KnowledgeArticleCreateRequest and KnowledgeArticleUpdateRequest
    art_req = KnowledgeArticleCreateRequest(
        title="Freight Elevator Guide",
        content_markdown="# Freight Elevator\n\nBooking guide.",
        category="policy",
        tags=["elevator", "moving"],
    )
    assert art_req.category == "policy"

    art_up = KnowledgeArticleUpdateRequest(
        title="Updated Guide",
        status="published",
    )
    assert art_up.status == "published"

    # 6. KnowledgeArticleItem and KnowledgeArticleListResponse
    art_item = KnowledgeArticleItem(
        id=expected_article_id,
        title="Freight Elevator Guide",
        category="policy",
        content_markdown="# Guide",
        status="draft",
    )
    art_list = KnowledgeArticleListResponse(items=[art_item], total=1)
    assert art_list.total == 1
    assert art_list.items[0].id == expected_article_id

    # 7. KnowledgeArticlePublishRequest & Response
    pub_req = KnowledgeArticlePublishRequest(collection="policies", chunk_size=expected_chunk_size)
    assert pub_req.chunk_size == expected_chunk_size

    pub_resp = KnowledgeArticlePublishResponse(
        article=art_item,
        file_id=expected_file_id,
        collection="policies",
        indexed_in_vectorstore=True,
        linked_gap_resolved=True,
    )
    assert pub_resp.file_id == expected_file_id
    assert pub_resp.indexed_in_vectorstore is True

    # 8. SessionDraftArticleRequest
    draft_req = SessionDraftArticleRequest(author="operator_dan", link_gap_id=1)
    assert draft_req.author == "operator_dan"
    assert draft_req.link_gap_id == 1

    # 9. KnowledgeBaseAnalyticsResponse
    analytics_resp = KnowledgeBaseAnalyticsResponse(
        total_gaps=expected_gaps_count,
        open_gaps_count=2,
        drafting_gaps_count=1,
        resolved_gaps_count=2,
        gap_resolution_rate=expected_resolution_rate,
        total_articles=3,
        published_articles_count=2,
        estimated_deflected_queries=15,
    )
    assert analytics_resp.total_gaps == expected_gaps_count
    assert analytics_resp.gap_resolution_rate == expected_resolution_rate


def test_unit_models_validations_and_roundtrip():
    # 1. Valid UnitCreateRequest
    unit_rent = 1850.0
    req = UnitCreateRequest(
        id="unit_301",
        property_name="Sunset Heights",
        unit_number="301",
        building_name="Tower C",
        floor=3,
        monthly_rent=unit_rent,
        parking_spot="P-301",
        gate_code="#3010",
    )
    assert req.id == "unit_301"
    assert req.monthly_rent == unit_rent

    # 2. Validation failures
    with pytest.raises(ValidationError):
        UnitCreateRequest(id="invalid id with spaces", property_name="Valid", unit_number="1")
    with pytest.raises(ValidationError):
        UnitCreateRequest(id="unit_1", property_name="", unit_number="1")
    with pytest.raises(ValidationError):
        UnitCreateRequest(id="unit_1", property_name="Valid", unit_number="")

    # 3. UnitUpdateRequest
    updated_rent = 1950.0
    up_req = UnitUpdateRequest(monthly_rent=updated_rent, parking_spot="P-999")
    assert up_req.monthly_rent == updated_rent

    # 4. UnitItem and responses
    item = UnitItem(
        id="unit_301",
        property_name="Sunset Heights",
        unit_number="301",
        monthly_rent=unit_rent,
    )
    resp = UnitResponse(unit=item)
    assert resp.unit.id == "unit_301"
    list_resp = UnitListResponse(items=[item], total=1)
    assert list_resp.total == 1
    assert len(list_resp.items) == 1


def test_tenant_models_validations_and_roundtrip():
    # 1. Valid TenantCreateRequest
    tenant_rent = 1850.0
    balance = 200.0
    req = TenantCreateRequest(
        id="tenant_10",
        first_name="Kyle",
        last_name="Reese",
        email="kyle.reese@example.com",
        phone="+1-555-0399",
        unit_id="unit_301",
        lease_start="2026-01-01",
        lease_end="2026-12-31",
        monthly_rent=tenant_rent,
        balance_due=balance,
        status="active",
    )
    assert req.id == "tenant_10"
    assert req.email == "kyle.reese@example.com"
    assert req.monthly_rent == tenant_rent

    # 2. Validation failures
    with pytest.raises(ValidationError):
        TenantCreateRequest(
            id="tenant_10",
            first_name="Kyle",
            last_name="Reese",
            email="invalid-email",
            phone="555-0100",
            lease_start="2026-01-01",
            lease_end="2026-12-31",
        )
    with pytest.raises(ValidationError):
        TenantCreateRequest(
            id="tenant_10",
            first_name="Kyle",
            last_name="Reese",
            email="kyle@example.com",
            phone="555-0100",
            lease_start="invalid-date",
            lease_end="2026-12-31",
        )
    with pytest.raises(ValidationError):
        TenantCreateRequest(
            id="tenant_10",
            first_name="Kyle",
            last_name="Reese",
            email="kyle@example.com",
            phone="555-0100",
            lease_start="2026-01-01",
            lease_end="2026-12-31",
            status="invalid_status",
        )

    # 3. TenantUpdateRequest
    up_req = TenantUpdateRequest(status="past_due", balance_due=500.0)
    assert up_req.status == "past_due"

    # 4. TenantItem and responses
    item = TenantItem(
        id="tenant_10",
        first_name="Kyle",
        last_name="Reese",
        email="kyle.reese@example.com",
        phone="+1-555-0399",
        lease_start="2026-01-01",
        lease_end="2026-12-31",
        monthly_rent=tenant_rent,
    )
    resp = TenantResponse(tenant=item)
    assert resp.tenant.id == "tenant_10"
    list_resp = TenantListResponse(items=[item], total=1)
    assert list_resp.total == 1


def test_session_tenant_link_and_context_models():
    # 1. SessionTenantLinkRequest
    link_req = SessionTenantLinkRequest(tenant_id="tenant_1", unit_id="unit_101")
    assert link_req.tenant_id == "tenant_1"
    assert link_req.unit_id == "unit_101"

    # 2. SessionTenantContextResponse
    u_item = UnitItem(id="unit_101", property_name="Sunset Heights", unit_number="101")
    t_item = TenantItem(
        id="tenant_1",
        first_name="Sarah",
        last_name="Connor",
        email="sarah@example.com",
        phone="555-0199",
        lease_start="2026-01-01",
        lease_end="2026-12-31",
    )
    ctx_resp = SessionTenantContextResponse(
        session_id="sess-link-1",
        tenant_id="tenant_1",
        unit_id="unit_101",
        tenant=t_item,
        unit=u_item,
    )
    assert ctx_resp.session_id == "sess-link-1"
    assert ctx_resp.tenant is not None
    assert ctx_resp.tenant.first_name == "Sarah"

    # 3. TenantSupportHistoryResponse
    h_item = TenantSupportHistorySessionItem(
        session_id="sess-link-1",
        label="HVAC Ticket",
        status="resolved",
        rating=1,
        message_count=3,
        preview="HVAC inquiry",
    )
    hist_resp = TenantSupportHistoryResponse(
        tenant=t_item,
        total_sessions=1,
        sessions=[h_item],
    )
    assert hist_resp.total_sessions == 1
    assert hist_resp.sessions[0].label == "HVAC Ticket"


def test_work_order_enums():
    assert WorkOrderCategory.PLUMBING == "plumbing"
    assert WorkOrderCategory.HVAC == "hvac"
    assert WorkOrderCategory.ELECTRICAL == "electrical"
    assert WorkOrderCategory.APPLIANCE == "appliance"
    assert WorkOrderCategory.PEST == "pest"
    assert WorkOrderCategory.STRUCTURAL == "structural"
    assert WorkOrderCategory.SECURITY == "security"
    assert WorkOrderCategory.GENERAL == "general"

    assert WorkOrderPriority.LOW == "low"
    assert WorkOrderPriority.MEDIUM == "medium"
    assert WorkOrderPriority.HIGH == "high"
    assert WorkOrderPriority.EMERGENCY == "emergency"

    assert WorkOrderStatus.SUBMITTED == "submitted"
    assert WorkOrderStatus.SCHEDULED == "scheduled"
    assert WorkOrderStatus.IN_PROGRESS == "in_progress"
    assert WorkOrderStatus.ON_HOLD == "on_hold"
    assert WorkOrderStatus.COMPLETED == "completed"
    assert WorkOrderStatus.CANCELLED == "cancelled"


def test_work_order_create_request_validation():
    # Valid creation request
    expected_est = 150.0
    req = WorkOrderCreateRequest(
        id="wo_req_1",
        unit_id="unit_101",
        title="Kitchen Sink Leak",
        description="Steady dripping under sink",
        category="plumbing",
        priority="high",
        status="submitted",
        entry_permission="call_first",
        assigned_to="Apex Plumbing",
        estimated_cost=expected_est,
    )
    assert req.id == "wo_req_1"
    assert req.unit_id == "unit_101"
    assert req.title == "Kitchen Sink Leak"
    assert req.category == "plumbing"
    assert req.priority == "high"
    assert req.estimated_cost == expected_est

    # Auto-normalization to lowercase
    normalized_req = WorkOrderCreateRequest(
        unit_id="unit_204",
        title="AC Issue",
        description="AC not blowing cold",
        category="HVAC",
        priority="EMERGENCY",
        status="SCHEDULED",
        entry_permission="PERMISSION_GRANTED",
    )
    assert normalized_req.category == "hvac"
    assert normalized_req.priority == "emergency"
    assert normalized_req.status == "scheduled"
    assert normalized_req.entry_permission == "permission_granted"

    # Validation errors on invalid fields
    with pytest.raises(ValidationError):
        WorkOrderCreateRequest(
            unit_id="unit_101",
            title="",
            description="Testing blank title",
        )

    with pytest.raises(ValidationError):
        WorkOrderCreateRequest(
            unit_id="unit_101",
            title="Valid Title",
            description="",
        )

    with pytest.raises(ValidationError):
        WorkOrderCreateRequest(
            unit_id="unit_101",
            title="Valid Title",
            description="Valid Desc",
            category="invalid_category",
        )

    with pytest.raises(ValidationError):
        WorkOrderCreateRequest(
            unit_id="unit_101",
            title="Valid Title",
            description="Valid Desc",
            priority="invalid_priority",
        )


def test_work_order_update_request_validation():
    # Valid partial update
    expected_cost = 175.0
    up_req = WorkOrderUpdateRequest(
        title="Updated title",
        priority="emergency",
        status="completed",
        completed_at="2026-10-15T12:00:00",
        actual_cost=expected_cost,
    )
    assert up_req.title == "Updated title"
    assert up_req.priority == "emergency"
    assert up_req.status == "completed"
    assert up_req.actual_cost == expected_cost

    # Invalid status update raises ValidationError
    with pytest.raises(ValidationError):
        WorkOrderUpdateRequest(status="invalid_status")


def test_work_order_from_session_request():
    req = WorkOrderFromSessionRequest(
        title="Noise complaint / Lock repair",
        description="Front door lock jammed",
        category="security",
        priority="high",
        entry_permission="appointment_only",
    )
    assert req.title == "Noise complaint / Lock repair"
    assert req.category == "security"
    assert req.priority == "high"
    assert req.entry_permission == "appointment_only"


def test_work_order_response_and_list_models():
    item = WorkOrderItem(
        id="wo_test_item",
        unit_id="unit_101",
        title="Ceiling fan wobbling",
        description="Wobbles on high speed",
        category="electrical",
        priority="low",
        status="submitted",
        entry_permission="permission_granted",
    )
    resp = WorkOrderResponse(work_order=item)
    assert resp.work_order.id == "wo_test_item"
    assert resp.work_order.title == "Ceiling fan wobbling"

    list_resp = WorkOrderListResponse(items=[item], total=1, limit=50, offset=0)
    assert list_resp.total == 1
    assert len(list_resp.items) == 1
    assert list_resp.items[0].id == "wo_test_item"


def test_work_order_metrics_response():
    expected_tot = 10
    expected_open = 6
    expected_em = 2
    expected_est = 1200.0
    metrics = WorkOrderMetricsResponse(
        total_work_orders=expected_tot,
        open_work_orders=expected_open,
        emergency_work_orders=expected_em,
        in_progress_work_orders=3,
        completed_work_orders=4,
        by_status={"submitted": 3, "in_progress": 3, "completed": 4},
        by_priority={"low": 2, "medium": 4, "high": 2, "emergency": 2},
        by_category={"plumbing": 4, "hvac": 4, "general": 2},
        total_estimated_cost=expected_est,
        total_actual_cost=1150.0,
    )
    assert metrics.total_work_orders == expected_tot
    assert metrics.open_work_orders == expected_open
    assert metrics.emergency_work_orders == expected_em
    assert metrics.total_estimated_cost == expected_est


def test_billing_transaction_models():
    expected_amount = 1450.0
    req = BillingTransactionCreateRequest(
        tenant_id="tenant_1",
        unit_id="unit_101",
        description="Monthly Rent - November 2026",
        amount=expected_amount,
        transaction_type="rent",
        status="posted",
        due_date="2026-11-01",
    )
    assert req.tenant_id == "tenant_1"
    assert req.amount == expected_amount
    assert req.transaction_type == "rent"
    assert req.status == "posted"

    upd = BillingTransactionUpdateRequest(
        status="paid",
        notes="Paid via portal",
    )
    assert upd.status == "paid"
    assert upd.notes == "Paid via portal"

    item = BillingTransactionItem(
        id="tx_test_101",
        tenant_id="tenant_1",
        unit_id="unit_101",
        transaction_type="rent",
        amount=expected_amount,
        status="paid",
        due_date="2026-11-01",
        paid_at="2026-11-02T10:00:00",
        payment_method="ach",
        reference_number="ACH-9988",
        description="Monthly Rent",
    )
    resp = BillingTransactionResponse(transaction=item)
    assert resp.transaction.id == "tx_test_101"

    list_resp = BillingTransactionListResponse(items=[item], total=1, limit=50, offset=0)
    assert list_resp.total == 1
    assert len(list_resp.items) == 1


def test_tenant_payment_and_ledger_models():
    pay_amount = 500.0
    expected_new_balance = 950.0
    pay_req = TenantPaymentRequest(
        amount=pay_amount,
        payment_method="online_portal",
        reference_number="REF-PAY-123",
        description="Resident partial payment",
    )
    assert pay_req.amount == pay_amount
    assert pay_req.payment_method == "online_portal"

    item = BillingTransactionItem(
        id="tx_pay_1",
        tenant_id="tenant_1",
        unit_id="unit_101",
        transaction_type="payment",
        amount=pay_amount,
        status="paid",
        payment_method="online_portal",
        reference_number="REF-PAY-123",
        description="Resident partial payment",
    )
    pay_resp = TenantPaymentResponse(
        transaction=item,
        previous_balance=1450.0,
        new_balance=expected_new_balance,
        amount_paid=pay_amount,
        tenant_status="active",
    )
    assert pay_resp.amount_paid == pay_amount
    assert pay_resp.new_balance == expected_new_balance

    ledger_resp = TenantLedgerSummaryResponse(
        tenant_id="tenant_1",
        unit_id="unit_101",
        current_balance=expected_new_balance,
        monthly_rent=1450.0,
        total_charges=1450.0,
        total_payments=pay_amount,
        overdue_amount=0.0,
        overdue_count=0,
        tenant_status="active",
        last_payment=item,
        recent_transactions=[item],
    )
    assert ledger_resp.tenant_id == "tenant_1"
    assert ledger_resp.current_balance == expected_new_balance
    assert len(ledger_resp.recent_transactions) == 1

    expected_total_tx = 10
    expected_col_rate = 80.0
    metrics_resp = BillingMetricsResponse(
        total_transactions=expected_total_tx,
        total_billed=10000.0,
        total_collected=8000.0,
        collection_rate=expected_col_rate,
        total_outstanding=2000.0,
        overdue_transactions_count=1,
        overdue_tenants_count=1,
        by_type={"rent": 8, "payment": 2},
        by_status={"paid": 7, "overdue": 1, "posted": 2},
        by_payment_method={"ach": 2},
    )
    assert metrics_resp.total_transactions == expected_total_tx
    assert metrics_resp.collection_rate == expected_col_rate


def test_lease_renewal_models():
    # 1. Valid create request
    req = LeaseRenewalCreateRequest(
        tenant_id="tenant_1",
        unit_id="unit_101",
        proposed_rent=1500.0,
        current_rent=1450.0,
        term_months=12,
        start_date="2026-11-01",
        end_date="2027-10-31",
        concession_amount=100.0,
        concession_notes="Credit upon signing",
        status="offered",
        notes="Standard offer",
    )
    assert req.tenant_id == "tenant_1"
    assert req.proposed_rent == 1500.0  # noqa: PLR2004
    assert req.term_months == 12  # noqa: PLR2004
    assert req.status == "offered"

    # Validation errors
    with pytest.raises(ValidationError):
        LeaseRenewalCreateRequest(tenant_id="tenant_1", proposed_rent=0.0)

    with pytest.raises(ValidationError):
        LeaseRenewalCreateRequest(tenant_id="tenant_1", term_months=5)

    with pytest.raises(ValidationError):
        LeaseRenewalCreateRequest(tenant_id="tenant_1", status="bad_status")

    # 2. Update request
    up_req = LeaseRenewalUpdateRequest(
        proposed_rent=1550.0,
        term_months=24,
        status="negotiating",
        concession_amount=150.0,
    )
    assert up_req.proposed_rent == 1550.0  # noqa: PLR2004
    assert up_req.term_months == 24  # noqa: PLR2004
    assert up_req.status == "negotiating"

    # 3. Sign request
    sign_req = LeaseRenewalSignRequest(
        signature_name="Sarah Connor",
        signature_ip="192.168.1.10",
        notes="Executed via resident portal",
    )
    assert sign_req.signature_name == "Sarah Connor"
    assert sign_req.signature_ip == "192.168.1.10"

    with pytest.raises(ValidationError):
        LeaseRenewalSignRequest(signature_name="")

    # 4. Item and Response models
    item = LeaseRenewalItem(
        id="lr_101",
        tenant_id="tenant_1",
        unit_id="unit_101",
        current_rent=1450.0,
        proposed_rent=1500.0,
        term_months=12,
        start_date="2026-11-01",
        end_date="2027-10-31",
        concession_amount=100.0,
        concession_notes="Discount",
        security_deposit_change=0.0,
        status="signed",
        expires_at="2026-10-31",
        signature_name="Sarah Connor",
        signature_ip="192.168.1.10",
        signed_at="2026-10-15T10:00:00Z",
        notes="Executed",
        document_file_id=42,
        created_at="2026-10-01T09:00:00Z",
        updated_at="2026-10-15T10:00:00Z",
    )
    resp = LeaseRenewalResponse(renewal=item)
    assert resp.renewal.id == "lr_101"
    assert resp.renewal.status == "signed"

    list_resp = LeaseRenewalListResponse(items=[item], total=1, limit=50, offset=0)
    assert list_resp.total == 1
    assert len(list_resp.items) == 1

    # 5. Publish models
    pub_req = LeaseRenewalDocumentPublishRequest(
        collection="default", chunking_strategy="markdown", chunk_size=1000, chunk_overlap=200
    )
    assert pub_req.chunking_strategy == "markdown"

    pub_resp = LeaseRenewalDocumentPublishResponse(
        renewal_id="lr_101",
        file_id=42,
        filename="lease_renewal_lr_101.md",
        collection="default",
        sha256="abc123hash",
        content_length=1500,
        indexed_in_chroma=True,
    )
    assert pub_resp.file_id == 42  # noqa: PLR2004
    assert pub_resp.indexed_in_chroma is True

    # 6. Metrics model
    expected_total_lr = 5
    expected_rate = 60.0
    metrics_resp = LeaseRenewalMetricsResponse(
        total_renewals=expected_total_lr,
        signed_renewals=3,
        pending_renewals=1,
        draft_renewals=1,
        declined_renewals=0,
        renewal_rate=expected_rate,
        avg_rent_increase_pct=4.5,
        by_status={"signed": 3, "offered": 1, "draft": 1},
        by_term={"12": 4, "24": 1},
    )
    assert metrics_resp.total_renewals == expected_total_lr
    assert metrics_resp.renewal_rate == expected_rate


def test_inspection_models_lifecycle_and_validation():
    # 1. InspectionItemSchema
    item = InspectionItemSchema(
        id="item_1",
        room="Living Room",
        item_name="Hardwood Flooring",
        condition="damaged",
        notes="Deep scratch near window",
        photo_count=2,
        action_needed="repair",
        estimated_cost=150.0,
    )
    assert item.condition == "damaged"
    assert item.action_needed == "repair"
    assert item.estimated_cost == 150.0  # noqa: PLR2004

    # Invalid action raises error
    with pytest.raises(ValidationError):
        InspectionItemSchema(
            room="Bedroom",
            item_name="Carpet",
            action_needed="invalid_action",
        )

    # 2. InspectionCreateRequest
    req = InspectionCreateRequest(
        tenant_id="tenant_1",
        unit_id="unit_101",
        inspection_type="PRE_MOVE_OUT",
        status="SCHEDULED",
        overall_condition="GOOD",
        key_return_status="PENDING",
        items=[item],
        notes="Move-out checklist initiated",
    )
    assert req.inspection_type == "pre_move_out"
    assert req.status == "scheduled"
    assert req.overall_condition == "good"
    assert req.key_return_status == "pending"
    assert len(req.items or []) == 1

    # Invalid inspection type raises error
    with pytest.raises(ValidationError):
        InspectionCreateRequest(tenant_id="tenant_1", inspection_type="invalid_type")

    # 3. InspectionUpdateRequest
    upd = InspectionUpdateRequest(
        status="IN_PROGRESS",
        overall_condition="FAIR",
        key_return_status="RETURNED",
        deposit_deduction_total=150.0,
    )
    assert upd.status == "in_progress"
    assert upd.overall_condition == "fair"
    assert upd.key_return_status == "returned"
    assert upd.deposit_deduction_total == 150.0  # noqa: PLR2004

    # 4. InspectionCompleteRequest
    comp = InspectionCompleteRequest(
        deposit_held=2000.0,
        key_return_status="RETURNED",
        overall_condition="GOOD",
        notes="All cleared",
    )
    assert comp.deposit_held == 2000.0  # noqa: PLR2004
    assert comp.key_return_status == "returned"

    # 5. InspectionWorkOrderConversionRequest
    wo_conv = InspectionWorkOrderConversionRequest(
        item_id="item_1",
        title="Repair scratched hardwood",
        category="general",
        priority="high",
    )
    assert wo_conv.item_id == "item_1"
    assert wo_conv.priority == "high"

    # 6. SessionInspectionCreateRequest
    sess_req = SessionInspectionCreateRequest(
        inspection_type="MOVE_OUT",
        scheduled_date="2026-11-01",
        notes="Initiated via support chat",
    )
    assert sess_req.inspection_type == "move_out"

    # 7. Record, Response, and List Response
    rec = InspectionRecord(
        id="insp_101",
        tenant_id="tenant_1",
        unit_id="unit_101",
        scheduled_date="2026-11-01",
        completed_date="2026-11-01",
        inspector_name="Alex Rivera",
        status="completed",
        overall_condition="good",
        items=[item.model_dump()],
        deposit_deduction_total=150.0,
        deposit_refund_amount=1850.0,
        key_return_status="returned",
        notes="Finalized",
        created_at="2026-11-01T09:00:00Z",
        updated_at="2026-11-01T11:00:00Z",
    )
    resp = InspectionResponse(inspection=rec)
    assert resp.inspection.id == "insp_101"
    assert resp.inspection.deposit_refund_amount == 1850.0  # noqa: PLR2004

    list_resp = InspectionListResponse(items=[rec], total=1, limit=50, offset=0)
    assert list_resp.total == 1
    assert len(list_resp.items) == 1

    # 8. Metrics Response
    metrics = InspectionMetricsResponse(
        total_inspections=4,
        scheduled_count=1,
        in_progress_count=0,
        completed_count=3,
        cancelled_count=0,
        move_in_count=1,
        move_out_count=2,
        other_type_count=1,
        total_deposit_deductions=450.0,
        total_deposit_refunds=4000.0,
        condition_counts={"good": 3, "fair": 1},
    )
    assert metrics.total_inspections == 4  # noqa: PLR2004
    assert metrics.total_deposit_deductions == 450.0  # noqa: PLR2004

    # 9. Document Publish Request & Response
    pub_req = InspectionDocumentPublishRequest(
        collection="default", chunking_strategy="markdown", chunk_size=1000, chunk_overlap=200
    )
    assert pub_req.chunking_strategy == "markdown"

    pub_resp = InspectionDocumentPublishResponse(
        inspection_id="insp_101",
        file_id=12,
        filename="inspection_insp_101.md",
        collection="default",
        sha256="hash123",
        content_length=1200,
        indexed_in_chroma=True,
    )
    assert pub_resp.inspection_id == "insp_101"
    assert pub_resp.indexed_in_chroma is True



def test_package_models_validation() -> None:
    expected_total = 10
    expected_avg_hours = 12.5

    # Carrier & Status enum checks
    assert PackageCarrier.AMAZON == "Amazon"
    assert PackageCarrier.FEDEX == "FedEx"
    assert PackageStatus.DELIVERED == "delivered"
    assert PackageStatus.PICKED_UP == "picked_up"

    # PackageCreateRequest
    create_req = PackageCreateRequest(
        tenant_id="tnt_001",
        unit_id="unit_101",
        carrier="UPS",
        tracking_number="1Z999999",
        pickup_pin="123456",
        location="Locker Bay 1",
        notes="Urgent medication",
    )
    assert create_req.tenant_id == "tnt_001"
    assert create_req.tracking_number == "1Z999999"

    # PackageUpdateRequest
    up_req = PackageUpdateRequest(
        location="Front Desk", notes="Held for pickup", status="delivered"
    )
    assert up_req.location == "Front Desk"

    # PackagePickupRequest
    pu_req = PackagePickupRequest(pickup_pin="654321")
    assert pu_req.pickup_pin == "654321"

    # PackageItem & Response
    item = PackageItem(
        id="pkg_test123",
        tenant_id="tnt_001",
        unit_id="unit_101",
        carrier="Amazon",
        tracking_number="TBA12345",
        pickup_pin="123456",
        location="Locker A-1",
        status="delivered",
        delivered_at="2026-10-29T10:00:00Z",
    )
    resp = PackageResponse(package=item)
    assert resp.package.id == "pkg_test123"

    # PackageListResponse
    list_resp = PackageListResponse(items=[item], total=1, limit=50, offset=0)
    assert len(list_resp.items) == 1
    assert list_resp.total == 1

    # PackageMetricsResponse
    metrics = PackageMetricsResponse(
        total_packages=expected_total,
        delivered_packages=4,
        picked_up_packages=6,
        carrier_breakdown={"Amazon": 5, "UPS": 5},
        average_pickup_hours=expected_avg_hours,
    )
    assert metrics.total_packages == expected_total
    assert metrics.average_pickup_hours == expected_avg_hours

    # SessionIntakePackageRequest
    session_intake = SessionIntakePackageRequest(
        carrier="FedEx",
        tracking_number="FX-889900",
        location="Locker 4",
    )
    assert session_intake.carrier == "FedEx"



def test_amenity_and_reservation_models():
    """Verify v0.43.0 Community Amenity and Reservation Pydantic schemas."""
    expected_total = 10
    expected_revenue = 250.0
    expected_attendees = 12

    # AmenityCreateRequest
    create_req = AmenityCreateRequest(
        name="Skyline Lounge",
        category="rooftop",
        capacity=30,
        hourly_rate=40.0,
        deposit_amount=100.0,
        opening_hour=10,
        closing_hour=22,
    )
    assert create_req.name == "Skyline Lounge"
    assert create_req.category == "rooftop"

    # AmenityItem & Response
    am_item = AmenityItem(
        id="am_test_1",
        name="Skyline Lounge",
        category="rooftop",
        capacity=30,
        hourly_rate=40.0,
        deposit_amount=100.0,
        opening_hour=10,
        closing_hour=22,
    )
    am_resp = AmenityResponse(amenity=am_item)
    assert am_resp.amenity.id == "am_test_1"

    # ReservationCreateRequest
    res_req = ReservationCreateRequest(
        amenity_id="am_test_1",
        tenant_id="tenant_1",
        unit_id="101",
        start_time="2026-11-15T18:00:00Z",
        end_time="2026-11-15T21:00:00Z",
        attendees_count=12,
    )
    assert res_req.attendees_count == expected_attendees

    # ReservationItem & Response
    res_item = ReservationItem(
        id="res_test_1",
        amenity_id="am_test_1",
        tenant_id="tenant_1",
        unit_id="101",
        start_time="2026-11-15T18:00:00Z",
        end_time="2026-11-15T21:00:00Z",
        total_fee=120.0,
        deposit_paid=100.0,
        amenity_name="Skyline Lounge",
    )
    res_resp = ReservationResponse(reservation=res_item)
    assert res_resp.reservation.id == "res_test_1"

    # AmenityMetricsResponse
    metrics = AmenityMetricsResponse(
        active_amenities_count=5,
        total_reservations=expected_total,
        confirmed_count=8,
        cancelled_count=2,
        total_revenue=expected_revenue,
        amenity_usage_breakdown={"am_test_1": 8},
    )
    assert metrics.total_reservations == expected_total
    assert metrics.total_revenue == expected_revenue



def test_parking_models_validation() -> None:
    """Test validation and serialization of parking and vehicle models."""
    expected_fine = 60.0
    expected_total_spots = 20
    expected_occupancy = 75.0

    # Spot models
    spot_req = ParkingSpotCreateRequest(
        spot_number="P-301",
        zone="Garage Level 3",
        spot_type="assigned_resident",
        unit_id="unit_301",
        status="vacant",
    )
    assert spot_req.spot_number == "P-301"

    spot_item = ParkingSpotItem(
        id="spot_301",
        spot_number="P-301",
        zone="Garage Level 3",
        spot_type="assigned_resident",
        unit_id="unit_301",
        status="vacant",
    )
    spot_resp = ParkingSpotResponse(spot=spot_item)
    assert spot_resp.spot.id == "spot_301"

    spot_list = ParkingSpotListResponse(items=[spot_item], total=1)
    assert len(spot_list.items) == 1

    spot_up = ParkingSpotUpdateRequest(status="maintenance", clear_unit=True)
    assert spot_up.status == "maintenance"
    assert spot_up.clear_unit is True

    # Vehicle models
    veh_req = VehicleRegisterRequest(
        tenant_id="tenant_101",
        unit_id="unit_101",
        license_plate="7ABC123",
        make="Honda",
        model="Civic",
        year=2021,
    )
    assert veh_req.license_plate == "7ABC123"

    veh_item = VehicleItem(
        id="veh_101",
        tenant_id="tenant_101",
        unit_id="unit_101",
        license_plate="7ABC123",
        state_province="CA",
        make="Honda",
        model="Civic",
        year=2021,
    )
    veh_resp = VehicleResponse(vehicle=veh_item)
    assert veh_resp.vehicle.id == "veh_101"

    veh_list = VehicleListResponse(items=[veh_item], total=1)
    assert len(veh_list.items) == 1

    veh_up = VehicleUpdateRequest(color="Red", is_active=False)
    assert veh_up.color == "Red"
    assert veh_up.is_active is False

    # Visitor pass models
    pass_req = VisitorPassCreateRequest(
        unit_id="unit_101",
        tenant_id="tenant_101",
        visitor_name="Jane Doe",
        vehicle_plate="8XYZ987",
        start_time="2026-11-02T10:00:00Z",
        end_time="2026-11-03T10:00:00Z",
    )
    assert pass_req.visitor_name == "Jane Doe"

    pass_item = VisitorPassItem(
        id="vpass_101",
        unit_id="unit_101",
        tenant_id="tenant_101",
        visitor_name="Jane Doe",
        vehicle_plate="8XYZ987",
        pass_code="VP-99881",
        start_time="2026-11-02T10:00:00Z",
        end_time="2026-11-03T10:00:00Z",
        status="active",
    )
    pass_resp = VisitorPassResponse(pass_info=pass_item)
    assert pass_resp.pass_info.pass_code == "VP-99881"

    pass_list = VisitorPassListResponse(items=[pass_item], total=1)
    assert len(pass_list.items) == 1

    pass_up = VisitorPassUpdateRequest(status="expired")
    assert pass_up.status == "expired"

    # Violation models
    viol_req = ParkingViolationCreateRequest(
        spot_id="spot_301",
        license_plate="BADCAR1",
        violation_type="unauthorized_parking",
        fine_amount=expected_fine,
    )
    assert viol_req.fine_amount == expected_fine

    viol_item = ParkingViolationItem(
        id="viol_101",
        spot_id="spot_301",
        license_plate="BADCAR1",
        violation_type="unauthorized_parking",
        fine_amount=expected_fine,
        status="issued",
    )
    viol_resp = ParkingViolationResponse(violation=viol_item)
    assert viol_resp.violation.id == "viol_101"

    viol_list = ParkingViolationListResponse(items=[viol_item], total=1)
    assert len(viol_list.items) == 1

    viol_up = ParkingViolationUpdateRequest(status="paid")
    assert viol_up.status == "paid"

    # Metrics model
    metrics = ParkingMetricsResponse(
        total_spots=expected_total_spots,
        assigned_spots=15,
        vacant_spots=5,
        visitor_spots=4,
        occupancy_rate_pct=expected_occupancy,
        active_vehicles_count=18,
        active_visitor_passes=2,
        open_violations_count=1,
        total_fines_assessed=expected_fine,
    )
    assert metrics.total_spots == expected_total_spots
    assert metrics.occupancy_rate_pct == expected_occupancy


def test_pet_models_validation():
    """Verify serialization, validation, and defaults for Pet Registry models."""
    expected_weight = 42.5
    expected_updated_weight = 44.0
    expected_age = 4
    expected_rent = 35.0
    expected_updated_rent = 40.0
    expected_deposit = 300.0
    expected_fine = 50.0
    expected_active_count = 12
    expected_restricted_count = 2
    expected_revenue = 350.0

    # PetCreateRequest and PetItem
    req = PetCreateRequest(
        tenant_id="tenant_10",
        unit_id="unit_302",
        name="Charlie",
        pet_type="dog",
        breed="Beagle",
        weight_lbs=expected_weight,
        age_years=expected_age,
        is_service_animal=False,
        rabies_tag="RAB-9921",
        vaccination_expires="2027-01-15",
    )
    assert req.name == "Charlie"
    assert req.weight_lbs == expected_weight

    item = PetItem(
        id="pet_101",
        tenant_id="tenant_10",
        unit_id="unit_302",
        name="Charlie",
        pet_type="dog",
        breed="Beagle",
        weight_lbs=expected_weight,
        is_service_animal=False,
        status="active",
    )
    resp = PetResponse(pet=item)
    assert resp.pet.id == "pet_101"

    pet_list = PetListResponse(items=[item], total=1)
    assert len(pet_list.items) == 1

    pet_up = PetUpdateRequest(weight_lbs=expected_updated_weight, status="active")
    assert pet_up.weight_lbs == expected_updated_weight

    # PetPolicy models
    policy_req = PetPolicyCreateRequest(
        property_name="Sunset Gardens",
        pet_type="dog",
        max_weight_lbs=expected_weight,
        monthly_pet_rent=expected_rent,
        one_time_deposit=expected_deposit,
        restricted_breeds=["Pit Bull", "Rottweiler"],
    )
    assert policy_req.monthly_pet_rent == expected_rent
    assert len(policy_req.restricted_breeds) == expected_restricted_count

    policy_item = PetPolicyItem(
        id="policy_01",
        property_name="Sunset Gardens",
        monthly_pet_rent=expected_rent,
        one_time_deposit=expected_deposit,
        restricted_breeds=["Pit Bull"],
    )
    policy_resp = PetPolicyResponse(policy=policy_item)
    assert policy_resp.policy.id == "policy_01"

    policy_list = PetPolicyListResponse(items=[policy_item], total=1)
    assert len(policy_list.items) == 1

    policy_up = PetPolicyUpdateRequest(monthly_pet_rent=expected_updated_rent)
    assert policy_up.monthly_pet_rent == expected_updated_rent

    # PetIncident models
    inc_req = PetIncidentCreateRequest(
        incident_type="noise_barking",
        pet_id="pet_101",
        tenant_id="tenant_10",
        fine_amount=expected_fine,
    )
    assert inc_req.incident_type == "noise_barking"

    inc_item = PetIncidentItem(
        id="inc_01",
        incident_type="noise_barking",
        incident_date="2026-11-01",
        pet_id="pet_101",
        fine_amount=expected_fine,
        status="reported",
    )
    inc_resp = PetIncidentResponse(incident=inc_item)
    assert inc_resp.incident.id == "inc_01"

    inc_list = PetIncidentListResponse(items=[inc_item], total=1)
    assert len(inc_list.items) == 1

    inc_up = PetIncidentUpdateRequest(status="resolved")
    assert inc_up.status == "resolved"

    # SessionRegisterPetRequest
    sess_req = SessionRegisterPetRequest(
        name="Milo",
        pet_type="cat",
        weight_lbs=9.0,
    )
    assert sess_req.name == "Milo"

    # PetMetricsResponse
    metrics = PetMetricsResponse(
        total_active_pets=expected_active_count,
        total_dogs=8,
        total_cats=4,
        monthly_pet_revenue=expected_revenue,
    )
    assert metrics.total_active_pets == expected_active_count
    assert metrics.monthly_pet_revenue == expected_revenue



def test_access_control_models_validation():
    """Verify validation and serialization for access control Pydantic models."""
    expected_fee = 50.0
    expected_total_creds = 42

    # Credential models
    cred_req = AccessCredentialCreateRequest(
        tenant_id="tenant_1",
        unit_id="unit_101",
        credential_type="key_fob",
        credential_number="FOB-8811",
        access_level="all_access",
    )
    assert cred_req.credential_number == "FOB-8811"

    cred_item = AccessCredentialItem(
        id="cred_01",
        tenant_id="tenant_1",
        unit_id="unit_101",
        credential_number="FOB-8811",
        issued_at="2026-11-01T00:00:00",
        replacement_fee=expected_fee,
    )
    cred_resp = AccessCredentialResponse(credential=cred_item)
    assert cred_resp.credential.id == "cred_01"

    cred_list = AccessCredentialListResponse(items=[cred_item], total=1)
    assert len(cred_list.items) == 1

    cred_up = AccessCredentialUpdateRequest(status="suspended")
    assert cred_up.status == "suspended"

    # Guest pass models
    pass_req = GuestPassCreateRequest(
        tenant_id="tenant_1",
        unit_id="unit_101",
        guest_name="Sarah Visitor",
        pass_type="visitor",
        max_uses=2,
    )
    assert pass_req.guest_name == "Sarah Visitor"

    pass_item = GuestPassItem(
        id="pass_01",
        tenant_id="tenant_1",
        unit_id="unit_101",
        guest_name="Sarah Visitor",
        access_code="123456",
        valid_from="2026-11-01T00:00:00",
        valid_until="2026-11-02T00:00:00",
        allowed_zones=["main_lobby", "elevator"],
    )
    pass_resp = GuestPassResponse(guest_pass=pass_item)
    assert pass_resp.guest_pass.access_code == "123456"

    pass_list = GuestPassListResponse(items=[pass_item], total=1)
    assert len(pass_list.items) == 1

    pass_up = GuestPassUpdateRequest(increment_use=True)
    assert pass_up.increment_use is True

    # Intercom directory models
    intercom_req = IntercomDirectoryCreateRequest(
        tenant_id="tenant_1",
        unit_id="unit_101",
        display_name="Smith, J.",
        directory_code="101",
        forwarding_phone="+1-555-0101",
    )
    assert intercom_req.directory_code == "101"

    intercom_item = IntercomDirectoryItem(
        id="dir_01",
        tenant_id="tenant_1",
        unit_id="unit_101",
        display_name="Smith, J.",
        directory_code="101",
        forwarding_phone="+1-555-0101",
    )
    intercom_resp = IntercomDirectoryResponse(entry=intercom_item)
    assert intercom_resp.entry.display_name == "Smith, J."

    intercom_list = IntercomDirectoryListResponse(items=[intercom_item], total=1)
    assert len(intercom_list.items) == 1

    intercom_up = IntercomDirectoryUpdateRequest(buzzer_enabled=False)
    assert intercom_up.buzzer_enabled is False

    # Session actions
    expected_hours = 12
    gen_pass = SessionGenerateGuestPassRequest(
        guest_name="Delivery Courier",
        valid_hours=expected_hours,
    )
    assert gen_pass.valid_hours == expected_hours

    lost_fob = SessionReportLostFobRequest(
        credential_id="cred_01",
        deactivation_reason="Lost on subway",
    )
    assert lost_fob.credential_id == "cred_01"

    # Metrics
    metrics = AccessControlMetricsResponse(
        total_credentials=expected_total_creds,
        active_credentials=38,
        lost_credentials=4,
    )
    assert metrics.total_credentials == expected_total_creds



def test_incident_models_validation():
    """Verify validation and serialization for incident, notice, and appeal schemas."""
    expected_cure_days = 7
    expected_fine = 25.0
    expected_incidents = 10
    expected_fines_total = 150.0

    # 1. Incident schemas
    inc_req = CommunityIncidentCreateRequest(
        incident_type="noise_complaint",
        description="Loud bass vibrating floor after midnight.",
        severity="medium",
        unit_id="unit_101",
        tenant_id="tenant_1",
        reported_by="resident",
        location="Unit 101 Living Room",
    )
    assert inc_req.description == "Loud bass vibrating floor after midnight."

    inc_item = CommunityIncidentItem(
        id="inc_01",
        incident_number="INC-2026-101",
        incident_type="noise_complaint",
        severity="medium",
        status="reported",
        unit_id="unit_101",
        tenant_id="tenant_1",
        reported_by="resident",
        incident_date="2026-11-04T23:15:00Z",
        description="Loud bass vibrating floor after midnight.",
        created_at="2026-11-04T23:20:00Z",
        updated_at="2026-11-04T23:20:00Z",
    )
    inc_resp = CommunityIncidentResponse(incident=inc_item)
    assert inc_resp.incident.incident_number == "INC-2026-101"

    inc_list = CommunityIncidentListResponse(items=[inc_item], total=1)
    assert len(inc_list.items) == 1

    inc_up = CommunityIncidentUpdateRequest(
        status="resolved",
        resolution_notes="Resident complied.",
    )
    assert inc_up.status == "resolved"

    # 2. Notice schemas
    notice_req = ViolationNoticeCreateRequest(
        tenant_id="tenant_1",
        unit_id="unit_101",
        violation_type="noise_complaint",
        notice_type="courtesy_warning",
        remedy_instructions="Keep music below 55 dB after 10 PM quiet hours.",
        cure_days=expected_cure_days,
        fine_amount=0.0,
    )
    assert notice_req.cure_days == expected_cure_days

    notice_item = ViolationNoticeItem(
        id="viol_01",
        notice_number="VN-2026-089",
        tenant_id="tenant_1",
        unit_id="unit_101",
        violation_type="noise_complaint",
        notice_type="courtesy_warning",
        status="issued",
        issued_at="2026-11-05T09:00:00Z",
        remedy_instructions="Keep music below 55 dB after 10 PM quiet hours.",
        created_at="2026-11-05T09:00:00Z",
        updated_at="2026-11-05T09:00:00Z",
    )
    notice_resp = ViolationNoticeResponse(notice=notice_item)
    assert notice_resp.notice.notice_number == "VN-2026-089"

    notice_list = ViolationNoticeListResponse(items=[notice_item], total=1)
    assert len(notice_list.items) == 1

    notice_up = ViolationNoticeUpdateRequest(status="cured", fine_amount=expected_fine)
    assert notice_up.status == "cured"
    assert notice_up.fine_amount == expected_fine

    # 3. Appeal schemas
    appeal_req = ViolationAppealCreateRequest(
        notice_id="viol_01",
        tenant_id="tenant_1",
        unit_id="unit_101",
        reason="Music was from neighboring apartment on adjacent terrace.",
    )
    assert appeal_req.notice_id == "viol_01"

    appeal_item = ViolationAppealItem(
        id="appeal_01",
        appeal_number="APL-2026-042",
        notice_id="viol_01",
        tenant_id="tenant_1",
        unit_id="unit_101",
        status="submitted",
        reason="Music was from neighboring apartment on adjacent terrace.",
        submitted_at="2026-11-05T14:30:00Z",
        created_at="2026-11-05T14:30:00Z",
        updated_at="2026-11-05T14:30:00Z",
    )
    appeal_resp = ViolationAppealResponse(appeal=appeal_item)
    assert appeal_resp.appeal.appeal_number == "APL-2026-042"

    appeal_list = ViolationAppealListResponse(items=[appeal_item], total=1)
    assert len(appeal_list.items) == 1

    appeal_up = ViolationAppealUpdateRequest(
        status="waived",
        reviewed_by="Manager Sarah",
        decision_notes="Confirmed sound came from unit 102.",
    )
    assert appeal_up.status == "waived"

    # 4. Session actions
    sess_notice = SessionIssueViolationNoticeRequest(
        violation_type="trash_disposal",
        notice_type="courtesy_warning",
        remedy_instructions="Place all recycling in designated bins.",
    )
    assert sess_notice.violation_type == "trash_disposal"

    sess_appeal = SessionSubmitViolationAppealRequest(
        notice_id="viol_01",
        reason="Boxes were left by delivery carrier, not resident.",
    )
    assert sess_appeal.notice_id == "viol_01"

    # 5. Metrics response
    metrics = IncidentMetricsResponse(
        total_incidents=expected_incidents,
        active_incidents=2,
        total_violations=5,
        open_violations=3,
        total_fines_assessed=expected_fines_total,
    )
    assert metrics.total_incidents == expected_incidents
    assert metrics.total_fines_assessed == expected_fines_total



def test_announcement_models_validation():
    """Verify validation and serialization of announcement and concierge Pydantic models."""
    expected_announcements = 3
    expected_alerts = 1

    # 1. Announcement create & item
    create_req = CommunityAnnouncementCreateRequest(
        title="Main Boiler Maintenance",
        content="Hot water will be suspended between 9 AM and 1 PM tomorrow.",
        category="maintenance_advisory",
        priority="urgent",
        scope="building",
        target_building="North Tower",
        require_acknowledgment=True,
    )
    assert create_req.title == "Main Boiler Maintenance"
    assert create_req.require_acknowledgment is True

    ann_item = CommunityAnnouncementItem(
        id="ann_test_01",
        announcement_number="ANN-2026-999",
        title=create_req.title,
        content=create_req.content,
        category=create_req.category,
        priority=create_req.priority,
        scope=create_req.scope,
        target_building=create_req.target_building,
        require_acknowledgment=True,
        published_at="2026-11-20T10:00:00Z",
        created_at="2026-11-20T10:00:00Z",
        updated_at="2026-11-20T10:00:00Z",
    )
    ann_resp = CommunityAnnouncementResponse(announcement=ann_item)
    assert ann_resp.announcement.announcement_number == "ANN-2026-999"

    ann_list = CommunityAnnouncementListResponse(items=[ann_item], total=1)
    assert ann_list.total == 1

    ann_update = CommunityAnnouncementUpdateRequest(
        title="Main Boiler Maintenance (Completed)",
        status="archived",
    )
    assert ann_update.status == "archived"

    # 2. Acknowledgment models
    ack_req = AnnouncementAcknowledgeRequest(
        tenant_id="tenant_3",
        unit_id="unit_PH1",
        channel="chat_session",
        notes="Confirmed",
    )
    assert ack_req.tenant_id == "tenant_3"

    ack_item = AnnouncementAcknowledgmentItem(
        id="ack_test_01",
        announcement_id="ann_test_01",
        tenant_id="tenant_3",
        unit_id="unit_PH1",
        acknowledged_at="2026-11-20T11:00:00Z",
    )
    ack_resp = AnnouncementAcknowledgmentResponse(acknowledgment=ack_item)
    assert ack_resp.acknowledgment.announcement_id == "ann_test_01"

    ack_list = AnnouncementAcknowledgmentListResponse(items=[ack_item], total=1)
    assert ack_list.total == 1

    # 3. Concierge request models
    con_req = ConciergeRequestCreateRequest(
        tenant_id="tenant_3",
        unit_id="unit_PH1",
        request_type="dry_cleaning",
        priority="normal",
        instructions="Pickup garment bag from door hook at 10 AM.",
        preferred_date="2026-11-21",
    )
    assert con_req.request_type == "dry_cleaning"

    con_item = ConciergeRequestItem(
        id="con_test_01",
        request_number="CON-2026-088",
        tenant_id=con_req.tenant_id,
        unit_id=con_req.unit_id,
        request_type=con_req.request_type,
        instructions=con_req.instructions,
        status="submitted",
        created_at="2026-11-20T10:00:00Z",
        updated_at="2026-11-20T10:00:00Z",
    )
    con_resp = ConciergeRequestResponse(concierge_request=con_item)
    assert con_resp.concierge_request.request_number == "CON-2026-088"

    con_update = ConciergeRequestUpdateRequest(
        status="fulfilled",
        assigned_staff="Concierge James",
        fulfillment_notes="Garments delivered back to unit closet.",
    )
    assert con_update.status == "fulfilled"

    # 4. Session actions
    sess_ack = SessionAcknowledgeAlertRequest(
        announcement_id="ann_test_01",
        notes="Awaiting update",
    )
    assert sess_ack.announcement_id == "ann_test_01"

    sess_con = SessionCreateConciergeRequest(
        request_type="package_hold",
        instructions="Hold parcel in storage until Friday evening.",
    )
    assert sess_con.request_type == "package_hold"

    # 5. Metrics response
    metrics = AnnouncementsMetricsResponse(
        total_announcements=expected_announcements,
        published_announcements=2,
        active_emergency_alerts=expected_alerts,
        total_acknowledgments=1,
        total_concierge_requests=1,
    )
    assert metrics.total_announcements == expected_announcements
    assert metrics.active_emergency_alerts == expected_alerts



def test_move_logistics_models():
    """Test Pydantic model schemas for move logistics and elevator bookings."""
    expected_moves = 5
    expected_cois = 2

    chk = MoveChecklistItem(id="coi", label="COI Submission", completed=True)
    assert chk.id == "coi"
    assert chk.completed is True

    move_item = MoveLogisticsItem(
        id="move_test_1",
        move_number="MOV-IN-2026-TEST1",
        tenant_id="tenant_3",
        unit_id="unit_PH1",
        scheduled_date="2026-11-20",
        moving_company="Apex Movers",
        checklist_items=[chk],
        created_at="2026-11-12T00:00:00Z",
        updated_at="2026-11-12T00:00:00Z",
    )
    assert move_item.move_number == "MOV-IN-2026-TEST1"
    assert len(move_item.checklist_items) == 1

    resp = MoveLogisticsResponse(move_event=move_item)
    assert resp.move_event.id == "move_test_1"

    list_resp = MoveLogisticsListResponse(items=[move_item], total=1)
    assert list_resp.total == 1

    create_req = MoveLogisticsCreateRequest(
        tenant_id="tenant_1",
        unit_id="unit_101",
        move_type="move_out",
        scheduled_date="2026-12-05",
        moving_company="Quick Mover",
    )
    assert create_req.move_type == "move_out"

    update_req = MoveLogisticsUpdateRequest(status="completed", coi_status="verified")
    assert update_req.status == "completed"

    toggle_req = MoveChecklistToggleRequest(item_id="coi", completed=True)
    assert toggle_req.item_id == "coi"

    booking_item = FreightElevatorBookingItem(
        id="elv_test_1",
        booking_number="ELV-2026-TEST1",
        tenant_id="tenant_3",
        unit_id="unit_PH1",
        booking_date="2026-11-20",
        time_slot="08:00-12:00",
        created_at="2026-11-12T00:00:00Z",
        updated_at="2026-11-12T00:00:00Z",
    )
    assert booking_item.time_slot == "08:00-12:00"

    book_create = FreightElevatorBookingCreateRequest(
        tenant_id="tenant_1",
        unit_id="unit_101",
        booking_date="2026-11-25",
        time_slot="12:00-16:00",
    )
    assert book_create.booking_date == "2026-11-25"

    book_resp = FreightElevatorBookingResponse(booking=booking_item)
    assert book_resp.booking.id == "elv_test_1"

    book_list = FreightElevatorBookingListResponse(items=[booking_item], total=1)
    assert book_list.total == 1

    sess_move = SessionScheduleMoveRequest(move_type="move_in", scheduled_date="2026-11-20")
    assert sess_move.move_type == "move_in"

    sess_elv = SessionReserveElevatorRequest(booking_date="2026-11-20", time_slot="08:00-12:00")
    assert sess_elv.time_slot == "08:00-12:00"

    metrics = MoveLogisticsMetricsResponse(
        total_moves=expected_moves, scheduled_moves=3, pending_cois=expected_cois
    )
    assert metrics.total_moves == expected_moves
    assert metrics.pending_cois == expected_cois
