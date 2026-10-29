import hashlib
import json
import logging
import os
import tempfile
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from api import (
    assignment,
    business_hours,
    csat,
    db_utils,
    inspections,
    knowledge_base,
    lease_renewals,
    macro_suggestions,
    macros,
    packages,
    sla,
    tenant_context,
    vendors,
    webhooks,
)
from api.chroma_utils import (
    ChunkingOptions,
    ChunkingStrategy,
    delete_collection_from_chroma,
    delete_doc_from_chroma,
    get_collection_chunk_analytics,
    get_collection_chunk_count,
    get_doc_chunks_from_chroma,
    index_document_to_chroma,
    load_document_source,
    rechunk_collection_in_chroma,
    reindex_chunks_in_chroma,
    rename_collection_in_chroma,
    select_retriever,
)
from api.collections import DEFAULT_COLLECTION, normalize_collection
from api.db_utils import (
    VALID_SESSION_STATUSES,
    create_macro,
    create_sla_policy,
    create_support_agent,
    create_webhook,
    delete_document_record,
    delete_document_source,
    delete_document_sources_by_collection,
    delete_documents_by_collection,
    delete_macro,
    delete_session,
    delete_sessions,
    delete_sla_policy,
    delete_support_agent,
    delete_webhook,
    get_agent_performance_analytics,
    get_all_collections,
    get_all_documents,
    get_all_sessions,
    get_chat_history,
    get_collections_details,
    get_document_by_hash,
    get_document_record,
    get_document_source,
    get_feedback_analytics,
    get_feedback_by_id,
    get_library_stats,
    get_macro,
    get_macro_by_shortcut,
    get_session_assignment_history,
    get_session_feedback,
    get_session_latest_user_query,
    get_session_metadata,
    get_sla_policy,
    get_support_agent,
    get_support_triage_analytics,
    get_webhook,
    get_webhook_delivery_logs,
    insert_application_logs,
    insert_document_record,
    insert_feedback,
    list_feedback,
    list_feedback_review_queue,
    list_macro_categories,
    list_macros,
    list_sla_policies,
    list_support_agents,
    list_webhooks,
    normalize_session_label,
    ping_db,
    prune_sessions_before,
    rename_collection,
    rename_session,
    save_document_source,
    search_sessions,
    submit_csat_feedback,
    truncate_history,
    update_feedback_review,
    update_macro,
    update_session_metadata,
    update_sla_policy,
    update_support_agent,
    update_webhook,
)
from api.observability import (
    estimate_tokens,
    increment,
    record_latency,
    render_prometheus,
    snapshot,
)
from api.pii import redact_pii
from api.presenters import (
    build_search_hits,
    build_sources,
    render_session_csv,
    render_session_json,
    render_session_markdown,
)
from api.pydantic_models import (
    AgentPerformanceScorecardsResponse,
    AgentScorecardItem,
    AgentWorkloadResponse,
    AutoAssignRequest,
    BillingMetricsResponse,
    BillingTransactionCreateRequest,
    BillingTransactionItem,
    BillingTransactionListResponse,
    BillingTransactionResponse,
    BillingTransactionUpdateRequest,
    BulkDeleteFileRequest,
    BulkDeleteFileResult,
    BulkDeleteResponse,
    BulkDeleteSessionRequest,
    BulkDeleteSessionResponse,
    BulkDeleteSessionResult,
    BulkUploadItem,
    BulkUploadResponse,
    BusinessHoursStatusResponse,
    ChatMessage,
    CollectionAnalyticsResponse,
    CollectionDetailResponse,
    CollectionRechunkRequest,
    CollectionRechunkResponse,
    ConfigResponse,
    CSATFeedbackSubmitRequest,
    CSATSummaryResponse,
    DeleteDocumentResponse,
    DeleteFileRequest,
    DeleteSessionResponse,
    DocumentChunkInfo,
    DocumentDetailResponse,
    DocumentInfo,
    DocumentRechunkItem,
    FeedbackAnalyticsResponse,
    FeedbackInput,
    FeedbackItem,
    FeedbackListResponse,
    FeedbackResponse,
    FeedbackReviewItemResponse,
    FeedbackReviewQueueResponse,
    FeedbackReviewUpdateRequest,
    HealthResponse,
    InspectionCompleteRequest,
    InspectionCreateRequest,
    InspectionDocumentPublishRequest,
    InspectionDocumentPublishResponse,
    InspectionListResponse,
    InspectionMetricsResponse,
    InspectionRecord,
    InspectionResponse,
    InspectionUpdateRequest,
    InspectionWorkOrderConversionRequest,
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
    PackageCreateRequest,
    PackageItem,
    PackageListResponse,
    PackageMetricsResponse,
    PackagePickupRequest,
    PackageResponse,
    PackageUpdateRequest,
    PruneSessionsResponse,
    QueryInput,
    QueryResponse,
    QuotaInfo,
    RechunkDocumentRequest,
    RenameCollectionRequest,
    RenameCollectionResponse,
    SearchInput,
    SearchResponse,
    SessionAssignmentHistoryResponse,
    SessionAssignmentRecord,
    SessionAssignmentRequest,
    SessionDraftArticleRequest,
    SessionInfo,
    SessionInspectionCreateRequest,
    SessionIntakePackageRequest,
    SessionMacroSuggestionsResponse,
    SessionSearchResponse,
    SessionSearchResult,
    SessionSLAStatusResponse,
    SessionSummaryRequest,
    SessionSummaryResponse,
    SessionTenantContextResponse,
    SessionTenantLinkRequest,
    SLAAlertEvaluateRequest,
    SLAAlertEvaluateResponse,
    SLAAlertItem,
    SLAComplianceAnalyticsResponse,
    SLAPoliciesListResponse,
    SLAPolicyCreateRequest,
    SLAPolicyResponse,
    SLAPolicyUpdateRequest,
    StatsResponse,
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
    UploadDocumentResponse,
    VendorCreateRequest,
    VendorDispatchCompleteRequest,
    VendorDispatchItem,
    VendorDispatchListResponse,
    VendorDispatchRequest,
    VendorDispatchResponse,
    VendorItem,
    VendorListResponse,
    VendorMetricsResponse,
    VendorResponse,
    VendorUpdateRequest,
    WebhookCreateRequest,
    WebhookDeliveryLogItem,
    WebhookDeliveryLogsResponse,
    WebhookPingResponse,
    WebhookResponse,
    WebhookUpdateRequest,
    WorkOrderCreateRequest,
    WorkOrderFromSessionRequest,
    WorkOrderItem,
    WorkOrderListResponse,
    WorkOrderMetricsResponse,
    WorkOrderResponse,
    WorkOrderUpdateRequest,
)
from api.security import (
    WINDOW_SECONDS,
    check_api_key,
    check_rate_limit,
    check_token_quota,
    get_token_usage,
    is_public_path,
    record_token_usage,
)
from api.settings import settings
from api.summarization import summarize_dialogue


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def build_log_formatter() -> logging.Formatter:
    if settings.log_format == "json":
        return JsonLogFormatter()
    return logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")


def configure_logging() -> None:
    level = getattr(logging, settings.log_level, logging.INFO)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(logging.StreamHandler())
    if settings.log_path:
        root.addHandler(logging.FileHandler(settings.log_path))
    root.setLevel(level)
    for handler in root.handlers:
        handler.setFormatter(build_log_formatter())


configure_logging()
logger = logging.getLogger(__name__)
app = FastAPI(
    title=settings.app_name,
    description="Document-grounded customer support assistant API.",
    version=settings.app_version,
)

vendors.create_vendors()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".html", ".md", ".txt", ".csv"}


def _latency_group(path: str) -> str:
    if path == "/chat":
        return "chat"
    if path == "/chat/stream":
        return "stream"
    if path == "/search":
        return "search"
    if path in {"/upload-doc", "/upload-docs"}:
        return "upload"
    return "other"


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    if not is_public_path(request.url.path):
        if not check_api_key(request.headers.get("X-API-Key"), settings.api_key):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key."},
                headers={"X-Request-ID": request_id},
            )
        client_ip = request.client.host if request.client else "unknown"
        if not check_rate_limit(client_ip, settings.rate_limit_per_min):
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
                headers={
                    "X-Request-ID": request_id,
                    "Retry-After": str(int(WINDOW_SECONDS)),
                },
            )
    started = time.perf_counter()
    response = await call_next(request)
    record_latency(_latency_group(request.url.path), time.perf_counter() - started)
    response.headers["X-Request-ID"] = request_id
    return response


def sanitize_filename(filename: str) -> str:
    cleaned = filename.replace("\\", "/")
    return Path(cleaned).name.replace("\x00", "").strip()


MIN_CHUNK_SIZE = 100
MAX_CHUNK_SIZE = 4000


def validate_chunk_params(chunk_size: int, chunk_overlap: int) -> None:
    if not MIN_CHUNK_SIZE <= chunk_size <= MAX_CHUNK_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"chunk_size must be between {MIN_CHUNK_SIZE} and {MAX_CHUNK_SIZE}.",
        )
    if not 0 <= chunk_overlap < chunk_size:
        raise HTTPException(
            status_code=400,
            detail="chunk_overlap must be >= 0 and smaller than chunk_size.",
        )


def validate_upload_size(size_bytes: int) -> None:
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.max_upload_mb} MB upload limit.",
        )


def stage_upload_file(file_obj, suffix: str) -> tuple[str, str]:
    """Stream an upload to a temp file, returning (path, sha256 hex digest)."""
    digest = hashlib.sha256()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as buffer:
        while chunk := file_obj.read(1024 * 1024):
            digest.update(chunk)
            buffer.write(chunk)
        return buffer.name, digest.hexdigest()


def get_rag_chain_for_model(  # noqa: PLR0913, PLR0917 - explicit retrieval options
    model: str,
    file_ids: list[int] | None = None,
    source_filename: str | None = None,
    use_hybrid: bool | None = None,
    collections: list[str] | None = None,
    expand_query: bool | None = None,
    rerank: bool | None = None,
    use_cross_encoder_rerank: bool | None = None,
    cross_encoder_model: str | None = None,
):
    # ruff: noqa: PLC0415 - lazy import required for Python 3.14 compatibility
    from api.langchain_utils import get_rag_chain

    return get_rag_chain(
        model,
        file_ids=file_ids,
        source_filename=source_filename,
        use_hybrid=use_hybrid,
        collections=collections,
        expand_query=expand_query,
        rerank=rerank,
        use_cross_encoder_rerank=use_cross_encoder_rerank,
        cross_encoder_model=cross_encoder_model,
    )


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", app=settings.app_name, version=settings.app_version)


@app.get("/config", response_model=ConfigResponse)
def get_runtime_config():
    return ConfigResponse(
        app_name=settings.app_name,
        app_version=settings.app_version,
        default_model=settings.default_model,
        retriever_k=settings.retriever_k,
        max_history_turns=settings.max_history_turns,
        max_upload_mb=settings.max_upload_mb,
        max_bulk_files=settings.max_bulk_files,
        use_hybrid_retriever=settings.use_hybrid_retriever,
        use_query_expansion=settings.use_query_expansion,
        use_rerank=settings.use_rerank,
        api_key_required=bool(settings.api_key),
        rate_limit_per_min=settings.rate_limit_per_min,
        token_budget_configured=settings.token_daily_budget_est > 0,
    )


@app.get("/health/live")
def health_live():
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready():
    checks: dict[str, str] = {}
    try:
        ping_db()
        checks["sqlite"] = "ok"
    except Exception as exc:
        checks["sqlite"] = f"error: {exc}"
    try:
        os.makedirs(settings.chroma_persist_dir, exist_ok=True)
        checks["chroma_dir"] = "ok"
    except Exception as exc:
        checks["chroma_dir"] = f"error: {exc}"
    ready = all(value == "ok" for value in checks.values())
    status_code = 200 if ready else 503
    return JSONResponse(status_code=status_code, content={"ready": ready, "checks": checks})


@app.get("/metrics")
def metrics():
    return PlainTextResponse(render_prometheus(), media_type="text/plain")


@app.get("/stats", response_model=StatsResponse)
def stats():
    return StatsResponse(**get_library_stats())


@app.get("/metrics.json")
def metrics_json():
    return snapshot()


@app.get("/quota", response_model=QuotaInfo)
def quota(request: Request):
    budget = settings.token_daily_budget_est
    if budget <= 0:
        return QuotaInfo(budget=0, used=0, remaining=None, unlimited=True)
    used = get_token_usage(_client_ip(request))
    return QuotaInfo(budget=budget, used=used, remaining=max(0, budget - used), unlimited=False)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _enforce_token_quota(client_ip: str, tokens: int) -> None:
    if not check_token_quota(client_ip, tokens, settings.token_daily_budget_est):
        raise HTTPException(
            status_code=429, detail="Daily token budget exceeded. Try again tomorrow."
        )


@app.post("/chat", response_model=QueryResponse)
def chat(query_input: QueryInput, request: Request):
    increment("chat_requests")
    client_ip = _client_ip(request)
    question_tokens = estimate_tokens(query_input.question)
    _enforce_token_quota(client_ip, question_tokens)
    session_id = query_input.session_id
    logger.info(
        "Session ID: %s, User Query: %s, Model: %s",
        session_id,
        redact_pii(query_input.question),
        query_input.model.value,
    )
    if not session_id:
        session_id = str(uuid.uuid4())

    chat_history = truncate_history(get_chat_history(session_id), settings.max_history_turns)
    rag_chain = get_rag_chain_for_model(
        query_input.model.value,
        file_ids=query_input.file_ids,
        source_filename=query_input.source_filename,
        use_hybrid=query_input.use_hybrid,
        collections=query_input.collections,
        expand_query=query_input.expand_query,
        rerank=query_input.rerank,
        use_cross_encoder_rerank=query_input.use_cross_encoder_rerank,
        cross_encoder_model=query_input.cross_encoder_model,
    )
    grounded_input = tenant_context.inject_tenant_context_into_prompt(
        query_input.question, session_id=session_id
    )
    try:
        result = rag_chain.invoke({"input": grounded_input, "chat_history": chat_history})
    except Exception as exc:
        increment("chat_errors")
        logger.exception("RAG chain failed for session_id %s", session_id)
        raise HTTPException(
            status_code=502, detail="Failed to generate a response from the retrieval pipeline."
        ) from exc

    answer: str | None
    if isinstance(result, str):
        answer = result
    elif isinstance(result, dict):
        answer = result.get("answer") if isinstance(result.get("answer"), str) else None
    else:
        answer = None
    if not isinstance(answer, str):
        increment("chat_errors")
        logger.error("RAG chain returned an invalid response for session_id %s", session_id)
        raise HTTPException(
            status_code=502, detail="The retrieval pipeline returned an invalid response."
        )

    sources = build_sources(result.get("context") if isinstance(result, dict) else [])

    insert_application_logs(session_id, query_input.question, answer, query_input.model.value)
    answer_tokens = estimate_tokens(answer)
    increment("prompt_tokens_est", question_tokens)
    increment("completion_tokens_est", answer_tokens)
    record_token_usage(client_ip, question_tokens + answer_tokens)
    logger.info("Session ID: %s, AI Response: %s", session_id, redact_pii(answer))
    return QueryResponse(
        answer=answer, session_id=session_id, model=query_input.model, sources=sources
    )


@app.post("/search", response_model=SearchResponse)
def search(search_input: SearchInput, request: Request):
    increment("search_requests")
    client_ip = _client_ip(request)
    question_tokens = estimate_tokens(search_input.question)
    _enforce_token_quota(client_ip, question_tokens)
    use_hybrid = search_input.use_hybrid
    if use_hybrid is None:
        use_hybrid = settings.use_hybrid_retriever
    expand = search_input.expand_query
    if expand is None:
        expand = settings.use_query_expansion
    rerank = search_input.rerank
    if rerank is None:
        rerank = settings.use_rerank
    use_cross_encoder = search_input.use_cross_encoder_rerank
    if use_cross_encoder is None:
        use_cross_encoder = settings.use_cross_encoder_rerank
    cross_encoder_model = search_input.cross_encoder_model
    if cross_encoder_model is None:
        cross_encoder_model = settings.cross_encoder_model
    retriever = select_retriever(
        k=search_input.k,
        file_ids=search_input.file_ids,
        source_filename=search_input.source_filename,
        use_hybrid=use_hybrid,
        bm25_weight=settings.hybrid_bm25_weight,
        vector_weight=settings.hybrid_vector_weight,
        collections=search_input.collections,
        expand_query=expand,
        llm=None,
        expansion_count=settings.expansion_count,
        rerank=rerank,
        use_cross_encoder_rerank=use_cross_encoder,
        cross_encoder_model=cross_encoder_model,
    )
    try:
        documents = retriever.invoke(search_input.question)
    except Exception as exc:
        logger.exception("Retrieval failed for search")
        raise HTTPException(
            status_code=502, detail="Failed to retrieve documents for the query."
        ) from exc
    increment("prompt_tokens_est", question_tokens)
    hits = build_search_hits(documents, score_threshold=search_input.score_threshold)
    return SearchResponse(hits=hits)


