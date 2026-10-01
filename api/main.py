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

from api import webhooks
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
    create_webhook,
    delete_document_record,
    delete_document_source,
    delete_document_sources_by_collection,
    delete_documents_by_collection,
    delete_session,
    delete_sessions,
    delete_webhook,
    get_all_collections,
    get_all_documents,
    get_all_sessions,
    get_chat_history,
    get_collections_details,
    get_document_by_hash,
    get_document_record,
    get_document_source,
    get_feedback_analytics,
    get_library_stats,
    get_session_feedback,
    get_session_metadata,
    get_support_triage_analytics,
    get_webhook,
    get_webhook_delivery_logs,
    insert_application_logs,
    insert_document_record,
    insert_feedback,
    list_feedback,
    list_webhooks,
    normalize_session_label,
    ping_db,
    prune_sessions_before,
    rename_collection,
    rename_session,
    save_document_source,
    search_sessions,
    truncate_history,
    update_session_metadata,
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
    BulkDeleteFileRequest,
    BulkDeleteFileResult,
    BulkDeleteResponse,
    BulkDeleteSessionRequest,
    BulkDeleteSessionResponse,
    BulkDeleteSessionResult,
    BulkUploadItem,
    BulkUploadResponse,
    ChatMessage,
    CollectionAnalyticsResponse,
    CollectionDetailResponse,
    CollectionRechunkRequest,
    CollectionRechunkResponse,
    ConfigResponse,
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
    HealthResponse,
    PruneSessionsResponse,
    QueryInput,
    QueryResponse,
    QuotaInfo,
    RechunkDocumentRequest,
    RenameCollectionRequest,
    RenameCollectionResponse,
    SearchInput,
    SearchResponse,
    SessionInfo,
    SessionSearchResponse,
    SessionSearchResult,
    SessionSummaryRequest,
    SessionSummaryResponse,
    StatsResponse,
    SupportTriageAnalyticsResponse,
    TagCount,
    UpdateSessionRequest,
    UploadDocumentResponse,
    WebhookCreateRequest,
    WebhookDeliveryLogItem,
    WebhookDeliveryLogsResponse,
    WebhookPingResponse,
    WebhookResponse,
    WebhookUpdateRequest,
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
    return QuotaInfo(
        budget=budget, used=used, remaining=max(0, budget - used), unlimited=False
    )


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
    try:
        result = rag_chain.invoke({"input": query_input.question, "chat_history": chat_history})
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
    try:
        async for chunk in rag_chain.astream(
            {"input": query_input.question, "chat_history": chat_history}
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
                BulkUploadItem(
                    filename=filename, status="indexed", file_id=response.file_id
                )
            )
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            results.append(
                BulkUploadItem(filename=filename, status="error", detail=detail)
            )
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
        raise HTTPException(
            status_code=404, detail=f"Collection {source} was not found."
        )

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
        raise HTTPException(
            status_code=404, detail=f"Collection {collection_name} was not found."
        )

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
def list_sessions(status: str | None = None, tag: str | None = None):
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
    if status is not None or tag is not None:
        return get_all_sessions(status=status, tag=tag)
    return get_all_sessions()


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
            and request.tags is None
            and request.summary is None
            and request.resolution_notes is None
            and request.label is not None
        ):
            label = normalize_session_label(request.label)
            updated = rename_session(session_id, label)
        else:
            updated = update_session_metadata(
                session_id,
                label=request.label,
                status=request.status,
                tags=request.tags,
                summary=request.summary,
                resolution_notes=request.resolution_notes,
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
def summarize_session_route(
    session_id: str, request: SessionSummaryRequest | None = None
):
    _require_session_id(session_id)
    history = get_chat_history(session_id)
    if not history:
        raise HTTPException(status_code=404, detail=f"Session {session_id} was not found.")

    req = request or SessionSummaryRequest()
    summary_data = summarize_dialogue(history, model=req.model)

    saved = False
    if req.save_summary and summary_data.get("summary"):
        meta = get_session_metadata(session_id) or {}
        existing_tags = [
            t.strip() for t in (meta.get("tags") or "").split(",") if t.strip()
        ]
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

