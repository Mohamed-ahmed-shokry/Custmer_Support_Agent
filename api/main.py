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

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from api.chroma_utils import (
    ChunkingOptions,
    ChunkingStrategy,
    delete_collection_from_chroma,
    delete_doc_from_chroma,
    index_document_to_chroma,
    rename_collection_in_chroma,
    select_retriever,
)
from api.collections import DEFAULT_COLLECTION, normalize_collection
from api.db_utils import (
    delete_document_record,
    delete_documents_by_collection,
    delete_session,
    get_all_collections,
    get_all_documents,
    get_all_sessions,
    get_chat_history,
    get_document_by_hash,
    get_document_record,
    get_library_stats,
    insert_application_logs,
    insert_document_record,
    insert_feedback,
    normalize_session_label,
    ping_db,
    prune_sessions_before,
    rename_collection,
    rename_session,
    truncate_history,
)
from api.observability import (
    estimate_tokens,
    increment,
    record_latency,
    render_prometheus,
    snapshot,
)
from api.pii import redact_pii
from api.presenters import build_search_hits, build_sources, render_session_markdown
from api.pydantic_models import (
    BulkUploadItem,
    BulkUploadResponse,
    ChatMessage,
    DeleteDocumentResponse,
    DeleteFileRequest,
    DeleteSessionResponse,
    DocumentInfo,
    FeedbackInput,
    FeedbackResponse,
    HealthResponse,
    PruneSessionsResponse,
    QueryInput,
    QueryResponse,
    QuotaInfo,
    RenameCollectionRequest,
    RenameCollectionResponse,
    RenameSessionRequest,
    SearchInput,
    SearchResponse,
    SessionInfo,
    StatsResponse,
    UploadDocumentResponse,
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


def configure_logging() -> None:
    level = getattr(logging, settings.log_level, logging.INFO)
    handler = logging.FileHandler("app.log")
    if settings.log_format == "json":
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


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
    if path == "/upload-doc":
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
    )


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", app=settings.app_name, version=settings.app_version)


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
    from fastapi.responses import JSONResponse  # noqa: PLC0415 - keep import lazy

    return JSONResponse(status_code=status_code, content={"ready": ready, "checks": checks})


@app.get("/metrics")
def metrics():
    from fastapi.responses import PlainTextResponse  # noqa: PLC0415 - keep import lazy

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
    )
    try:
        result = rag_chain.invoke({"input": query_input.question, "chat_history": chat_history})
    except Exception as exc:
        increment("chat_errors")
        logger.exception("RAG chain failed for session_id %s", session_id)
        raise HTTPException(
            status_code=502, detail="Failed to generate a response from the retrieval pipeline."
        ) from exc

    answer = result.get("answer") if isinstance(result, dict) else None
    if not isinstance(answer, str):
        increment("chat_errors")
        logger.error("RAG chain returned an invalid response for session_id %s", session_id)
        raise HTTPException(
            status_code=502, detail="The retrieval pipeline returned an invalid response."
        )

    sources = build_sources(result.get("context"))

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
    )
    try:
        documents = retriever.invoke(search_input.question)
    except Exception as exc:
        logger.exception("Retrieval failed for search")
        raise HTTPException(
            status_code=502, detail="Failed to retrieve documents for the query."
        ) from exc
    increment("prompt_tokens_est", question_tokens)
    record_token_usage(client_ip, question_tokens)
    return SearchResponse(hits=build_search_hits(documents))


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
    )
    try:
        async for chunk in rag_chain.astream(
            {"input": query_input.question, "chat_history": chat_history}
        ):
            if "answer" in chunk:
                yield f"data: {chunk['answer']}\n\n"
            elif "context" in chunk:
                sources = build_sources(chunk["context"])
                if sources:
                    source_data = json.dumps([s.model_dump() for s in sources])
                    yield f"event: sources\ndata: {source_data}\n\n"
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


@app.get("/collections", response_model=list[str])
def list_collections():
    return get_all_collections()


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

    increment("deletes")
    return DeleteDocumentResponse(
        message=(
            f"Deleted collection {collection_name}: "
            f"{db_documents} document(s), {chroma_chunks} chunk(s)."
        )
    )


@app.get("/sessions", response_model=list[SessionInfo])
def list_sessions():
    return get_all_sessions()


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
        raise HTTPException(
            status_code=404, detail=f"Session {session_id} was not found."
        )
    return summaries[0]


@app.get("/sessions/{session_id}/history", response_model=list[ChatMessage])
def session_history(session_id: str):
    _require_session_id(session_id)
    return [ChatMessage(**message) for message in get_chat_history(session_id)]


@app.get("/sessions/{session_id}/export")
def export_session(session_id: str):
    from fastapi.responses import PlainTextResponse  # noqa: PLC0415 - keep import lazy

    _require_session_id(session_id)
    history = get_chat_history(session_id)
    if not history:
        raise HTTPException(
            status_code=404, detail=f"Session {session_id} was not found."
        )
    label = _get_session_summary_or_404(session_id).get("label")
    markdown = render_session_markdown(session_id, label, history)
    return PlainTextResponse(
        markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{session_id}.md"'},
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
        raise HTTPException(
            status_code=404, detail=f"Session {session_id} was not found."
        )
    return DeleteSessionResponse(message=f"Session {session_id} deleted.")


@app.post("/feedback", response_model=FeedbackResponse)
def submit_feedback(feedback: FeedbackInput):
    if not get_chat_history(feedback.session_id):
        raise HTTPException(
            status_code=404, detail=f"Session {feedback.session_id} was not found."
        )
    feedback_id = insert_feedback(feedback.session_id, feedback.rating)
    increment("feedback_up" if feedback.rating == 1 else "feedback_down")
    return FeedbackResponse(message="Feedback recorded.", feedback_id=feedback_id)


@app.patch("/sessions/{session_id}", response_model=SessionInfo)
def rename_session_route(session_id: str, request: RenameSessionRequest):
    _require_session_id(session_id)
    try:
        label = normalize_session_label(request.label)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not rename_session(session_id, label):
        raise HTTPException(
            status_code=404, detail=f"Session {session_id} was not found."
        )
    return SessionInfo(**_get_session_summary_or_404(session_id))


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

    increment("deletes")
    return DeleteDocumentResponse(
        message=f"Successfully deleted document with file_id {request.file_id} from the system."
    )