async def _stream_rag_response(
    query_input: QueryInput, chat_history: list, session_id: str
) -> AsyncGenerator[str, None]:
    """Stream RAG chain response as SSE events."""
    rag_chain = get_rag_chain_for_model(
        query_input.model.value,
        file_ids=query_input.file_ids,
        source_filename=query_input.source_filename,
        use_hybrid=query_input.use_hybrid,
        collections=query_input.collections,
        expand_query=query_input.expand_query,
        rerank=query_input.rerank,
        use_cross_encoder_rerank=query_input.use_cross_encoder_rerank,
        cross_encoder_model=query_input.cross_encoder_model,
    )
    grounded_input = tenant_context.inject_tenant_context_into_prompt(
        query_input.question, session_id=session_id
    )
    try:
        async for chunk in rag_chain.astream(
            {"input": grounded_input, "chat_history": chat_history}
        ):
            if isinstance(chunk, dict):
                if "answer" in chunk:
                    yield f"data: {chunk['answer']}\n\n"
                elif "context" in chunk:
                    sources = build_sources(chunk["context"])
                    if sources:
                        source_data = json.dumps([s.model_dump() for s in sources])
                        yield f"event: sources\ndata: {source_data}\n\n"
            elif isinstance(chunk, str):
                yield f"data: {chunk}\n\n"
    except Exception:
        logger.exception("RAG chain streaming failed for session_id %s", session_id)
        yield "event: error\ndata: Failed to generate response\n\n"


@app.post("/chat/stream")
async def chat_stream(query_input: QueryInput, request: Request):
    increment("stream_requests")
    client_ip = _client_ip(request)
    question_tokens = estimate_tokens(query_input.question)
    _enforce_token_quota(client_ip, question_tokens)
    session_id = query_input.session_id
    logger.info(
        "Stream Session ID: %s, User Query: %s, Model: %s",
        session_id,
        redact_pii(query_input.question),
        query_input.model.value,
    )
    if not session_id:
        session_id = str(uuid.uuid4())

    chat_history = truncate_history(get_chat_history(session_id), settings.max_history_turns)

    async def event_generator():
        full_answer = ""
        async for event in _stream_rag_response(query_input, chat_history, session_id):
            if event.startswith("data: "):
                full_answer += event[6:].strip()
            yield event

        # Log the complete interaction
        if full_answer:
            insert_application_logs(
                session_id, query_input.question, full_answer, query_input.model.value
            )
            answer_tokens = estimate_tokens(full_answer)
            increment("prompt_tokens_est", question_tokens)
            increment("completion_tokens_est", answer_tokens)
            record_token_usage(client_ip, question_tokens + answer_tokens)
            logger.info(
                "Stream Session ID: %s, AI Response: %s", session_id, redact_pii(full_answer)
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


FILE_REQUIRED = File(...)
FILES_REQUIRED = File(...)


def ingest_single_file(
    file: UploadFile,
    chunking_strategy: ChunkingStrategy,
    chunk_size: int,
    chunk_overlap: int,
    collection: str,
) -> UploadDocumentResponse:
    """Validate, stage, dedupe, and index one upload (raises HTTPException)."""
    safe_filename = sanitize_filename(file.filename or "")
    file_extension = os.path.splitext(safe_filename)[1].lower()

    if not safe_filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")

    if file_extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(
            status_code=400, detail=f"Unsupported file type. Allowed types are: {allowed}"
        )

    validate_chunk_params(chunk_size, chunk_overlap)
    collection_name = _normalize_collection_param(collection)

    options = ChunkingOptions(
        strategy=chunking_strategy, chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )

    temp_file_path = None

    try:
        temp_file_path, content_hash = stage_upload_file(file.file, file_extension)

        if os.path.getsize(temp_file_path) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file cannot be empty.")
        validate_upload_size(os.path.getsize(temp_file_path))

        duplicate = get_document_by_hash(content_hash)
        if duplicate is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Identical content already indexed as '{duplicate['filename']}' "
                    f"(file_id {duplicate['id']})."
                ),
            )

        file_id = insert_document_record(safe_filename, collection_name, content_hash)
        try:
            source_text = load_document_source(temp_file_path)
            save_document_source(
                file_id,
                source_text,
                chunking_strategy.value,
                chunk_size,
                chunk_overlap,
            )
        except Exception:
            logger.exception(
                "Failed to store source text for %s; re-chunking will be unavailable",
                safe_filename,
            )
        success = index_document_to_chroma(
            temp_file_path,
            file_id,
            safe_filename,
            options=options,
            collection=collection_name,
        )

        if success:
            increment("uploads")
            return UploadDocumentResponse(
                message=f"File {safe_filename} has been successfully uploaded and indexed.",
                file_id=file_id,
            )

        increment("upload_errors")
        if not delete_document_record(file_id):
            logger.warning(
                "Failed to remove document metadata after indexing failed for file_id %s", file_id
            )
        delete_document_source(file_id)
        raise HTTPException(status_code=500, detail=f"Failed to index {safe_filename}.")
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)


@app.post("/upload-doc", response_model=UploadDocumentResponse)
def upload_and_index_document(
    file: UploadFile = FILE_REQUIRED,
    chunking_strategy: ChunkingStrategy = ChunkingStrategy.RECURSIVE,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    collection: str = DEFAULT_COLLECTION,
):
    return ingest_single_file(file, chunking_strategy, chunk_size, chunk_overlap, collection)


@app.post("/upload-docs", response_model=BulkUploadResponse)
def upload_many_documents(
    files: list[UploadFile] = FILES_REQUIRED,
    chunking_strategy: ChunkingStrategy = ChunkingStrategy.RECURSIVE,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    collection: str = DEFAULT_COLLECTION,
):
    if not files:
        raise HTTPException(status_code=400, detail="At least one file must be uploaded.")
    if len(files) > settings.max_bulk_files:
        raise HTTPException(
            status_code=400,
            detail=f"At most {settings.max_bulk_files} files can be uploaded at once.",
        )

    results = []
    for file in files:
        filename = file.filename or "unnamed"
        try:
            response = ingest_single_file(
                file, chunking_strategy, chunk_size, chunk_overlap, collection
            )
            results.append(
                BulkUploadItem(filename=filename, status="indexed", file_id=response.file_id)
            )
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            results.append(BulkUploadItem(filename=filename, status="error", detail=detail))
        except Exception:
            logger.exception("Unexpected error while bulk-uploading %s", filename)
            results.append(
                BulkUploadItem(filename=filename, status="error", detail="Unexpected error.")
            )

    uploaded = sum(1 for item in results if item.status == "indexed")
    return BulkUploadResponse(results=results, uploaded=uploaded, failed=len(results) - uploaded)


@app.get("/list-docs", response_model=list[DocumentInfo])
def list_documents(collection: str | None = None):
    if collection is None:
        return get_all_documents()
    return get_all_documents(_normalize_collection_param(collection))


@app.get("/docs/{file_id}", response_model=DocumentDetailResponse)
def get_document_details(file_id: int):
    record = get_document_record(file_id)
    if record is None:
        raise HTTPException(
            status_code=404, detail=f"Document with file_id {file_id} was not found."
        )
    raw_chunks = get_doc_chunks_from_chroma(file_id)
    chunks = [DocumentChunkInfo(**chunk) for chunk in raw_chunks]
    source_record = get_document_source(file_id)
    return DocumentDetailResponse(
        id=record["id"],
        filename=record["filename"],
        collection=record.get("collection", DEFAULT_COLLECTION),
        sha256=record.get("sha256"),
        upload_timestamp=record.get("upload_timestamp"),
        chunk_count=len(chunks),
        chunks=chunks,
        chunking_strategy=source_record.get("strategy") if source_record else None,
        chunk_size=source_record.get("chunk_size") if source_record else None,
        chunk_overlap=source_record.get("chunk_overlap") if source_record else None,
    )


@app.post("/docs/{file_id}/rechunk", response_model=DocumentDetailResponse)
def rechunk_document_route(
    file_id: int,
    request: RechunkDocumentRequest | None = None,
):
    record = get_document_record(file_id)
    if record is None:
        raise HTTPException(
            status_code=404, detail=f"Document with file_id {file_id} was not found."
        )

    req = request or RechunkDocumentRequest()
    validate_chunk_params(req.chunk_size, req.chunk_overlap)

    source_record = get_document_source(file_id)
    if source_record is None or not source_record.get("source_text"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Source text for document with file_id {file_id} is not available for re-chunking."
            ),
        )

    options = ChunkingOptions(
        strategy=req.chunking_strategy,
        chunk_size=req.chunk_size,
        chunk_overlap=req.chunk_overlap,
    )

    filename = record.get("filename", f"doc_{file_id}")
    collection = record.get("collection", DEFAULT_COLLECTION)
    source_text = source_record["source_text"]

    success = reindex_chunks_in_chroma(
        file_id=file_id,
        source_text=source_text,
        filename=filename,
        collection=collection,
        options=options,
    )
    if not success:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to re-chunk document '{filename}'.",
        )

    save_document_source(
        file_id=file_id,
        source_text=source_text,
        strategy=req.chunking_strategy.value,
        chunk_size=req.chunk_size,
        chunk_overlap=req.chunk_overlap,
    )

    raw_chunks = get_doc_chunks_from_chroma(file_id)
    chunks = [DocumentChunkInfo(**chunk) for chunk in raw_chunks]

    return DocumentDetailResponse(
        id=record["id"],
        filename=filename,
        collection=collection,
        sha256=record.get("sha256"),
        upload_timestamp=record.get("upload_timestamp"),
        chunk_count=len(chunks),
        chunks=chunks,
        chunking_strategy=req.chunking_strategy.value,
        chunk_size=req.chunk_size,
        chunk_overlap=req.chunk_overlap,
    )


@app.get("/collections", response_model=list[str])
def list_collections():
    return get_all_collections()


@app.get("/collections/details", response_model=list[CollectionDetailResponse])
def get_collections_details_route():
    details = get_collections_details()
    results = []
    for item in details:
        col = item["collection"]
        chunk_count = get_collection_chunk_count(col)
        results.append(
            CollectionDetailResponse(
                collection=col,
                document_count=item["document_count"],
                chunk_count=chunk_count,
                file_formats=item["file_formats"],
                earliest_upload=item["earliest_upload"],
                latest_upload=item["latest_upload"],
            )
        )
    return results


@app.patch("/collections/{collection}", response_model=RenameCollectionResponse)
def rename_collection_route(collection: str, request: RenameCollectionRequest):
    source = _normalize_collection_param(collection)
    target = request.collection
    if target != source and target in get_all_collections():
        raise HTTPException(
            status_code=409,
            detail=f"Collection {target} already exists; delete it first or pick another name.",
        )

    chunks = rename_collection_in_chroma(source, target)
    if chunks < 0:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to rename collection {source} in Chroma.",
        )

    documents = rename_collection(source, target)
    if chunks == 0 and documents == 0:
        raise HTTPException(status_code=404, detail=f"Collection {source} was not found.")

    increment("renames")
    return RenameCollectionResponse(
        message=f"Renamed collection {source} to {target}.",
        collection=target,
        documents=documents,
        chunks=chunks,
    )


@app.delete("/collections/{collection}", response_model=DeleteDocumentResponse)
def delete_collection_route(collection: str):
    collection_name = _normalize_collection_param(collection)
    if collection_name == DEFAULT_COLLECTION:
        raise HTTPException(
            status_code=400,
            detail="The default collection cannot be deleted; delete documents individually.",
        )

    chroma_chunks = delete_collection_from_chroma(collection_name)
    if chroma_chunks < 0:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete collection {collection_name} from Chroma.",
        )

    db_documents = delete_documents_by_collection(collection_name)
    if chroma_chunks == 0 and db_documents == 0:
        raise HTTPException(status_code=404, detail=f"Collection {collection_name} was not found.")

    delete_document_sources_by_collection(collection_name)
    increment("deletes")
    return DeleteDocumentResponse(
        message=(
            f"Deleted collection {collection_name}: "
            f"{db_documents} document(s), {chroma_chunks} chunk(s)."
        )
    )


@app.get(
    "/collections/{collection}/analytics",
    response_model=CollectionAnalyticsResponse,
)
def get_collection_analytics_route(collection: str):
    collection_name = _normalize_collection_param(collection)
    known = get_all_collections()
    if collection_name not in known:
        raise HTTPException(
            status_code=404,
            detail=f"Collection '{collection_name}' was not found.",
        )
    analytics = get_collection_chunk_analytics(collection_name)
    return CollectionAnalyticsResponse(**analytics)


@app.post(
    "/collections/{collection}/rechunk",
    response_model=CollectionRechunkResponse,
)
def rechunk_collection_route(
    collection: str,
    request: CollectionRechunkRequest | None = None,
):
    collection_name = _normalize_collection_param(collection)
    known = get_all_collections()
    if collection_name not in known:
        raise HTTPException(
            status_code=404,
            detail=f"Collection '{collection_name}' was not found.",
        )

    req = request or CollectionRechunkRequest()
    options = ChunkingOptions(
        strategy=req.chunking_strategy,
        chunk_size=req.chunk_size,
        chunk_overlap=req.chunk_overlap,
    )
    result = rechunk_collection_in_chroma(collection_name, options)
    increment("rechunks")
    return CollectionRechunkResponse(
        message=(
            f"Re-chunked collection '{collection_name}': "
            f"{result['rechunked_documents']} re-chunked, "
            f"{result['skipped_documents']} skipped, "
            f"{result['failed_documents']} failed."
        ),
        collection=collection_name,
        strategy=result["strategy"],
        chunk_size=result["chunk_size"],
        chunk_overlap=result["chunk_overlap"],
        total_documents=result["total_documents"],
        rechunked_documents=result["rechunked_documents"],
        skipped_documents=result["skipped_documents"],
        failed_documents=result["failed_documents"],
        total_chunks_created=result["total_chunks_created"],
        items=[DocumentRechunkItem(**item) for item in result["items"]],
    )


@app.get("/sessions", response_model=list[SessionInfo])
def list_sessions(
    status: str | None = None,
    tag: str | None = None,
    agent: str | None = None,
    tier: str | None = None,
):
    if status is not None:
        cleaned_status = status.strip().lower()
        if cleaned_status not in VALID_SESSION_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid session status '{cleaned_status}'. "
                    f"Must be one of: {sorted(VALID_SESSION_STATUSES)}."
                ),
            )
        status = cleaned_status
    if tag is not None:
        cleaned_tag = tag.strip().lower()
        tag = cleaned_tag if cleaned_tag else None
    if agent is not None:
        cleaned_agent = agent.strip().lower()
        agent = cleaned_agent if cleaned_agent else None
    if tier is not None:
        cleaned_tier = tier.strip().lower()
        tier = cleaned_tier if cleaned_tier else None

    kwargs: dict[str, str | None] = {}
    if status is not None or tag is not None:
        kwargs["status"] = status
        kwargs["tag"] = tag
    if agent is not None:
        kwargs["assigned_agent"] = agent
    if tier is not None:
        kwargs["escalation_tier"] = tier
    return get_all_sessions(**kwargs)


MAX_SEARCH_LIMIT = 100


@app.get("/sessions/search", response_model=SessionSearchResponse)
def search_sessions_route(q: str, limit: int = 20):
    cleaned = q.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Query parameter 'q' must not be empty.")
    if limit <= 0 or limit > MAX_SEARCH_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=f"Query parameter 'limit' must be between 1 and {MAX_SEARCH_LIMIT}.",
        )
    raw_results = search_sessions(cleaned, limit=limit)
    results = [SessionSearchResult(**r) for r in raw_results]
    return SessionSearchResponse(query=cleaned, results=results)


@app.get("/sessions/triage-analytics", response_model=SupportTriageAnalyticsResponse)
def support_triage_analytics():
    data = get_support_triage_analytics()
    return SupportTriageAnalyticsResponse(
        total_sessions=data["total_sessions"],
        active_count=data["active_count"],
        resolved_count=data["resolved_count"],
        escalated_count=data["escalated_count"],
        closed_count=data["closed_count"],
        resolution_rate=data["resolution_rate"],
        escalation_rate=data["escalation_rate"],
        avg_turns_per_session=data["avg_turns_per_session"],
        top_tags=[TagCount(**t) for t in data["top_tags"]],
    )


def _require_session_id(session_id: str) -> str:
    if not session_id.strip():
        raise HTTPException(status_code=400, detail="session_id must not be empty.")
    return session_id


def _normalize_collection_param(collection: str) -> str:
    try:
        return normalize_collection(collection)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _get_session_summary_or_404(session_id: str):
    summaries = [s for s in get_all_sessions() if s["session_id"] == session_id]
    if not summaries:
        raise HTTPException(status_code=404, detail=f"Session {session_id} was not found.")
    return summaries[0]


@app.get("/sessions/{session_id}/history", response_model=list[ChatMessage])
def session_history(session_id: str):
    _require_session_id(session_id)
    return [ChatMessage(**message) for message in get_chat_history(session_id)]


@app.get("/sessions/{session_id}/export")
def export_session(session_id: str, format: str = "markdown"):
    _require_session_id(session_id)
    export_format = format.strip().lower()
    if export_format not in {"markdown", "json", "csv"}:
        raise HTTPException(
            status_code=400,
            detail="Query parameter 'format' must be one of: markdown, json, csv.",
        )
    history = get_chat_history(session_id)
    if not history:
        raise HTTPException(status_code=404, detail=f"Session {session_id} was not found.")
    session_data = _get_session_summary_or_404(session_id)
    label = session_data.get("label")
    status = session_data.get("status")
    tags = session_data.get("tags")
    summary = session_data.get("summary")
    resolution_notes = session_data.get("resolution_notes")
    if export_format == "json":
        content = render_session_json(
            session_id,
            label,
            history,
            status=status,
            tags=tags,
            summary=summary,
            resolution_notes=resolution_notes,
        )
        media_type = "application/json"
        extension = "json"
    elif export_format == "csv":
        content = render_session_csv(
            session_id,
            label,
            history,
            status=status,
            tags=tags,
            summary=summary,
            resolution_notes=resolution_notes,
        )
        media_type = "text/csv"
        extension = "csv"
    else:
        content = render_session_markdown(
            session_id,
            label,
            history,
            status=status,
            tags=tags,
            summary=summary,
            resolution_notes=resolution_notes,
        )
        media_type = "text/markdown"
        extension = "md"

    return PlainTextResponse(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{session_id}.{extension}"'},
    )


@app.delete("/sessions", response_model=PruneSessionsResponse)
def prune_sessions(before: str):
    """Delete sessions inactive since `before` (ISO datetime), with labels+feedback."""
    try:
        cutoff = datetime.fromisoformat(before)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Query param 'before' must be an ISO datetime."
        ) from exc
    if cutoff.tzinfo is not None:
        cutoff = cutoff.astimezone(UTC).replace(tzinfo=None)
    cutoff_iso = cutoff.isoformat(sep=" ")
    deleted = prune_sessions_before(cutoff_iso)
    return PruneSessionsResponse(
        message=f"Pruned {deleted} session(s) inactive since {cutoff_iso}.",
        deleted_sessions=deleted,
    )


@app.delete("/sessions/{session_id}", response_model=DeleteSessionResponse)
def delete_session_route(session_id: str):
    _require_session_id(session_id)
    if not delete_session(session_id):
        raise HTTPException(status_code=404, detail=f"Session {session_id} was not found.")
    return DeleteSessionResponse(message=f"Session {session_id} deleted.")


@app.post("/delete-sessions", response_model=BulkDeleteSessionResponse)
def delete_many_sessions(request: BulkDeleteSessionRequest):
    results: list[BulkDeleteSessionResult] = []
    try:
        status_map = delete_sessions(request.session_ids)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete sessions: {str(exc)}",
        ) from exc

    for session_id in request.session_ids:
        status = status_map.get(session_id, "not_found")
        if status == "deleted":
            increment("deletes")
            results.append(BulkDeleteSessionResult(session_id=session_id, status="deleted"))
        elif status == "not_found":
            results.append(
                BulkDeleteSessionResult(
                    session_id=session_id,
                    status="not_found",
                    detail=f"Session {session_id} was not found.",
                )
            )
        else:
            results.append(
                BulkDeleteSessionResult(
                    session_id=session_id,
                    status="error",
                    detail=f"Failed to delete session {session_id}.",
                )
            )

    deleted_count = sum(1 for r in results if r.status == "deleted")
    return BulkDeleteSessionResponse(
        results=results,
        deleted=deleted_count,
        failed=len(results) - deleted_count,
    )


@app.post("/feedback", response_model=FeedbackResponse)
def submit_feedback(feedback: FeedbackInput, background_tasks: BackgroundTasks):
    if not get_chat_history(feedback.session_id):
        raise HTTPException(status_code=404, detail=f"Session {feedback.session_id} was not found.")
    feedback_id = insert_feedback(feedback.session_id, feedback.rating, feedback.comment)
    increment("feedback_up" if feedback.rating == 1 else "feedback_down")
    if feedback.rating == -1:
        background_tasks.add_task(
            webhooks.dispatch_event,
            "feedback.negative",
            {
                "session_id": feedback.session_id,
                "feedback_id": feedback_id,
                "rating": feedback.rating,
                "comment": feedback.comment,
            },
        )
    return FeedbackResponse(message="Feedback recorded.", feedback_id=feedback_id)


MAX_FEEDBACK_LIMIT = 100


@app.get("/feedback", response_model=FeedbackListResponse)
def list_feedback_route(
    rating: int | None = None,
    session_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    if rating is not None and rating not in (1, -1):
        raise HTTPException(status_code=400, detail="Query param 'rating' must be 1 or -1.")
    if limit <= 0 or limit > MAX_FEEDBACK_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=f"Query param 'limit' must be between 1 and {MAX_FEEDBACK_LIMIT}.",
        )
    if offset < 0:
        raise HTTPException(status_code=400, detail="Query param 'offset' must be non-negative.")

    items, total = list_feedback(rating=rating, session_id=session_id, limit=limit, offset=offset)
    return FeedbackListResponse(
        items=[FeedbackItem(**item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


MAX_ANALYTICS_COMMENTS_LIMIT = 50


@app.get("/feedback/analytics", response_model=FeedbackAnalyticsResponse)
def feedback_analytics_route(recent_comments_limit: int = 5):
    if recent_comments_limit < 0 or recent_comments_limit > MAX_ANALYTICS_COMMENTS_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=(
                "Query param 'recent_comments_limit' must be between 0 and "
                f"{MAX_ANALYTICS_COMMENTS_LIMIT}."
            ),
        )
    data = get_feedback_analytics(recent_comments_limit=recent_comments_limit)
    return FeedbackAnalyticsResponse(
        total_feedback=data["total_feedback"],
        positive_feedback=data["positive_feedback"],
        negative_feedback=data["negative_feedback"],
        satisfaction_rate=data["satisfaction_rate"],
        total_comments=data["total_comments"],
        comment_rate=data["comment_rate"],
        recent_comments=[FeedbackItem(**item) for item in data["recent_comments"]],
    )


@app.post("/feedback/csat", response_model=FeedbackResponse, status_code=201)
def submit_csat_feedback_route(
    request: CSATFeedbackSubmitRequest,
    background_tasks: BackgroundTasks,
):
    if not get_chat_history(request.session_id):
        raise HTTPException(status_code=404, detail=f"Session {request.session_id} was not found.")

    try:
        feedback_item = submit_csat_feedback(
            session_id=request.session_id,
            score=request.score,
            resolution_satisfaction=request.resolution_satisfaction,
            agent_helpfulness=request.agent_helpfulness,
            response_speed=request.response_speed,
            comment=request.comment,
            assigned_agent=request.assigned_agent,
            escalation_tier=request.escalation_tier,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    fb_id = feedback_item["id"]
    increment("feedback_up" if feedback_item.get("rating") == 1 else "feedback_down")

    # If low CSAT (<= 2 stars), schedule low_csat alert webhook
    if csat.is_low_csat(feedback_item):
        background_tasks.add_task(csat.dispatch_low_csat_alert_if_needed, feedback_item)

    return FeedbackResponse(
        message="CSAT feedback recorded.",
        feedback_id=fb_id,
    )


MAX_CSAT_SUMMARY_LIMIT = 10000


@app.get("/feedback/queue", response_model=FeedbackReviewQueueResponse)
def list_feedback_review_queue_route(  # noqa: PLR0913, PLR0917
    review_status: str | None = None,
    assigned_agent: str | None = None,
    escalation_tier: str | None = None,
    min_score: int | None = None,
    max_score: int | None = None,
    limit: int = 50,
    offset: int = 0,
):
    min_csat_star = 1
    max_csat_star = 5
    if min_score is not None and not (min_csat_star <= min_score <= max_csat_star):
        raise HTTPException(status_code=400, detail="Query param 'min_score' must be 1 to 5.")
    if max_score is not None and not (min_csat_star <= max_score <= max_csat_star):
        raise HTTPException(status_code=400, detail="Query param 'max_score' must be 1 to 5.")
    if limit <= 0 or limit > MAX_FEEDBACK_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=f"Query param 'limit' must be between 1 and {MAX_FEEDBACK_LIMIT}.",
        )
    if offset < 0:
        raise HTTPException(status_code=400, detail="Query param 'offset' must be non-negative.")

    try:
        items, total = list_feedback_review_queue(
            review_status=review_status,
            assigned_agent=assigned_agent,
            escalation_tier=escalation_tier,
            min_score=min_score,
            max_score=max_score,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return FeedbackReviewQueueResponse(
        items=[FeedbackReviewItemResponse(**item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.patch("/feedback/{feedback_id}/review", response_model=FeedbackReviewItemResponse)
def update_feedback_review_route(feedback_id: int, request: FeedbackReviewUpdateRequest):
    existing = get_feedback_by_id(feedback_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Feedback {feedback_id} was not found.")

    try:
        updated = update_feedback_review(
            feedback_id=feedback_id,
            review_status=request.review_status,
            reviewer_notes=request.reviewer_notes,
            reviewed_by=request.reviewed_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail=f"Feedback {feedback_id} was not found.")

    return FeedbackReviewItemResponse(**updated)


@app.get("/feedback/csat-summary", response_model=CSATSummaryResponse)
def get_csat_summary_route(limit: int = 1000):
    if limit <= 0 or limit > MAX_CSAT_SUMMARY_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=f"Query param 'limit' must be between 1 and {MAX_CSAT_SUMMARY_LIMIT}.",
        )
    summary_data = csat.calculate_csat_summary(limit=limit)
    return CSATSummaryResponse(**summary_data)


@app.get("/feedback/agent-scorecards", response_model=AgentPerformanceScorecardsResponse)
def get_agent_scorecards_route():
    scorecards_data = get_agent_performance_analytics()
    return AgentPerformanceScorecardsResponse(
        scorecards=[AgentScorecardItem(**item) for item in scorecards_data],
        total_agents=len(scorecards_data),
    )


@app.get("/sessions/{session_id}/feedback", response_model=list[FeedbackItem])
def get_session_feedback_route(session_id: str):
    _require_session_id(session_id)
    if not get_chat_history(session_id):
        raise HTTPException(status_code=404, detail=f"Session {session_id} was not found.")
    items = get_session_feedback(session_id)
    return [FeedbackItem(**item) for item in items]


@app.patch("/sessions/{session_id}", response_model=SessionInfo)
def update_session_route(
    session_id: str,
    request: UpdateSessionRequest,
    background_tasks: BackgroundTasks,
):
    _require_session_id(session_id)
    prior_session = _get_session_summary_or_404(session_id)
    prior_status = (prior_session.get("status") or "active").lower()

    try:
        if (
            request.status is None
            and request.priority is None
            and request.tags is None
            and request.summary is None
            and request.resolution_notes is None
            and request.assigned_agent is None
            and request.escalation_tier is None
            and request.label is not None
        ):
            label = normalize_session_label(request.label)
            updated = rename_session(session_id, label)
        else:
            updated = update_session_metadata(
                session_id,
                label=request.label,
                status=request.status,
                priority=request.priority,
                tags=request.tags,
                summary=request.summary,
                resolution_notes=request.resolution_notes,
                assigned_agent=request.assigned_agent,
                escalation_tier=request.escalation_tier,
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail=f"Session {session_id} was not found.")

    new_session = _get_session_summary_or_404(session_id)
    new_status = (new_session.get("status") or "active").lower()

    if new_status != prior_status:
        if new_status == "escalated":
            background_tasks.add_task(
                webhooks.dispatch_event,
                "session.escalated",
                {
                    "session_id": session_id,
                    "previous_status": prior_status,
                    "status": "escalated",
                    "label": new_session.get("label"),
                    "tags": new_session.get("tags"),
                    "summary": new_session.get("summary"),
                },
            )
        elif new_status == "resolved":
            background_tasks.add_task(
                webhooks.dispatch_event,
                "session.resolved",
                {
                    "session_id": session_id,
                    "previous_status": prior_status,
                    "status": "resolved",
                    "label": new_session.get("label"),
                    "tags": new_session.get("tags"),
                    "summary": new_session.get("summary"),
                    "resolution_notes": new_session.get("resolution_notes"),
                },
            )

    return SessionInfo(**new_session)


@app.post("/sessions/{session_id}/summarize", response_model=SessionSummaryResponse)
def summarize_session_route(session_id: str, request: SessionSummaryRequest | None = None):
    _require_session_id(session_id)
    history = get_chat_history(session_id)
    if not history:
        raise HTTPException(status_code=404, detail=f"Session {session_id} was not found.")

    req = request or SessionSummaryRequest()
    summary_data = summarize_dialogue(history, model=req.model)

    saved = False
    if req.save_summary and summary_data.get("summary"):
        meta = get_session_metadata(session_id) or {}
        existing_tags = [t.strip() for t in (meta.get("tags") or "").split(",") if t.strip()]
        new_tags = sorted(set(existing_tags + summary_data.get("suggested_tags", [])))
        update_session_metadata(
            session_id,
            summary=summary_data["summary"],
            tags=new_tags if new_tags else None,
        )
        saved = True

    return SessionSummaryResponse(
        session_id=session_id,
        summary=summary_data["summary"],
        key_points=summary_data.get("key_points", []),
        sentiment=summary_data.get("sentiment", "neutral"),
        suggested_tags=summary_data.get("suggested_tags", []),
        saved=saved,
    )


@app.post("/delete-doc", response_model=DeleteDocumentResponse)
def delete_document(request: DeleteFileRequest):
    if get_document_record(request.file_id) is None:
        raise HTTPException(
            status_code=404, detail=f"Document with file_id {request.file_id} was not found."
        )

    chroma_delete_success = delete_doc_from_chroma(request.file_id)

    if not chroma_delete_success:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete document with file_id {request.file_id} from Chroma.",
        )

    db_delete_success = delete_document_record(request.file_id)
    if not db_delete_success:
        detail = (
            f"Deleted from Chroma but failed to delete document with file_id "
            f"{request.file_id} from the database."
        )
        raise HTTPException(status_code=500, detail=detail)

    delete_document_source(request.file_id)
    increment("deletes")
    return DeleteDocumentResponse(
        message=f"Successfully deleted document with file_id {request.file_id} from the system."
    )


@app.post("/delete-docs", response_model=BulkDeleteResponse)
def delete_many_documents(request: BulkDeleteFileRequest):
    results: list[BulkDeleteFileResult] = []
    for file_id in request.file_ids:
        if get_document_record(file_id) is None:
            results.append(
                BulkDeleteFileResult(
                    file_id=file_id,
                    status="not_found",
                    detail=f"Document with file_id {file_id} was not found.",
                )
            )
            continue

        if not delete_doc_from_chroma(file_id):
            results.append(
                BulkDeleteFileResult(
                    file_id=file_id,
                    status="error",
                    detail=f"Failed to delete document with file_id {file_id} from Chroma.",
                )
            )
            continue

        if not delete_document_record(file_id):
            results.append(
                BulkDeleteFileResult(
                    file_id=file_id,
                    status="error",
                    detail=(
                        f"Deleted from Chroma but failed to delete document with file_id "
                        f"{file_id} from the database."
                    ),
                )
            )
            continue

        delete_document_source(file_id)

        increment("deletes")
        results.append(BulkDeleteFileResult(file_id=file_id, status="deleted"))

    deleted_count = sum(1 for r in results if r.status == "deleted")
    return BulkDeleteResponse(
        results=results,
        deleted=deleted_count,
        failed=len(results) - deleted_count,
    )


MAX_WEBHOOK_DELIVERIES_LIMIT = 100


@app.post("/webhooks", response_model=WebhookResponse, status_code=201)
def register_webhook(request: WebhookCreateRequest):
    try:
        created = create_webhook(
            url=request.url,
            events=request.events,
            secret=request.secret,
            is_active=request.is_active,
        )
        return WebhookResponse(**created)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/webhooks", response_model=list[WebhookResponse])
def list_webhooks_route(active_only: bool = False, event: str | None = None):
    hooks = list_webhooks(active_only=active_only, event=event)
    return [WebhookResponse(**h) for h in hooks]


@app.get("/webhooks/deliveries", response_model=WebhookDeliveryLogsResponse)
def list_webhook_deliveries_route(
    webhook_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
):
    if limit <= 0 or limit > MAX_WEBHOOK_DELIVERIES_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=f"Query param 'limit' must be between 1 and {MAX_WEBHOOK_DELIVERIES_LIMIT}.",
        )
    if offset < 0:
        raise HTTPException(status_code=400, detail="Query param 'offset' must be non-negative.")
    items, total = get_webhook_delivery_logs(webhook_id=webhook_id, limit=limit, offset=offset)
    return WebhookDeliveryLogsResponse(
        items=[WebhookDeliveryLogItem(**item) for item in items],
        total=total,
    )


@app.get("/webhooks/{webhook_id}", response_model=WebhookResponse)
def get_webhook_route(webhook_id: int):
    hook = get_webhook(webhook_id)
    if hook is None:
        raise HTTPException(status_code=404, detail=f"Webhook {webhook_id} was not found.")
    return WebhookResponse(**hook)


@app.patch("/webhooks/{webhook_id}", response_model=WebhookResponse)
def update_webhook_route(webhook_id: int, request: WebhookUpdateRequest):
    try:
        updated = update_webhook(
            webhook_id=webhook_id,
            url=request.url,
            events=request.events,
            secret=request.secret,
            is_active=request.is_active,
            reset_failures=request.reset_failures,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Webhook {webhook_id} was not found.")
    return WebhookResponse(**updated)


@app.delete("/webhooks/{webhook_id}")
def delete_webhook_route(webhook_id: int):
    deleted = delete_webhook(webhook_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Webhook {webhook_id} was not found.")
    return {"message": f"Webhook {webhook_id} deleted."}


@app.post("/webhooks/{webhook_id}/ping", response_model=WebhookPingResponse)
def ping_webhook_route(webhook_id: int):
    try:
        result = webhooks.ping_webhook(webhook_id)
        return WebhookPingResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# Canned Responses & Action Macro endpoints
@app.post("/macros", response_model=MacroResponse, status_code=201)
def create_macro_route(request: MacroCreateRequest):
    try:
        created = create_macro(
            title=request.title,
            shortcut=request.shortcut,
            category=request.category,
            content=request.content,
            tags=request.tags,
            status_action=request.status_action,
        )
        return MacroResponse(**created)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/macros", response_model=list[MacroResponse])
def list_macros_route(
    category: str | None = None,
    tag: str | None = None,
    search: str | None = None,
):
    macros_list = list_macros(category=category, tag=tag, search=search)
    return [MacroResponse(**m) for m in macros_list]


@app.get("/macros/categories", response_model=MacroCategoriesResponse)
def list_macro_categories_route():
    categories = list_macro_categories()
    return MacroCategoriesResponse(categories=categories)


@app.get("/macros/{macro_id}", response_model=MacroResponse)
def get_macro_route(macro_id: int):
    macro = get_macro(macro_id)
    if macro is None:
        raise HTTPException(status_code=404, detail=f"Macro {macro_id} was not found.")
    return MacroResponse(**macro)


@app.patch("/macros/{macro_id}", response_model=MacroResponse)
def update_macro_route(macro_id: int, request: MacroUpdateRequest):
    try:
        updated = update_macro(
            macro_id=macro_id,
            title=request.title,
            shortcut=request.shortcut,
            category=request.category,
            content=request.content,
            tags=request.tags,
            status_action=request.status_action,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Macro {macro_id} was not found.")
    return MacroResponse(**updated)


@app.delete("/macros/{macro_id}")
def delete_macro_route(macro_id: int):
    deleted = delete_macro(macro_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Macro {macro_id} was not found.")
    return {"message": f"Macro {macro_id} deleted."}


@app.post("/macros/{macro_id}/render", response_model=MacroRenderResponse)
def render_macro_route(macro_id: int, request: MacroRenderRequest):
    macro = get_macro(macro_id)
    if macro is None:
        raise HTTPException(status_code=404, detail=f"Macro {macro_id} was not found.")
    rendered, unresolved = macros.render_template(
        macro["content"],
        variables=request.variables,
        fallback_defaults=request.fallback_defaults,
    )
    return MacroRenderResponse(
        macro_id=macro_id,
        rendered_content=rendered,
        unresolved_variables=unresolved,
        status_action=macro["status_action"],
    )


def _resolve_macro_from_request(request: MacroApplyRequest) -> dict | None:
    if request.macro_id is not None:
        return get_macro(request.macro_id)
    if request.shortcut is not None:
        return get_macro_by_shortcut(request.shortcut)
    return None


def _dispatch_macro_status_webhook(
    background_tasks: BackgroundTasks,
    session_id: str,
    prior_session: dict,
    new_status: str,
    tags: list[str],
) -> None:
    prior_status = (prior_session.get("status") or "active").lower()
    if new_status == prior_status:
        return
    if new_status == "escalated":
        background_tasks.add_task(
            webhooks.dispatch_event,
            "session.escalated",
            {
                "session_id": session_id,
                "previous_status": prior_status,
                "status": "escalated",
                "label": prior_session.get("label"),
                "tags": tags,
                "summary": prior_session.get("summary"),
            },
        )
    elif new_status == "resolved":
        background_tasks.add_task(
            webhooks.dispatch_event,
            "session.resolved",
            {
                "session_id": session_id,
                "previous_status": prior_status,
                "status": "resolved",
                "label": prior_session.get("label"),
                "tags": tags,
                "summary": prior_session.get("summary"),
                "resolution_notes": prior_session.get("resolution_notes"),
            },
        )


@app.post("/sessions/{session_id}/apply-macro", response_model=MacroApplyResponse)
def apply_macro_to_session_route(
    session_id: str,
    request: MacroApplyRequest,
    background_tasks: BackgroundTasks,
):
    _require_session_id(session_id)
    prior_session = _get_session_summary_or_404(session_id)

    macro = _resolve_macro_from_request(request)
    if macro is None:
        target = request.macro_id if request.macro_id is not None else request.shortcut
        raise HTTPException(status_code=404, detail=f"Macro {target} was not found.")

    call_vars = {"session_id": session_id, **request.variables}
    rendered, unresolved = macros.render_template(
        macro["content"],
        variables=call_vars,
        fallback_defaults=request.fallback_defaults,
    )

    insert_application_logs(
        session_id=session_id,
        user_query=f"[Applied Macro: {macro['title']}]",
        gpt_response=rendered,
        model=request.model,
    )

    applied_status: str | None = None
    applied_tags: list[str] = []

    if request.update_status and macro["status_action"]:
        applied_status = macro["status_action"]

    if request.append_tags and macro["tags"]:
        raw_existing_tags = prior_session.get("tags")
        if isinstance(raw_existing_tags, list):
            existing_tags = raw_existing_tags
        elif isinstance(raw_existing_tags, str) and raw_existing_tags:
            existing_tags = [t.strip() for t in raw_existing_tags.split(",") if t.strip()]
        else:
            existing_tags = []
        applied_tags = list(dict.fromkeys(existing_tags + macro["tags"]))

    if applied_status or applied_tags:
        update_session_metadata(
            session_id=session_id,
            status=applied_status,
            tags=applied_tags if applied_tags else None,
        )

        if applied_status:
            _dispatch_macro_status_webhook(
                background_tasks=background_tasks,
                session_id=session_id,
                prior_session=prior_session,
                new_status=applied_status,
                tags=applied_tags,
            )

    return MacroApplyResponse(
        session_id=session_id,
        macro_id=macro["id"],
        macro_title=macro["title"],
        rendered_content=rendered,
        applied_status=applied_status,
        applied_tags=macro["tags"] if request.append_tags else [],
        unresolved_variables=unresolved,
        created_at=datetime.now(UTC).isoformat(),
    )


@app.post("/macros/suggest", response_model=MacroSuggestResponse)
def suggest_macros_route(request: MacroSuggestRequest):
    all_macros = list_macros(category=request.category)
    suggestions = macro_suggestions.suggest_macros_for_query(
        query=request.query,
        macros=all_macros,
        min_score=request.min_score,
        limit=request.top_k,
        category=request.category,
        session_id=request.session_id,
    )
    detected_intent, intent_conf = macro_suggestions.detect_query_intent(request.query)
    extracted_entities = macro_suggestions.extract_query_entities(request.query)
    if request.session_id:
        extracted_entities["session_id"] = request.session_id
    return MacroSuggestResponse(
        query=request.query,
        detected_intent=detected_intent,
        intent_confidence=intent_conf,
        extracted_variables=extracted_entities,
        suggestions=[MacroSuggestionItem(**s) for s in suggestions],
        total_matches=len(suggestions),
    )


@app.get(
    "/sessions/{session_id}/macro-suggestions",
    response_model=SessionMacroSuggestionsResponse,
)
def get_session_macro_suggestions_route(
    session_id: str,
    top_k: int = 3,
    min_score: float = 0.3,
    category: str | None = None,
):
    _require_session_id(session_id)
    _get_session_summary_or_404(session_id)
    latest_query = get_session_latest_user_query(session_id)
    if not latest_query:
        return SessionMacroSuggestionsResponse(
            session_id=session_id,
            latest_query=None,
            detected_intent="unknown",
            extracted_variables={"session_id": session_id},
            suggestions=[],
            total_matches=0,
        )
    all_macros = list_macros(category=category)
    suggestions = macro_suggestions.suggest_macros_for_query(
        query=latest_query,
        macros=all_macros,
        min_score=min_score,
        limit=top_k,
        category=category,
        session_id=session_id,
    )
    detected_intent, _ = macro_suggestions.detect_query_intent(latest_query)
    extracted_entities = macro_suggestions.extract_query_entities(latest_query)
    extracted_entities["session_id"] = session_id
    return SessionMacroSuggestionsResponse(
        session_id=session_id,
        latest_query=latest_query,
        detected_intent=detected_intent,
        extracted_variables=extracted_entities,
        suggestions=[MacroSuggestionItem(**s) for s in suggestions],
        total_matches=len(suggestions),
    )


# ============================================================================
# SLA Policies & Escalation Alerts Endpoints
# ============================================================================


@app.get("/sla/policies", response_model=SLAPoliciesListResponse)
def list_sla_policies_route(
    priority: str | None = None,
    category: str | None = None,
    active_only: bool = False,
):
    policies = list_sla_policies(
        priority=priority,
        category=category,
        active_only=active_only,
    )
    return SLAPoliciesListResponse(
        items=[SLAPolicyResponse(**p) for p in policies],
        total=len(policies),
    )


@app.post("/sla/policies", response_model=SLAPolicyResponse, status_code=201)
def create_sla_policy_route(request: SLAPolicyCreateRequest):
    try:
        policy_id = create_sla_policy(
            name=request.name,
            priority=request.priority,
            category=request.category,
            response_time_minutes=request.response_time_minutes,
            resolution_time_minutes=request.resolution_time_minutes,
            is_active=request.is_active,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    created = get_sla_policy(policy_id)
    if not created:
        raise HTTPException(status_code=500, detail="Failed to fetch created SLA policy.")
    return SLAPolicyResponse(**created)


@app.get("/sla/policies/{policy_id}", response_model=SLAPolicyResponse)
def get_sla_policy_route(policy_id: int):
    policy = get_sla_policy(policy_id)
    if not policy:
        raise HTTPException(
            status_code=404,
            detail=f"SLA policy {policy_id} was not found.",
        )
    return SLAPolicyResponse(**policy)


@app.patch("/sla/policies/{policy_id}", response_model=SLAPolicyResponse)
def update_sla_policy_route(policy_id: int, request: SLAPolicyUpdateRequest):
    is_active_int = 1 if request.is_active is True else (0 if request.is_active is False else None)
    try:
        updated = update_sla_policy(
            policy_id,
            name=request.name,
            priority=request.priority,
            category=request.category,
            response_time_minutes=request.response_time_minutes,
            resolution_time_minutes=request.resolution_time_minutes,
            is_active=is_active_int,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(
            status_code=404,
            detail=f"SLA policy {policy_id} was not found.",
        )
    policy = get_sla_policy(policy_id)
    if not policy:
        raise HTTPException(
            status_code=404,
            detail=f"SLA policy {policy_id} was not found.",
        )
    return SLAPolicyResponse(**policy)


@app.delete("/sla/policies/{policy_id}")
def delete_sla_policy_route(policy_id: int):
    deleted = delete_sla_policy(policy_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"SLA policy {policy_id} was not found.",
        )
    return {"message": f"SLA policy {policy_id} deleted."}


@app.get("/sessions/{session_id}/sla", response_model=SessionSLAStatusResponse)
def get_session_sla_route(session_id: str):
    _require_session_id(session_id)
    _get_session_summary_or_404(session_id)
    status = sla.calculate_session_sla_status(session_id)
    if not status:
        raise HTTPException(
            status_code=404,
            detail=f"SLA status not found for session {session_id}.",
        )
    return SessionSLAStatusResponse(**status)


@app.post("/sla/evaluate-alerts", response_model=SLAAlertEvaluateResponse)
def evaluate_sla_alerts_route(request: SLAAlertEvaluateRequest | None = None):
    approaching_minutes = request.approaching_threshold_minutes if request else 30
    eval_result = sla.evaluate_and_dispatch_sla_alerts(
        approaching_threshold_minutes=approaching_minutes
    )
    return SLAAlertEvaluateResponse(
        total_sessions_checked=eval_result["total_sessions_checked"],
        alerts_triggered=eval_result["alerts_triggered"],
        alerts=[SLAAlertItem(**a) for a in eval_result["alerts"]],
    )


@app.get("/sla/analytics", response_model=SLAComplianceAnalyticsResponse)
def get_sla_analytics_route():
    analytics = sla.get_sla_compliance_analytics()
    return SLAComplianceAnalyticsResponse(**analytics)


# =====================================================================
# Support Agents, Session Assignment & Business Hours Endpoints
# =====================================================================


@app.get("/agents", response_model=SupportAgentListResponse)
def list_agents_route(
    tier: str | None = None,
    department: str | None = None,
    active_only: bool = False,
):
    items = list_support_agents(tier=tier, department=department, active_only=active_only)
    return SupportAgentListResponse(
        items=[SupportAgentResponse(**item) for item in items],
        total=len(items),
    )


@app.post("/agents", response_model=SupportAgentResponse, status_code=201)
def create_agent_route(agent_in: SupportAgentCreateRequest):
    existing = get_support_agent(agent_in.id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Support agent with id '{agent_in.id}' already exists.",
        )
    created = create_support_agent(
        agent_id=agent_in.id,
        name=agent_in.name,
        email=agent_in.email,
        tier=agent_in.tier,
        department=agent_in.department,
        is_active=1 if agent_in.is_active else 0,
    )
    return SupportAgentResponse(**created)


@app.get("/agents/workload", response_model=AgentWorkloadResponse)
def get_agents_workload_route():
    analytics = assignment.get_agent_workload_analytics()
    return AgentWorkloadResponse(**analytics)


@app.get("/agents/{agent_id}", response_model=SupportAgentResponse)
def get_agent_route(agent_id: str):
    agent = get_support_agent(agent_id)
    if not agent:
        raise HTTPException(
            status_code=404,
            detail=f"Support agent '{agent_id}' was not found.",
        )
    return SupportAgentResponse(**agent)


@app.patch("/agents/{agent_id}", response_model=SupportAgentResponse)
def update_agent_route(agent_id: str, agent_in: SupportAgentUpdateRequest):
    existing = get_support_agent(agent_id)
    if not existing:
        raise HTTPException(
            status_code=404,
            detail=f"Support agent '{agent_id}' was not found.",
        )
    update_support_agent(
        agent_id=agent_id,
        name=agent_in.name,
        email=agent_in.email,
        tier=agent_in.tier,
        department=agent_in.department,
        is_active=agent_in.is_active,
    )
    updated = get_support_agent(agent_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Agent update failed.")
    return SupportAgentResponse(**updated)


@app.delete("/agents/{agent_id}")
def delete_agent_route(agent_id: str):
    deleted = delete_support_agent(agent_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Support agent '{agent_id}' was not found.",
        )
    return {"message": f"Support agent '{agent_id}' deleted."}


@app.post("/sessions/{session_id}/assign", response_model=SessionInfo)
def assign_session_route(session_id: str, assign_in: SessionAssignmentRequest):
    _require_session_id(session_id)
    _get_session_summary_or_404(session_id)
    try:
        res = assignment.assign_session(
            session_id=session_id,
            agent_id=assign_in.agent_id,
            tier=assign_in.tier,
            assigned_by=assign_in.assigned_by,
            reason=assign_in.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return SessionInfo(**res["metadata"])


@app.post("/sessions/{session_id}/auto-assign", response_model=SessionInfo)
def auto_assign_session_route(session_id: str, req: AutoAssignRequest | None = None):
    _require_session_id(session_id)
    _get_session_summary_or_404(session_id)
    strategy = req.strategy if req else "least_busy"
    target_tier = req.target_tier if req else None
    department = req.department if req else None
    assigned_by = req.assigned_by if req else "auto_dispatcher"

    try:
        res = assignment.auto_assign_session(
            session_id=session_id,
            strategy=strategy,
            target_tier=target_tier,
            department=department,
            assigned_by=assigned_by,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return SessionInfo(**res["metadata"])


@app.get(
    "/sessions/{session_id}/assignment-history",
    response_model=SessionAssignmentHistoryResponse,
)
def get_session_assignment_history_route(session_id: str, limit: int = 50):
    _require_session_id(session_id)
    _get_session_summary_or_404(session_id)
    history = get_session_assignment_history(session_id=session_id, limit=limit)
    return SessionAssignmentHistoryResponse(
        session_id=session_id,
        items=[SessionAssignmentRecord(**h) for h in history],
        total=len(history),
    )


@app.get("/business-hours/status", response_model=BusinessHoursStatusResponse)
def get_business_hours_status_route():
    status = business_hours.get_business_hours_status()
    return BusinessHoursStatusResponse(**status)


# ============================================================================
# Knowledge Base Gap Detection, FAQ Article Drafting & Deflection Routes
# ============================================================================


@app.post("/knowledge/gaps", response_model=KnowledgeGapItem, status_code=201)
def create_knowledge_gap_route(gap_in: KnowledgeGapCreateRequest):
    """Log or increment a detected knowledge base gap."""
    try:
        gap = db_utils.record_knowledge_gap(
            query=gap_in.query,
            category=gap_in.category or "general",
            source_type=gap_in.source_type or "manual",
            session_id=gap_in.session_id,
            priority=gap_in.priority or "medium",
            notes=gap_in.notes or "",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not gap.get("deduplicated"):
        knowledge_base.dispatch_gap_detected_alert_if_needed(gap)

    return KnowledgeGapItem(**gap)


@app.get("/knowledge/gaps", response_model=KnowledgeGapListResponse)
def list_knowledge_gaps_route(  # noqa: PLR0913, PLR0917
    status: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    source_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List knowledge gaps with filtering and pagination."""
    gaps, total = db_utils.list_knowledge_gaps(
        status=status,
        category=category,
        priority=priority,
        source_type=source_type,
        limit=limit,
        offset=offset,
    )
    return KnowledgeGapListResponse(
        items=[KnowledgeGapItem(**g) for g in gaps],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.post("/knowledge/gaps/scan", response_model=KnowledgeGapScanResponse)
def scan_knowledge_gaps_route(limit: int = 100):
    """Scan support sessions and low-CSAT feedback to automatically identify gaps."""
    res = knowledge_base.scan_sessions_for_knowledge_gaps(limit=limit)
    return KnowledgeGapScanResponse(
        scanned_sessions_count=res["scanned_sessions_count"],
        gaps_created=res["gaps_created"],
        gaps_incremented=res["gaps_incremented"],
        total_gaps_identified=res["total_gaps_identified"],
        gaps=[KnowledgeGapItem(**g) for g in res["gaps"]],
    )


@app.get("/knowledge/gaps/{gap_id}", response_model=KnowledgeGapItem)
def get_knowledge_gap_route(gap_id: int):
    """Retrieve details of a knowledge gap by ID."""
    gap = db_utils.get_knowledge_gap(gap_id)
    if gap is None:
        raise HTTPException(status_code=404, detail=f"Knowledge gap #{gap_id} not found.")
    return KnowledgeGapItem(**gap)


@app.patch("/knowledge/gaps/{gap_id}", response_model=KnowledgeGapItem)
def update_knowledge_gap_route(gap_id: int, gap_in: KnowledgeGapUpdateRequest):
    """Update knowledge gap status, priority, category, linked article, or notes."""
    try:
        updated = db_utils.update_knowledge_gap(
            gap_id=gap_id,
            status=gap_in.status,
            priority=gap_in.priority,
            category=gap_in.category,
            linked_article_id=gap_in.linked_article_id,
            notes=gap_in.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail=f"Knowledge gap #{gap_id} not found.")
    return KnowledgeGapItem(**updated)


@app.delete("/knowledge/gaps/{gap_id}")
def delete_knowledge_gap_route(gap_id: int):
    """Delete a knowledge gap record."""
    deleted = db_utils.delete_knowledge_gap(gap_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Knowledge gap #{gap_id} not found.")
    return {"status": "deleted", "gap_id": gap_id}


@app.post("/knowledge/articles", response_model=KnowledgeArticleItem, status_code=201)
def create_knowledge_article_route(article_in: KnowledgeArticleCreateRequest):
    """Create a new knowledge base article draft."""
    try:
        article = db_utils.create_knowledge_article(
            title=article_in.title,
            content_markdown=article_in.content_markdown,
            category=article_in.category or "general",
            question_pattern=article_in.question_pattern or "",
            tags=article_in.tags or [],
            source_session_id=article_in.source_session_id,
            source_gap_id=article_in.source_gap_id,
            author=article_in.author or "support_agent",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return KnowledgeArticleItem(**article)


@app.post(
    "/sessions/{session_id}/draft-article",
    response_model=KnowledgeArticleItem,
    status_code=201,
)
def draft_article_from_session_route(
    session_id: str,
    req: SessionDraftArticleRequest | None = None,
):
    """Synthesize a structured Markdown FAQ/article draft from a support session."""
    _require_session_id(session_id)
    _get_session_summary_or_404(session_id)

    author = req.author if req and req.author else "support_agent"
    category = req.category if req else None
    link_gap_id = req.link_gap_id if req else None

    try:
        article = knowledge_base.synthesize_article_from_session(
            session_id=session_id,
            author=author,
            category=category,
            link_gap_id=link_gap_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return KnowledgeArticleItem(**article)


@app.get("/knowledge/articles", response_model=KnowledgeArticleListResponse)
def list_knowledge_articles_route(
    status: str | None = None,
    category: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List knowledge articles with status/category/keyword filters."""
    articles, total = db_utils.list_knowledge_articles(
        status=status,
        category=category,
        search=search,
        limit=limit,
        offset=offset,
    )
    return KnowledgeArticleListResponse(
        items=[KnowledgeArticleItem(**a) for a in articles],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get("/knowledge/articles/{article_id}", response_model=KnowledgeArticleItem)
def get_knowledge_article_route(article_id: int):
    """Retrieve details of a knowledge base article by ID."""
    article = db_utils.get_knowledge_article(article_id)
    if article is None:
        raise HTTPException(status_code=404, detail=f"Knowledge article #{article_id} not found.")
    return KnowledgeArticleItem(**article)


@app.patch("/knowledge/articles/{article_id}", response_model=KnowledgeArticleItem)
def update_knowledge_article_route(article_id: int, article_in: KnowledgeArticleUpdateRequest):
    """Update knowledge base article fields."""
    try:
        updated = db_utils.update_knowledge_article(
            article_id=article_id,
            title=article_in.title,
            content_markdown=article_in.content_markdown,
            category=article_in.category,
            question_pattern=article_in.question_pattern,
            tags=article_in.tags,
            status=article_in.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail=f"Knowledge article #{article_id} not found.")
    return KnowledgeArticleItem(**updated)


@app.delete("/knowledge/articles/{article_id}")
def delete_knowledge_article_route(article_id: int):
    """Delete a knowledge base article."""
    deleted = db_utils.delete_knowledge_article(article_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Knowledge article #{article_id} not found.")
    return {"status": "deleted", "article_id": article_id}


@app.post(
    "/knowledge/articles/{article_id}/publish",
    response_model=KnowledgeArticlePublishResponse,
)
def publish_knowledge_article_route(
    article_id: int,
    pub_in: KnowledgeArticlePublishRequest | None = None,
):
    """Publish a knowledge base article directly into RAG document store and resolve linked gaps."""
    collection = pub_in.collection if pub_in else "default"
    chunking_strategy = pub_in.chunking_strategy if pub_in else "markdown"
    chunk_size = pub_in.chunk_size if pub_in else 1000
    chunk_overlap = pub_in.chunk_overlap if pub_in else 200

    try:
        res = knowledge_base.publish_knowledge_article(
            article_id=article_id,
            collection=collection,
            chunking_strategy=chunking_strategy,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    except ValueError as exc:
        err_msg = str(exc)
        status_code = 404 if "not found" in err_msg.lower() else 422
        raise HTTPException(status_code=status_code, detail=err_msg) from exc

    return KnowledgeArticlePublishResponse(
        article=KnowledgeArticleItem(**res["article"]),
        file_id=res["file_id"],
        collection=res["collection"],
        indexed_in_vectorstore=res["indexed_in_vectorstore"],
        linked_gap_resolved=res["linked_gap_resolved"],
    )


@app.get("/knowledge/analytics", response_model=KnowledgeBaseAnalyticsResponse)
def get_knowledge_analytics_route():
    """Retrieve knowledge base gap and deflection analytics."""
    analytics = knowledge_base.get_knowledge_base_analytics()
    return KnowledgeBaseAnalyticsResponse(**analytics)


# --- Property Units Endpoints ---


@app.post("/units", response_model=UnitResponse, status_code=201)
def create_unit_route(request: UnitCreateRequest):
    """Register a new property unit."""
    try:
        created = db_utils.create_unit(
            unit_id=request.id,
            property_name=request.property_name,
            unit_number=request.unit_number,
            building_name=request.building_name or "",
            floor=request.floor if request.floor is not None else 1,
            address=request.address or "",
            city=request.city or "",
            state=request.state or "",
            zip_code=request.zip_code or "",
            monthly_rent=request.monthly_rent,
            parking_spot=request.parking_spot or "",
            gate_code=request.gate_code or "",
            wifi_ssid=request.wifi_ssid or "",
            trash_day=request.trash_day or "",
            notes=request.notes or "",
        )
        return UnitResponse(unit=UnitItem(**created))
    except ValueError as exc:
        status_code = 409 if "already exists" in str(exc).lower() else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.get("/units", response_model=UnitListResponse)
def list_units_route(
    property_name: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List property units with optional filtering and pagination."""
    units, total = db_utils.list_units(
        property_name=property_name,
        search=search,
        limit=limit,
        offset=offset,
    )
    return UnitListResponse(
        items=[UnitItem(**u) for u in units],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get("/units/{unit_id}", response_model=UnitResponse)
def get_unit_route(unit_id: str):
    """Fetch details for a specific property unit."""
    unit = db_utils.get_unit(unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Unit '{unit_id}' not found.")
    return UnitResponse(unit=UnitItem(**unit))


@app.patch("/units/{unit_id}", response_model=UnitResponse)
def update_unit_route(unit_id: str, request: UnitUpdateRequest):
    """Update fields of an existing property unit."""
    try:
        updated = db_utils.update_unit(
            unit_id=unit_id,
            property_name=request.property_name,
            unit_number=request.unit_number,
            building_name=request.building_name,
            floor=request.floor,
            address=request.address,
            city=request.city,
            state=request.state,
            zip_code=request.zip_code,
            monthly_rent=request.monthly_rent,
            parking_spot=request.parking_spot,
            gate_code=request.gate_code,
            wifi_ssid=request.wifi_ssid,
            trash_day=request.trash_day,
            notes=request.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail=f"Unit '{unit_id}' not found.")
    return UnitResponse(unit=UnitItem(**updated))


@app.delete("/units/{unit_id}")
def delete_unit_route(unit_id: str):
    """Delete a property unit record."""
    deleted = db_utils.delete_unit(unit_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Unit '{unit_id}' not found.")
    return {"status": "deleted", "unit_id": unit_id}


# --- Tenants Endpoints ---


@app.post("/tenants", response_model=TenantResponse, status_code=201)
def create_tenant_route(request: TenantCreateRequest):
    """Register a new tenant profile."""
    try:
        created = db_utils.create_tenant(
            tenant_id=request.id,
            first_name=request.first_name,
            last_name=request.last_name,
            email=request.email,
            phone=request.phone,
            lease_start=request.lease_start,
            lease_end=request.lease_end,
            unit_id=request.unit_id,
            monthly_rent=request.monthly_rent,
            balance_due=request.balance_due,
            status=request.status,
            emergency_contact_name=request.emergency_contact_name or "",
            emergency_contact_phone=request.emergency_contact_phone or "",
            notes=request.notes or "",
        )
        return TenantResponse(tenant=TenantItem(**created))
    except ValueError as exc:
        status_code = 409 if "already exists" in str(exc).lower() else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.get("/tenants", response_model=TenantListResponse)
def list_tenants_route(
    unit_id: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List tenant profiles with optional unit, status, and search filtering."""
    tenants, total = db_utils.list_tenants(
        unit_id=unit_id,
        status=status,
        search=search,
        limit=limit,
        offset=offset,
    )
    return TenantListResponse(
        items=[TenantItem(**t) for t in tenants],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get("/tenants/{tenant_id}", response_model=TenantResponse)
def get_tenant_route(tenant_id: str):
    """Retrieve details of a specific tenant profile."""
    tenant = db_utils.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found.")
    return TenantResponse(tenant=TenantItem(**tenant))


@app.patch("/tenants/{tenant_id}", response_model=TenantResponse)
def update_tenant_route(tenant_id: str, request: TenantUpdateRequest):
    """Update fields on an existing tenant profile."""
    try:
        updated = db_utils.update_tenant(
            tenant_id=tenant_id,
            first_name=request.first_name,
            last_name=request.last_name,
            email=request.email,
            phone=request.phone,
            unit_id=request.unit_id,
            lease_start=request.lease_start,
            lease_end=request.lease_end,
            monthly_rent=request.monthly_rent,
            balance_due=request.balance_due,
            status=request.status,
            emergency_contact_name=request.emergency_contact_name,
            emergency_contact_phone=request.emergency_contact_phone,
            notes=request.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found.")
    return TenantResponse(tenant=TenantItem(**updated))


@app.delete("/tenants/{tenant_id}")
def delete_tenant_route(tenant_id: str):
    """Delete a tenant profile."""
    deleted = db_utils.delete_tenant(tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found.")
    return {"status": "deleted", "tenant_id": tenant_id}


# --- Session Tenant Linking & Context Endpoints ---


@app.post("/sessions/{session_id}/link-tenant", response_model=SessionTenantContextResponse)
def link_session_tenant_route(session_id: str, request: SessionTenantLinkRequest):
    """Link a support session to a tenant and/or property unit."""
    try:
        db_utils.link_session_tenant(
            session_id=session_id,
            tenant_id=request.tenant_id,
            unit_id=request.unit_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    ctx = db_utils.get_session_tenant_context(session_id)
    if not ctx:
        return SessionTenantContextResponse(session_id=session_id)
    return SessionTenantContextResponse(
        session_id=session_id,
        tenant_id=ctx.get("tenant_id"),
        unit_id=ctx.get("unit_id"),
        tenant=TenantItem(**ctx["tenant"]) if ctx.get("tenant") else None,
        unit=UnitItem(**ctx["unit"]) if ctx.get("unit") else None,
    )


@app.get("/sessions/{session_id}/tenant-context", response_model=SessionTenantContextResponse)
def get_session_tenant_context_route(session_id: str):
    """Retrieve the grounded tenant and property unit context for a support session."""
    ctx = db_utils.get_session_tenant_context(session_id)
    if not ctx:
        return SessionTenantContextResponse(session_id=session_id)
    return SessionTenantContextResponse(
        session_id=session_id,
        tenant_id=ctx.get("tenant_id"),
        unit_id=ctx.get("unit_id"),
        tenant=TenantItem(**ctx["tenant"]) if ctx.get("tenant") else None,
        unit=UnitItem(**ctx["unit"]) if ctx.get("unit") else None,
    )


@app.get("/tenants/{tenant_id}/support-history", response_model=TenantSupportHistoryResponse)
def get_tenant_support_history_route(tenant_id: str):
    """Retrieve full support ticket/session history for a specific tenant."""
    try:
        history = db_utils.get_tenant_support_history(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TenantSupportHistoryResponse(
        tenant=TenantItem(**history["tenant"]),
        total_sessions=history["total_sessions"],
        sessions=[TenantSupportHistorySessionItem(**s) for s in history["sessions"]],
    )


# --- Maintenance Work Orders & Dispatch Endpoints ---


@app.post("/work-orders", response_model=WorkOrderResponse, status_code=201)
def create_work_order_route(
    request: WorkOrderCreateRequest,
    background_tasks: BackgroundTasks,
):
    """Create a new maintenance work order."""
    wo_id = request.id or f"wo_{uuid.uuid4().hex[:8]}"
    try:
        created = db_utils.create_work_order(
            work_order_id=wo_id,
            unit_id=request.unit_id,
            title=request.title,
            description=request.description,
            category=request.category,
            priority=request.priority,
            status=request.status,
            tenant_id=request.tenant_id,
            session_id=request.session_id,
            entry_permission=request.entry_permission,
            assigned_to=request.assigned_to,
            scheduled_date=request.scheduled_date,
            resolution_notes=request.resolution_notes,
            estimated_cost=request.estimated_cost,
            actual_cost=request.actual_cost,
        )
    except ValueError as exc:
        status_code = 409 if "already exists" in str(exc).lower() else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    background_tasks.add_task(
        webhooks.dispatch_event,
        "work_order.created",
        {
            "work_order_id": created["id"],
            "unit_id": created["unit_id"],
            "tenant_id": created["tenant_id"],
            "session_id": created["session_id"],
            "title": created["title"],
            "category": created["category"],
            "priority": created["priority"],
            "status": created["status"],
            "assigned_to": created["assigned_to"],
            "scheduled_date": created["scheduled_date"],
            "estimated_cost": created["estimated_cost"],
        },
    )
    if created["priority"] == "emergency":
        background_tasks.add_task(
            webhooks.dispatch_event,
            "work_order.emergency_escalated",
            {
                "work_order_id": created["id"],
                "unit_id": created["unit_id"],
                "tenant_id": created["tenant_id"],
                "priority": "emergency",
                "title": created["title"],
                "category": created["category"],
            },
        )

    return WorkOrderResponse(work_order=WorkOrderItem(**created))


@app.get("/work-orders/metrics", response_model=WorkOrderMetricsResponse)
def get_work_order_metrics_route():
    """Retrieve aggregate maintenance metrics, KPIs, and status counts."""
    metrics = db_utils.get_work_order_summary_metrics()
    return WorkOrderMetricsResponse(**metrics)


@app.get("/work-orders", response_model=WorkOrderListResponse)
def list_work_orders_route(  # noqa: PLR0913, PLR0917
    unit_id: str | None = None,
    tenant_id: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List maintenance work orders with optional filtering and pagination."""
    items, total = db_utils.list_work_orders(
        unit_id=unit_id,
        tenant_id=tenant_id,
        status=status,
        priority=priority,
        category=category,
        search=search,
        limit=limit,
        offset=offset,
    )
    return WorkOrderListResponse(
        items=[WorkOrderItem(**item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get("/work-orders/{work_order_id}", response_model=WorkOrderResponse)
def get_work_order_route(work_order_id: str):
    """Retrieve details of a specific maintenance work order."""
    item = db_utils.get_work_order(work_order_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Work order '{work_order_id}' not found.")
    return WorkOrderResponse(work_order=WorkOrderItem(**item))


@app.patch("/work-orders/{work_order_id}", response_model=WorkOrderResponse)
def update_work_order_route(
    work_order_id: str,
    request: WorkOrderUpdateRequest,
    background_tasks: BackgroundTasks,
):
    """Update fields on an existing work order."""
    prior = db_utils.get_work_order(work_order_id)
    if not prior:
        raise HTTPException(status_code=404, detail=f"Work order '{work_order_id}' not found.")

    try:
        updated = db_utils.update_work_order(
            work_order_id=work_order_id,
            title=request.title,
            description=request.description,
            category=request.category,
            priority=request.priority,
            status=request.status,
            entry_permission=request.entry_permission,
            assigned_to=request.assigned_to,
            scheduled_date=request.scheduled_date,
            completed_at=request.completed_at,
            resolution_notes=request.resolution_notes,
            estimated_cost=request.estimated_cost,
            actual_cost=request.actual_cost,
            unit_id=request.unit_id,
            tenant_id=request.tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not updated:
        raise HTTPException(status_code=404, detail=f"Work order '{work_order_id}' not found.")

    if updated["status"] != prior["status"]:
        background_tasks.add_task(
            webhooks.dispatch_event,
            "work_order.status_changed",
            {
                "work_order_id": updated["id"],
                "unit_id": updated["unit_id"],
                "tenant_id": updated["tenant_id"],
                "previous_status": prior["status"],
                "new_status": updated["status"],
                "priority": updated["priority"],
                "category": updated["category"],
                "resolution_notes": updated["resolution_notes"],
                "actual_cost": updated["actual_cost"],
            },
        )

    if updated["priority"] == "emergency" and prior["priority"] != "emergency":
        background_tasks.add_task(
            webhooks.dispatch_event,
            "work_order.emergency_escalated",
            {
                "work_order_id": updated["id"],
                "unit_id": updated["unit_id"],
                "tenant_id": updated["tenant_id"],
                "priority": "emergency",
                "title": updated["title"],
                "category": updated["category"],
            },
        )

    return WorkOrderResponse(work_order=WorkOrderItem(**updated))


@app.delete("/work-orders/{work_order_id}")
def delete_work_order_route(work_order_id: str):
    """Delete a maintenance work order."""
    deleted = db_utils.delete_work_order(work_order_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Work order '{work_order_id}' not found.")
    return {"status": "deleted", "work_order_id": work_order_id}


@app.post(
    "/sessions/{session_id}/create-work-order",
    response_model=WorkOrderResponse,
    status_code=201,
)
def create_work_order_from_session_route(
    session_id: str,
    request: WorkOrderFromSessionRequest,
    background_tasks: BackgroundTasks,
):
    """Convert a support session into a maintenance work order with auto-resolved unit/tenant."""
    target_unit = request.unit_id
    target_tenant = request.tenant_id

    if not target_unit or not target_tenant:
        ctx = db_utils.get_session_tenant_context(session_id)
        if ctx:
            if not target_unit:
                target_unit = ctx.get("unit_id")
            if not target_tenant:
                target_tenant = ctx.get("tenant_id")

    if not target_unit:
        raise HTTPException(
            status_code=422,
            detail="unit_id is required either in request body or linked to session context.",
        )

    wo_id = f"wo_{uuid.uuid4().hex[:8]}"
    try:
        created = db_utils.create_work_order(
            work_order_id=wo_id,
            unit_id=target_unit,
            title=request.title,
            description=request.description,
            category=request.category,
            priority=request.priority,
            status="submitted",
            tenant_id=target_tenant,
            session_id=session_id,
            entry_permission=request.entry_permission,
            assigned_to=request.assigned_to,
            scheduled_date=request.scheduled_date,
            estimated_cost=request.estimated_cost,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    background_tasks.add_task(
        webhooks.dispatch_event,
        "work_order.created",
        {
            "work_order_id": created["id"],
            "unit_id": created["unit_id"],
            "tenant_id": created["tenant_id"],
            "session_id": created["session_id"],
            "title": created["title"],
            "category": created["category"],
            "priority": created["priority"],
            "status": created["status"],
            "assigned_to": created["assigned_to"],
            "scheduled_date": created["scheduled_date"],
            "estimated_cost": created["estimated_cost"],
        },
    )
    if created["priority"] == "emergency":
        background_tasks.add_task(
            webhooks.dispatch_event,
            "work_order.emergency_escalated",
            {
                "work_order_id": created["id"],
                "unit_id": created["unit_id"],
                "tenant_id": created["tenant_id"],
                "priority": "emergency",
                "title": created["title"],
                "category": created["category"],
            },
        )

    return WorkOrderResponse(work_order=WorkOrderItem(**created))


@app.get("/units/{unit_id}/work-orders", response_model=WorkOrderListResponse)
def get_unit_work_orders_route(unit_id: str, open_only: bool = False):
    """Retrieve maintenance work orders for a specific unit."""
    items = db_utils.get_unit_work_orders(unit_id, open_only=open_only)
    return WorkOrderListResponse(
        items=[WorkOrderItem(**item) for item in items],
        total=len(items),
        limit=len(items),
        offset=0,
    )


@app.get("/tenants/{tenant_id}/work-orders", response_model=WorkOrderListResponse)
def get_tenant_work_orders_route(tenant_id: str, open_only: bool = False):
    """Retrieve maintenance work orders for a specific tenant."""
    items = db_utils.get_tenant_work_orders(tenant_id, open_only=open_only)
    return WorkOrderListResponse(
        items=[WorkOrderItem(**item) for item in items],
        total=len(items),
        limit=len(items),
        offset=0,
    )


# ---------------------------------------------------------------------------
# Resident Billing, Rent Ledgers, Invoices & Payment Operations
# ---------------------------------------------------------------------------


@app.post("/billing/transactions", response_model=BillingTransactionResponse, status_code=201)
def create_billing_transaction_route(
    request: BillingTransactionCreateRequest, background_tasks: BackgroundTasks
):
    tx_id = request.id or f"tx_{uuid.uuid4().hex[:10]}"
    try:
        created = db_utils.create_billing_transaction(
            transaction_id=tx_id,
            tenant_id=request.tenant_id,
            unit_id=request.unit_id,
            description=request.description,
            amount=request.amount,
            transaction_type=request.transaction_type,
            status=request.status,
            due_date=request.due_date,
            paid_at=request.paid_at,
            payment_method=request.payment_method,
            reference_number=request.reference_number,
            session_id=request.session_id,
            notes=request.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    event_name = (
        "billing.payment_received"
        if created["transaction_type"] == "payment"
        else "billing.charge_posted"
    )
    background_tasks.add_task(
        webhooks.dispatch_event,
        event_name,
        {
            "transaction_id": created["id"],
            "tenant_id": created["tenant_id"],
            "unit_id": created["unit_id"],
            "transaction_type": created["transaction_type"],
            "amount": created["amount"],
            "status": created["status"],
            "due_date": created["due_date"],
            "payment_method": created["payment_method"],
        },
    )
    if created["status"] == "overdue":
        background_tasks.add_task(
            webhooks.dispatch_event,
            "billing.overdue_escalated",
            {
                "transaction_id": created["id"],
                "tenant_id": created["tenant_id"],
                "unit_id": created["unit_id"],
                "amount": created["amount"],
                "due_date": created["due_date"],
            },
        )
    elif created["transaction_type"] == "late_fee":
        background_tasks.add_task(
            webhooks.dispatch_event,
            "billing.late_fee_assessed",
            {
                "transaction_id": created["id"],
                "tenant_id": created["tenant_id"],
                "unit_id": created["unit_id"],
                "amount": created["amount"],
            },
        )

    return BillingTransactionResponse(transaction=BillingTransactionItem(**created))


@app.get("/billing/transactions", response_model=BillingTransactionListResponse)
def list_billing_transactions_route(  # noqa: PLR0913, PLR0917
    tenant_id: str | None = None,
    unit_id: str | None = None,
    transaction_type: str | None = None,
    status: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List billing transactions with optional filtering and pagination."""
    items, total = db_utils.list_billing_transactions(
        tenant_id=tenant_id,
        unit_id=unit_id,
        transaction_type=transaction_type,
        status=status,
        start_date=start_date,
        end_date=end_date,
        search=search,
        limit=limit,
        offset=offset,
    )
    return BillingTransactionListResponse(
        items=[BillingTransactionItem(**item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get("/billing/metrics", response_model=BillingMetricsResponse)
def get_billing_metrics_route():
    """Retrieve portfolio billing and payment financial metrics."""
    metrics = db_utils.get_billing_summary_metrics()
    return BillingMetricsResponse(**metrics)


@app.get("/billing/transactions/{transaction_id}", response_model=BillingTransactionResponse)
def get_billing_transaction_route(transaction_id: str):
    """Retrieve a single billing transaction by ID."""
    item = db_utils.get_billing_transaction(transaction_id)
    if not item:
        raise HTTPException(
            status_code=404,
            detail=f"Billing transaction '{transaction_id}' not found.",
        )
    return BillingTransactionResponse(transaction=BillingTransactionItem(**item))


@app.patch("/billing/transactions/{transaction_id}", response_model=BillingTransactionResponse)
def update_billing_transaction_route(
    transaction_id: str,
    request: BillingTransactionUpdateRequest,
    background_tasks: BackgroundTasks,
):
    """Update billing transaction details (status, notes, payment info)."""
    item = db_utils.update_billing_transaction(
        transaction_id=transaction_id,
        status=request.status,
        description=request.description,
        due_date=request.due_date,
        paid_at=request.paid_at,
        payment_method=request.payment_method,
        reference_number=request.reference_number,
        notes=request.notes,
    )
    if not item:
        raise HTTPException(
            status_code=404,
            detail=f"Billing transaction '{transaction_id}' not found.",
        )

    if request.status == "paid":
        background_tasks.add_task(
            webhooks.dispatch_event,
            "billing.payment_received",
            {
                "transaction_id": item["id"],
                "tenant_id": item["tenant_id"],
                "unit_id": item["unit_id"],
                "amount": item["amount"],
                "status": "paid",
            },
        )
    elif request.status == "overdue":
        background_tasks.add_task(
            webhooks.dispatch_event,
            "billing.overdue_escalated",
            {
                "transaction_id": item["id"],
                "tenant_id": item["tenant_id"],
                "unit_id": item["unit_id"],
                "amount": item["amount"],
            },
        )

    return BillingTransactionResponse(transaction=BillingTransactionItem(**item))


@app.delete("/billing/transactions/{transaction_id}")
def delete_billing_transaction_route(transaction_id: str):
    """Delete a billing transaction record."""
    deleted = db_utils.delete_billing_transaction(transaction_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Billing transaction '{transaction_id}' not found.",
        )
    return {"message": f"Billing transaction '{transaction_id}' deleted successfully."}


@app.post("/tenants/{tenant_id}/payments", response_model=TenantPaymentResponse, status_code=201)
def record_tenant_payment_route(
    tenant_id: str,
    request: TenantPaymentRequest,
    background_tasks: BackgroundTasks,
):
    """Record a tenant payment, reconciling tenant balance and overdue charges."""
    try:
        result = db_utils.record_tenant_payment(
            tenant_id=tenant_id,
            amount=request.amount,
            payment_method=request.payment_method,
            reference_number=request.reference_number,
            description=request.description,
            session_id=request.session_id,
            notes=request.notes,
            transaction_id=request.transaction_id,
        )
    except ValueError as exc:
        if "does not exist" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not result:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found.")

    tx = result["transaction"]
    background_tasks.add_task(
        webhooks.dispatch_event,
        "billing.payment_received",
        {
            "transaction_id": tx["id"],
            "tenant_id": tx["tenant_id"],
            "unit_id": tx["unit_id"],
            "amount": tx["amount"],
            "payment_method": tx["payment_method"],
            "previous_balance": result["previous_balance"],
            "new_balance": result["new_balance"],
        },
    )

    return TenantPaymentResponse(
        transaction=BillingTransactionItem(**tx),
        previous_balance=result["previous_balance"],
        new_balance=result["new_balance"],
        amount_paid=result["amount_paid"],
        tenant_status=result["tenant_status"],
    )


@app.get("/tenants/{tenant_id}/ledger", response_model=TenantLedgerSummaryResponse)
def get_tenant_ledger_route(tenant_id: str):
    """Retrieve a tenant's complete ledger summary, charges, payments, and balance."""
    ledger = db_utils.get_tenant_ledger_summary(tenant_id)
    if not ledger:
        raise HTTPException(
            status_code=404,
            detail=f"Tenant '{tenant_id}' not found or has no billing record.",
        )
    last_payment = (
        BillingTransactionItem(**ledger["last_payment"]) if ledger.get("last_payment") else None
    )
    recent_transactions = [
        BillingTransactionItem(**item) for item in ledger.get("recent_transactions", [])
    ]
    return TenantLedgerSummaryResponse(
        tenant_id=ledger["tenant_id"],
        unit_id=ledger["unit_id"],
        current_balance=ledger["current_balance"],
        monthly_rent=ledger["monthly_rent"],
        total_charges=ledger["total_charges"],
        total_payments=ledger["total_payments"],
        overdue_amount=ledger["overdue_amount"],
        overdue_count=ledger["overdue_count"],
        tenant_status=ledger["tenant_status"],
        last_payment=last_payment,
        recent_transactions=recent_transactions,
    )


@app.post(
    "/sessions/{session_id}/record-payment",
    response_model=TenantPaymentResponse,
    status_code=201,
)
def record_session_payment_route(
    session_id: str,
    request: TenantPaymentRequest,
    background_tasks: BackgroundTasks,
):
    """Record a payment directly from an active support session for its linked tenant."""
    context = db_utils.get_session_tenant_context(session_id)
    if not context or not context.get("tenant"):
        raise HTTPException(
            status_code=400,
            detail=f"Session '{session_id}' has no linked tenant to record payment for.",
        )
    tenant_id = context["tenant"]["id"]
    try:
        result = db_utils.record_tenant_payment(
            tenant_id=tenant_id,
            amount=request.amount,
            payment_method=request.payment_method,
            reference_number=request.reference_number,
            description=request.description,
            session_id=session_id,
            notes=request.notes,
            transaction_id=request.transaction_id,
        )
    except ValueError as exc:
        if "does not exist" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not result:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found.")

    tx = result["transaction"]
    background_tasks.add_task(
        webhooks.dispatch_event,
        "billing.payment_received",
        {
            "transaction_id": tx["id"],
            "tenant_id": tx["tenant_id"],
            "unit_id": tx["unit_id"],
            "session_id": session_id,
            "amount": tx["amount"],
            "previous_balance": result["previous_balance"],
            "new_balance": result["new_balance"],
        },
    )

    return TenantPaymentResponse(
        transaction=BillingTransactionItem(**tx),
        previous_balance=result["previous_balance"],
        new_balance=result["new_balance"],
        amount_paid=result["amount_paid"],
        tenant_status=result["tenant_status"],
    )


# ============================================================================
# Lease Renewals & Digital Agreements Endpoints
# ============================================================================


@app.post("/lease-renewals", response_model=LeaseRenewalResponse, status_code=201)
def create_lease_renewal_route(
    request: LeaseRenewalCreateRequest,
    background_tasks: BackgroundTasks,
):
    """Create a new lease renewal offer, generating default dates/rent if omitted."""
    try:
        item = db_utils.create_lease_renewal(
            tenant_id=request.tenant_id,
            unit_id=request.unit_id,
            proposed_rent=request.proposed_rent,
            current_rent=request.current_rent,
            term_months=request.term_months,
            start_date=request.start_date,
            end_date=request.end_date,
            concession_amount=request.concession_amount,
            concession_notes=request.concession_notes,
            security_deposit_change=request.security_deposit_change,
            status=request.status,
            expires_at=request.expires_at,
            session_id=request.session_id,
            notes=request.notes,
            lr_id=request.renewal_id,
        )
    except ValueError as exc:
        if "does not exist" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    background_tasks.add_task(
        webhooks.dispatch_event,
        "lease_renewal.offered",
        {
            "renewal_id": item["id"],
            "tenant_id": item["tenant_id"],
            "unit_id": item["unit_id"],
            "proposed_rent": item["proposed_rent"],
            "term_months": item["term_months"],
            "status": item["status"],
            "expires_at": item["expires_at"],
        },
    )

    return LeaseRenewalResponse(renewal=LeaseRenewalItem(**item))


@app.get("/lease-renewals", response_model=LeaseRenewalListResponse)
def list_lease_renewals_route(  # noqa: PLR0913, PLR0917
    tenant_id: str | None = None,
    unit_id: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List lease renewals with filtering by tenant, unit, status, and search."""
    items, total = db_utils.list_lease_renewals(
        tenant_id=tenant_id,
        unit_id=unit_id,
        status=status,
        search=search,
        limit=limit,
        offset=offset,
    )
    return LeaseRenewalListResponse(
        items=[LeaseRenewalItem(**r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get("/lease-renewals/metrics", response_model=LeaseRenewalMetricsResponse)
def get_lease_renewal_metrics_route():
    """Retrieve portfolio lease renewal metrics (totals, renewal rate, terms)."""
    metrics = db_utils.get_lease_renewal_summary_metrics()
    return LeaseRenewalMetricsResponse(**metrics)


@app.get("/lease-renewals/{renewal_id}", response_model=LeaseRenewalResponse)
def get_lease_renewal_route(renewal_id: str):
    """Retrieve a single lease renewal record by its ID."""
    item = db_utils.get_lease_renewal(renewal_id)
    if not item:
        raise HTTPException(
            status_code=404,
            detail=f"Lease renewal '{renewal_id}' not found.",
        )
    return LeaseRenewalResponse(renewal=LeaseRenewalItem(**item))


@app.patch("/lease-renewals/{renewal_id}", response_model=LeaseRenewalResponse)
def update_lease_renewal_route(
    renewal_id: str,
    request: LeaseRenewalUpdateRequest,
    background_tasks: BackgroundTasks,
):
    """Update lease renewal terms, financial fields, or status."""
    try:
        item = db_utils.update_lease_renewal(
            renewal_id=renewal_id,
            proposed_rent=request.proposed_rent,
            term_months=request.term_months,
            start_date=request.start_date,
            end_date=request.end_date,
            concession_amount=request.concession_amount,
            concession_notes=request.concession_notes,
            security_deposit_change=request.security_deposit_change,
            status=request.status,
            expires_at=request.expires_at,
            notes=request.notes,
            document_file_id=request.document_file_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not item:
        raise HTTPException(
            status_code=404,
            detail=f"Lease renewal '{renewal_id}' not found.",
        )

    if request.status == "accepted":
        background_tasks.add_task(
            webhooks.dispatch_event,
            "lease_renewal.accepted",
            {"renewal_id": item["id"], "tenant_id": item["tenant_id"]},
        )
    elif request.status == "declined":
        background_tasks.add_task(
            webhooks.dispatch_event,
            "lease_renewal.declined",
            {"renewal_id": item["id"], "tenant_id": item["tenant_id"]},
        )

    return LeaseRenewalResponse(renewal=LeaseRenewalItem(**item))


@app.delete("/lease-renewals/{renewal_id}")
def delete_lease_renewal_route(renewal_id: str):
    """Delete a lease renewal record."""
    deleted = db_utils.delete_lease_renewal(renewal_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Lease renewal '{renewal_id}' not found.",
        )
    return {"message": f"Lease renewal '{renewal_id}' deleted successfully."}


@app.post("/lease-renewals/{renewal_id}/sign", response_model=LeaseRenewalResponse)
def sign_lease_renewal_route(
    renewal_id: str,
    request: LeaseRenewalSignRequest,
    background_tasks: BackgroundTasks,
):
    """Execute digital e-signature on renewal, updating tenant lease dates and rent."""
    try:
        item = db_utils.sign_lease_renewal(
            renewal_id=renewal_id,
            signature_name=request.signature_name,
            signature_ip=request.signature_ip,
            signed_at=request.signed_at,
            notes=request.notes,
        )
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    background_tasks.add_task(
        webhooks.dispatch_event,
        "lease_renewal.signed",
        {
            "renewal_id": item["id"],
            "tenant_id": item["tenant_id"],
            "unit_id": item["unit_id"],
            "proposed_rent": item["proposed_rent"],
            "term_months": item["term_months"],
            "signed_at": item["signed_at"],
            "signature_name": item["signature_name"],
        },
    )

    return LeaseRenewalResponse(renewal=LeaseRenewalItem(**item))


@app.post(
    "/lease-renewals/{renewal_id}/publish-document",
    response_model=LeaseRenewalDocumentPublishResponse,
)
def publish_lease_renewal_document_route(
    renewal_id: str,
    request: LeaseRenewalDocumentPublishRequest,
):
    """Synthesize legal renewal agreement in Markdown and index into RAG vector store."""
    try:
        result = lease_renewals.publish_lease_renewal_document(
            renewal_id=renewal_id,
            collection=request.collection,
            chunking_strategy=request.chunking_strategy,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
        )
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return LeaseRenewalDocumentPublishResponse(**result)


@app.post(
    "/sessions/{session_id}/create-lease-renewal",
    response_model=LeaseRenewalResponse,
    status_code=201,
)
def create_session_lease_renewal_route(
    session_id: str,
    request: LeaseRenewalCreateRequest,
    background_tasks: BackgroundTasks,
):
    """Generate a 1-click renewal offer from active support session for linked resident."""
    context = db_utils.get_session_tenant_context(session_id)
    if not context or not context.get("tenant"):
        raise HTTPException(
            status_code=400,
            detail=f"Session '{session_id}' has no linked tenant to create lease renewal for.",
        )
    tenant = context["tenant"]
    resolved_tenant_id = tenant["id"]
    resolved_unit_id = request.unit_id or tenant.get("unit_id")

    try:
        item = db_utils.create_lease_renewal(
            tenant_id=resolved_tenant_id,
            unit_id=resolved_unit_id,
            proposed_rent=request.proposed_rent,
            current_rent=request.current_rent,
            term_months=request.term_months,
            start_date=request.start_date,
            end_date=request.end_date,
            concession_amount=request.concession_amount,
            concession_notes=request.concession_notes,
            security_deposit_change=request.security_deposit_change,
            status=request.status,
            expires_at=request.expires_at,
            session_id=session_id,
            notes=request.notes,
            lr_id=request.renewal_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    background_tasks.add_task(
        webhooks.dispatch_event,
        "lease_renewal.offered",
        {
            "renewal_id": item["id"],
            "tenant_id": item["tenant_id"],
            "unit_id": item["unit_id"],
            "session_id": session_id,
            "proposed_rent": item["proposed_rent"],
            "term_months": item["term_months"],
            "status": item["status"],
            "expires_at": item["expires_at"],
        },
    )

    return LeaseRenewalResponse(renewal=LeaseRenewalItem(**item))


@app.get("/tenants/{tenant_id}/lease-renewals", response_model=LeaseRenewalListResponse)
def get_tenant_lease_renewals_route(tenant_id: str):
    """Retrieve all lease renewals associated with a specific resident."""
    tenant = db_utils.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=404,
            detail=f"Tenant '{tenant_id}' not found.",
        )
    items, total = db_utils.list_lease_renewals(tenant_id=tenant_id, limit=100)
    return LeaseRenewalListResponse(
        items=[LeaseRenewalItem(**r) for r in items],
        total=total,
        limit=100,
        offset=0,
    )


# ---------------------------------------------------------------------------
# Move-In/Move-Out Inspections & Turnover Endpoints (v0.39.0)
# ---------------------------------------------------------------------------


@app.post("/inspections", response_model=InspectionResponse, status_code=201)
def create_inspection_route(
    request: InspectionCreateRequest,
    background_tasks: BackgroundTasks,
):
    """Schedule and create a new resident move-in/out or turnover inspection."""
    try:
        item = db_utils.create_inspection(
            tenant_id=request.tenant_id,
            unit_id=request.unit_id,
            inspection_type=request.inspection_type,
            scheduled_date=request.scheduled_date,
            inspector_name=request.inspector_name,
            status=request.status,
            overall_condition=request.overall_condition,
            items=[i.model_dump() for i in request.items] if request.items else None,
            deposit_deduction_total=request.deposit_deduction_total,
            deposit_refund_amount=request.deposit_refund_amount,
            key_return_status=request.key_return_status,
            notes=request.notes,
            session_id=request.session_id,
            insp_id=request.insp_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    background_tasks.add_task(
        webhooks.dispatch_event,
        "inspection.scheduled",
        {
            "inspection_id": item["id"],
            "tenant_id": item["tenant_id"],
            "unit_id": item["unit_id"],
            "inspection_type": item["inspection_type"],
            "scheduled_date": item["scheduled_date"],
            "status": item["status"],
            "inspector_name": item["inspector_name"],
        },
    )

    return InspectionResponse(inspection=InspectionRecord(**item))


@app.get("/inspections", response_model=InspectionListResponse)
def list_inspections_route(  # noqa: PLR0913, PLR0917
    tenant_id: str | None = None,
    unit_id: str | None = None,
    inspection_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List inspections with filtering by tenant, unit, type, and status."""
    items, total = db_utils.list_inspections(
        tenant_id=tenant_id,
        unit_id=unit_id,
        inspection_type=inspection_type,
        status=status,
        limit=limit,
        offset=offset,
    )
    return InspectionListResponse(
        items=[InspectionRecord(**r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get("/inspections/metrics", response_model=InspectionMetricsResponse)
def get_inspection_metrics_route():
    """Retrieve aggregated portfolio move-in/out and turnover inspection KPIs."""
    metrics = db_utils.get_inspection_summary_metrics()
    return InspectionMetricsResponse(**metrics)


@app.get("/inspections/{inspection_id}", response_model=InspectionResponse)
def get_inspection_route(inspection_id: str):
    """Retrieve detailed move-in/out inspection record by ID."""
    item = db_utils.get_inspection(inspection_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Inspection '{inspection_id}' not found.")
    return InspectionResponse(inspection=InspectionRecord(**item))


@app.patch("/inspections/{inspection_id}", response_model=InspectionResponse)
def update_inspection_route(
    inspection_id: str,
    request: InspectionUpdateRequest,
):
    """Update inspection details, checklist items, key return, or notes."""
    try:
        item = db_utils.update_inspection(
            insp_id=inspection_id,
            scheduled_date=request.scheduled_date,
            completed_date=request.completed_date,
            inspector_name=request.inspector_name,
            status=request.status,
            overall_condition=request.overall_condition,
            items=[i.model_dump() for i in request.items] if request.items is not None else None,
            deposit_deduction_total=request.deposit_deduction_total,
            deposit_refund_amount=request.deposit_refund_amount,
            key_return_status=request.key_return_status,
            notes=request.notes,
            document_file_id=request.document_file_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not item:
        raise HTTPException(status_code=404, detail=f"Inspection '{inspection_id}' not found.")
    return InspectionResponse(inspection=InspectionRecord(**item))


@app.delete("/inspections/{inspection_id}")
def delete_inspection_route(inspection_id: str):
    """Cancel and delete an inspection record."""
    deleted = db_utils.delete_inspection(inspection_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Inspection '{inspection_id}' not found.")
    return {"status": "deleted", "id": inspection_id}


@app.post("/inspections/{inspection_id}/complete", response_model=InspectionResponse)
def complete_inspection_route(
    inspection_id: str,
    request: InspectionCompleteRequest,
    background_tasks: BackgroundTasks,
):
    """Finalize an inspection, calculate itemized deductions, and assess deposit refund."""
    try:
        item = db_utils.complete_inspection(
            insp_id=inspection_id,
            security_deposit_base=request.deposit_held,
            key_return_status=request.key_return_status,
            overall_condition=request.overall_condition,
            notes=request.notes,
            items=[i.model_dump() for i in request.items] if request.items is not None else None,
        )
    except ValueError as exc:
        if "not found" in str(exc).lower() or "does not exist" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not item:
        raise HTTPException(status_code=404, detail=f"Inspection '{inspection_id}' not found.")

    background_tasks.add_task(
        webhooks.dispatch_event,
        "inspection.completed",
        {
            "inspection_id": item["id"],
            "tenant_id": item["tenant_id"],
            "unit_id": item["unit_id"],
            "inspection_type": item["inspection_type"],
            "completed_date": item["completed_date"],
            "overall_condition": item["overall_condition"],
            "deposit_deduction_total": item["deposit_deduction_total"],
            "deposit_refund_amount": item["deposit_refund_amount"],
            "key_return_status": item["key_return_status"],
        },
    )

    if item.get("deposit_deduction_total", 0.0) > 0:
        background_tasks.add_task(
            webhooks.dispatch_event,
            "inspection.deposit_deductions_assessed",
            {
                "inspection_id": item["id"],
                "tenant_id": item["tenant_id"],
                "unit_id": item["unit_id"],
                "deposit_deduction_total": item["deposit_deduction_total"],
                "deposit_refund_amount": item["deposit_refund_amount"],
            },
        )

    if item.get("key_return_status") == "returned":
        background_tasks.add_task(
            webhooks.dispatch_event,
            "inspection.keys_returned",
            {
                "inspection_id": item["id"],
                "tenant_id": item["tenant_id"],
                "unit_id": item["unit_id"],
                "key_return_status": "returned",
            },
        )

    return InspectionResponse(inspection=InspectionRecord(**item))


@app.post("/inspections/{inspection_id}/convert-to-work-order")
def convert_inspection_item_to_work_order_route(
    inspection_id: str,
    request: InspectionWorkOrderConversionRequest,
    background_tasks: BackgroundTasks,
):
    """Convert an inspection deficiency item directly into a maintenance work order."""
    try:
        wo = db_utils.convert_inspection_item_to_work_order(
            insp_id=inspection_id,
            item_id=request.item_id,
            title=request.title,
            category=request.category,
            priority=request.priority,
            assigned_to=request.assigned_to or "",
            scheduled_date=request.scheduled_date or "",
        )
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    background_tasks.add_task(
        webhooks.dispatch_event,
        "work_order.created",
        {
            "work_order_id": wo["id"],
            "unit_id": wo["unit_id"],
            "tenant_id": wo["tenant_id"],
            "title": wo["title"],
            "category": wo["category"],
            "priority": wo["priority"],
            "status": wo["status"],
            "inspection_id": inspection_id,
        },
    )

    return {
        "status": "converted",
        "work_order": wo,
        "inspection_id": inspection_id,
        "item_id": request.item_id,
    }


@app.post(
    "/inspections/{inspection_id}/publish-document",
    response_model=InspectionDocumentPublishResponse,
)
def publish_inspection_document_route(
    inspection_id: str,
    request: InspectionDocumentPublishRequest,
):
    """Synthesize Markdown condition report and deposit settlement into RAG vector store."""
    try:
        result = inspections.publish_inspection_document(
            inspection_id=inspection_id,
            collection=request.collection,
            chunking_strategy=request.chunking_strategy,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
        )
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return InspectionDocumentPublishResponse(**result)


@app.post(
    "/sessions/{session_id}/create-inspection",
    response_model=InspectionResponse,
    status_code=201,
)
def create_session_inspection_route(
    session_id: str,
    request: SessionInspectionCreateRequest,
    background_tasks: BackgroundTasks,
):
    """Schedule a 1-click inspection from active support session for linked resident."""
    context = db_utils.get_session_tenant_context(session_id)
    if not context or not context.get("tenant"):
        raise HTTPException(
            status_code=400,
            detail=f"Session '{session_id}' has no linked tenant to schedule inspection for.",
        )
    tenant = context["tenant"]
    resolved_tenant_id = tenant["id"]
    resolved_unit_id = tenant.get("unit_id")

    try:
        item = db_utils.create_inspection(
            tenant_id=resolved_tenant_id,
            unit_id=resolved_unit_id,
            inspection_type=request.inspection_type,
            scheduled_date=request.scheduled_date,
            inspector_name=request.inspector_name,
            overall_condition=request.overall_condition,
            notes=request.notes,
            session_id=session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    background_tasks.add_task(
        webhooks.dispatch_event,
        "inspection.scheduled",
        {
            "inspection_id": item["id"],
            "tenant_id": item["tenant_id"],
            "unit_id": item["unit_id"],
            "session_id": session_id,
            "inspection_type": item["inspection_type"],
            "scheduled_date": item["scheduled_date"],
            "status": item["status"],
            "inspector_name": item["inspector_name"],
        },
    )

    return InspectionResponse(inspection=InspectionRecord(**item))


@app.get("/tenants/{tenant_id}/inspections", response_model=InspectionListResponse)
def get_tenant_inspections_route(tenant_id: str):
    """Retrieve all inspections associated with a specific resident."""
    tenant = db_utils.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=404,
            detail=f"Tenant '{tenant_id}' not found.",
        )
    items, total = db_utils.list_inspections(tenant_id=tenant_id, limit=100)
    return InspectionListResponse(
        items=[InspectionRecord(**r) for r in items],
        total=total,
        limit=100,
        offset=0,
    )


@app.get("/units/{unit_id}/inspections", response_model=InspectionListResponse)
def get_unit_inspections_route(unit_id: str):
    """Retrieve all inspections associated with a specific property unit."""
    unit = db_utils.get_unit(unit_id)
    if not unit:
        raise HTTPException(
            status_code=404,
            detail=f"Unit '{unit_id}' not found.",
        )
    items, total = db_utils.list_inspections(unit_id=unit_id, limit=100)
    return InspectionListResponse(
        items=[InspectionRecord(**r) for r in items],
        total=total,
        limit=100,
        offset=0,
    )


# --- Maintenance Vendor Directory & Dispatch Endpoints ---


@app.post("/vendors", response_model=VendorResponse, status_code=201)
def create_vendor_route(request: VendorCreateRequest):
    """Register a maintenance vendor in the directory."""
    try:
        created = vendors.create_vendor(
            name=request.name,
            trade=request.trade,
            contact_name=request.contact_name,
            email=request.email,
            phone=request.phone,
            hourly_rate=request.hourly_rate,
            status=request.status,
            notes=request.notes,
            vendor_id=request.id,
        )
    except ValueError as exc:
        status_code = 409 if "already exists" in str(exc).lower() else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return VendorResponse(vendor=VendorItem(**created))


@app.get("/vendors/metrics", response_model=VendorMetricsResponse)
def get_vendor_metrics_route():
    """Retrieve vendor directory, dispatch, rating and spend metrics."""
    return VendorMetricsResponse(**vendors.get_vendor_summary_metrics())


@app.get("/vendors", response_model=VendorListResponse)
def list_vendors_route(
    trade: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List vendors with optional trade, status and search filters."""
    items, total = vendors.list_vendors(
        trade=trade, status=status, search=search, limit=limit, offset=offset
    )
    return VendorListResponse(
        items=[VendorItem(**item) for item in items], total=total, limit=limit, offset=offset
    )


@app.get("/vendors/{vendor_id}", response_model=VendorResponse)
def get_vendor_route(vendor_id: str):
    """Retrieve a specific vendor."""
    item = vendors.get_vendor(vendor_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Vendor '{vendor_id}' not found.")
    return VendorResponse(vendor=VendorItem(**item))


@app.patch("/vendors/{vendor_id}", response_model=VendorResponse)
def update_vendor_route(vendor_id: str, request: VendorUpdateRequest):
    """Update fields on an existing vendor."""
    try:
        updated = vendors.update_vendor(vendor_id, **request.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail=f"Vendor '{vendor_id}' not found.")
    return VendorResponse(vendor=VendorItem(**updated))


@app.delete("/vendors/{vendor_id}")
def delete_vendor_route(vendor_id: str):
    """Delete a vendor and its dispatch history."""
    if not vendors.delete_vendor(vendor_id):
        raise HTTPException(status_code=404, detail=f"Vendor '{vendor_id}' not found.")
    return {"status": "deleted", "vendor_id": vendor_id}


def _dispatch_error_status(exc: ValueError) -> int:
    message = str(exc).lower()
    if "not found" in message:
        return 404
    if "already has an active dispatch" in message or "cannot be" in message:
        return 409
    return 422


@app.post(
    "/work-orders/{work_order_id}/dispatch-vendor",
    response_model=VendorDispatchResponse,
    status_code=201,
)
def dispatch_vendor_route(
    work_order_id: str,
    request: VendorDispatchRequest,
    background_tasks: BackgroundTasks,
):
    """Dispatch an open maintenance work order to an active vendor."""
    try:
        created = vendors.dispatch_vendor(
            work_order_id,
            request.vendor_id,
            agreed_cost=request.agreed_cost,
            scheduled_date=request.scheduled_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=_dispatch_error_status(exc), detail=str(exc)) from exc

    background_tasks.add_task(
        webhooks.dispatch_event,
        "vendor.dispatched",
        {
            "dispatch_id": created["id"],
            "vendor_id": created["vendor_id"],
            "work_order_id": created["work_order_id"],
            "agreed_cost": created["agreed_cost"],
        },
    )
    return VendorDispatchResponse(dispatch=VendorDispatchItem(**created))


@app.post("/vendor-dispatches/{dispatch_id}/complete", response_model=VendorDispatchResponse)
def complete_vendor_dispatch_route(
    dispatch_id: str,
    request: VendorDispatchCompleteRequest,
    background_tasks: BackgroundTasks,
):
    """Complete a vendor dispatch, recording final cost and rating and closing the work order."""
    try:
        completed = vendors.complete_dispatch(
            dispatch_id,
            final_cost=request.final_cost,
            rating=request.rating,
            feedback=request.feedback,
            resolution_notes=request.resolution_notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=_dispatch_error_status(exc), detail=str(exc)) from exc

    background_tasks.add_task(
        webhooks.dispatch_event,
        "vendor.job_completed",
        {
            "dispatch_id": completed["id"],
            "vendor_id": completed["vendor_id"],
            "work_order_id": completed["work_order_id"],
            "final_cost": completed["final_cost"],
            "rating": completed["rating"],
        },
    )
    return VendorDispatchResponse(dispatch=VendorDispatchItem(**completed))


@app.get("/vendors/{vendor_id}/dispatches", response_model=VendorDispatchListResponse)
def list_vendor_dispatches_route(
    vendor_id: str,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List the dispatch history of a vendor."""
    if not vendors.get_vendor(vendor_id):
        raise HTTPException(status_code=404, detail=f"Vendor '{vendor_id}' not found.")
    items, total = vendors.list_dispatches(
        vendor_id=vendor_id, status=status, limit=limit, offset=offset
    )
    return VendorDispatchListResponse(
        items=[VendorDispatchItem(**item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get(
    "/work-orders/{work_order_id}/dispatches",
    response_model=VendorDispatchListResponse,
)
def list_work_order_dispatches_route(
    work_order_id: str,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List dispatches associated with a specific work order."""
    if not db_utils.get_work_order(work_order_id):
        raise HTTPException(
            status_code=404, detail=f"Work order '{work_order_id}' not found."
        )
    items, total = vendors.list_dispatches(
        work_order_id=work_order_id, status=status, limit=limit, offset=offset
    )
    return VendorDispatchListResponse(
        items=[VendorDispatchItem(**item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# Resident Packages & Parcel Delivery Lockers (v0.42.0)
# ---------------------------------------------------------------------------


@app.post("/packages", response_model=PackageResponse, status_code=201)
def create_package_route(
    request: PackageCreateRequest,
    background_tasks: BackgroundTasks,
):
    """Log an incoming package delivery into parcel locker management."""
    if not db_utils.get_tenant(request.tenant_id):
        raise HTTPException(status_code=404, detail=f"Tenant '{request.tenant_id}' not found.")
    if not db_utils.get_unit(request.unit_id):
        raise HTTPException(status_code=404, detail=f"Unit '{request.unit_id}' not found.")

    try:
        created = packages.create_package(
            tenant_id=request.tenant_id,
            unit_id=request.unit_id,
            carrier=request.carrier,
            tracking_number=request.tracking_number,
            pickup_pin=request.pickup_pin,
            location=request.location,
            notes=request.notes,
            delivered_at=request.delivered_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    background_tasks.add_task(
        webhooks.dispatch_event,
        "package.delivered",
        {
            "package_id": created["id"],
            "tenant_id": created["tenant_id"],
            "unit_id": created["unit_id"],
            "carrier": created["carrier"],
            "tracking_number": created["tracking_number"],
            "location": created["location"],
            "delivered_at": created["delivered_at"],
        },
    )
    return PackageResponse(package=PackageItem(**created))


@app.get("/packages/metrics", response_model=PackageMetricsResponse)
def get_package_metrics_route():
    """Retrieve parcel locker occupancy, carrier breakdown, and turnaround metrics."""
    return PackageMetricsResponse(**packages.get_package_summary_metrics())


@app.get("/packages", response_model=PackageListResponse)
def list_packages_route(  # noqa: PLR0913, PLR0917
    tenant_id: str | None = None,
    unit_id: str | None = None,
    carrier: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List and filter resident packages."""
    items = packages.list_packages(
        tenant_id=tenant_id,
        unit_id=unit_id,
        carrier=carrier,
        status=status,
        search=search,
        limit=limit,
        offset=offset,
    )
    total = packages.count_packages(
        tenant_id=tenant_id,
        unit_id=unit_id,
        carrier=carrier,
        status=status,
        search=search,
    )
    return PackageListResponse(
        items=[PackageItem(**item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get("/packages/{package_id}", response_model=PackageResponse)
def get_package_route(package_id: str):
    """Retrieve details for a specific package."""
    pkg = packages.get_package(package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail=f"Package '{package_id}' not found.")
    return PackageResponse(package=PackageItem(**pkg))


@app.patch("/packages/{package_id}", response_model=PackageResponse)
def update_package_route(package_id: str, request: PackageUpdateRequest):
    """Update location, notes, or status for an existing package."""
    updated = packages.update_package(
        package_id,
        location=request.location,
        notes=request.notes,
        status=request.status,
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Package '{package_id}' not found.")
    return PackageResponse(package=PackageItem(**updated))


@app.delete("/packages/{package_id}")
def delete_package_route(package_id: str):
    """Delete a package record from parcel locker storage."""
    if not packages.delete_package(package_id):
        raise HTTPException(status_code=404, detail=f"Package '{package_id}' not found.")
    return {"status": "deleted", "package_id": package_id}


@app.post("/packages/{package_id}/pickup", response_model=PackageResponse)
def pickup_package_route(
    package_id: str,
    request: PackagePickupRequest,
    background_tasks: BackgroundTasks,
):
    """Verify resident pickup PIN and release package from parcel locker."""
    try:
        updated = packages.pickup_package(
            package_id,
            request.pickup_pin,
            picked_up_at=request.picked_up_at,
        )
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc

    background_tasks.add_task(
        webhooks.dispatch_event,
        "package.picked_up",
        {
            "package_id": updated["id"],
            "tenant_id": updated["tenant_id"],
            "unit_id": updated["unit_id"],
            "carrier": updated["carrier"],
            "tracking_number": updated["tracking_number"],
            "picked_up_at": updated["picked_up_at"],
        },
    )
    return PackageResponse(package=PackageItem(**updated))


@app.get("/tenants/{tenant_id}/packages", response_model=PackageListResponse)
def list_tenant_packages_route(
    tenant_id: str,
    pending_only: bool = False,
):
    """List packages for a specific resident."""
    if not db_utils.get_tenant(tenant_id):
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found.")
    items = packages.list_tenant_packages(tenant_id, pending_only=pending_only)
    return PackageListResponse(
        items=[PackageItem(**item) for item in items],
        total=len(items),
        limit=len(items),
        offset=0,
    )


@app.post("/sessions/{session_id}/intake-package", response_model=PackageResponse, status_code=201)
def session_intake_package_route(
    session_id: str,
    request: SessionIntakePackageRequest,
    background_tasks: BackgroundTasks,
):
    """Log package intake directly for the resident linked to an active support session."""
    context = db_utils.get_session_tenant_context(session_id)
    if not context or not context.get("tenant"):
        raise HTTPException(
            status_code=400,
            detail=f"Session '{session_id}' has no linked tenant to intake package for.",
        )
    tenant = context["tenant"]
    resolved_tenant_id = tenant["id"]
    resolved_unit_id = tenant.get("unit_id")
    if not resolved_unit_id:
        raise HTTPException(
            status_code=400,
            detail=f"Tenant '{resolved_tenant_id}' has no assigned unit.",
        )

    try:
        created = packages.create_package(
            tenant_id=resolved_tenant_id,
            unit_id=resolved_unit_id,
            carrier=request.carrier,
            tracking_number=request.tracking_number,
            pickup_pin=request.pickup_pin,
            location=request.location,
            notes=request.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    background_tasks.add_task(
        webhooks.dispatch_event,
        "package.delivered",
        {
            "package_id": created["id"],
            "tenant_id": created["tenant_id"],
            "unit_id": created["unit_id"],
            "carrier": created["carrier"],
            "tracking_number": created["tracking_number"],
            "location": created["location"],
            "delivered_at": created["delivered_at"],
        },
    )
    return PackageResponse(package=PackageItem(**created))
