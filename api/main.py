import json
import logging
import os
import shutil
import tempfile
import time
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from api.chroma_utils import (
    ChunkingOptions,
    ChunkingStrategy,
    delete_doc_from_chroma,
    index_document_to_chroma,
)
from api.collections import DEFAULT_COLLECTION, normalize_collection
from api.db_utils import (
    delete_document_record,
    get_all_collections,
    get_all_documents,
    get_all_sessions,
    get_chat_history,
    get_document_record,
    insert_application_logs,
    insert_document_record,
)
from api.observability import (
    estimate_tokens,
    increment,
    record_latency,
    render_prometheus,
    snapshot,
)
from api.pii import redact_pii
from api.pydantic_models import (
    ChatMessage,
    DeleteDocumentResponse,
    DeleteFileRequest,
    DocumentInfo,
    HealthResponse,
    QueryInput,
    QueryResponse,
    SessionInfo,
    SourceInfo,
    UploadDocumentResponse,
)
from api.security import check_api_key, check_rate_limit, is_public_path
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
                headers={"X-Request-ID": request_id},
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


def build_sources(documents) -> list[SourceInfo]:
    sources = []
    seen = set()
    for document in documents or []:
        metadata = document.metadata or {}
        key = (
            metadata.get("file_id"),
            metadata.get("filename") or metadata.get("source"),
            metadata.get("page"),
            metadata.get("chunk_index"),
        )
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            SourceInfo(
                file_id=metadata.get("file_id"),
                filename=metadata.get("filename") or metadata.get("source"),
                page=metadata.get("page"),
                chunk_index=metadata.get("chunk_index"),
                preview=document.page_content[:280].strip(),
            )
        )
    return sources


def get_rag_chain_for_model(
    model: str,
    file_ids: list[int] | None = None,
    source_filename: str | None = None,
    use_hybrid: bool | None = None,
    collections: list[str] | None = None,
):
    # ruff: noqa: PLC0415 - lazy import required for Python 3.14 compatibility
    from api.langchain_utils import get_rag_chain

    return get_rag_chain(
        model,
        file_ids=file_ids,
        source_filename=source_filename,
        use_hybrid=use_hybrid,
        collections=collections,
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
        get_all_documents()
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


@app.get("/metrics.json")
def metrics_json():
    return snapshot()


@app.post("/chat", response_model=QueryResponse)
def chat(query_input: QueryInput):
    increment("chat_requests")
    session_id = query_input.session_id
    logger.info(
        "Session ID: %s, User Query: %s, Model: %s",
        session_id,
        redact_pii(query_input.question),
        query_input.model.value,
    )
    if not session_id:
        session_id = str(uuid.uuid4())

    chat_history = get_chat_history(session_id)
    rag_chain = get_rag_chain_for_model(
        query_input.model.value,
        file_ids=query_input.file_ids,
        source_filename=query_input.source_filename,
        use_hybrid=query_input.use_hybrid,
        collections=query_input.collections,
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
    increment("prompt_tokens_est", estimate_tokens(query_input.question))
    increment("completion_tokens_est", estimate_tokens(answer))
    logger.info("Session ID: %s, AI Response: %s", session_id, redact_pii(answer))
    return QueryResponse(
        answer=answer, session_id=session_id, model=query_input.model, sources=sources
    )


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
async def chat_stream(query_input: QueryInput):
    increment("stream_requests")
    session_id = query_input.session_id
    logger.info(
        "Stream Session ID: %s, User Query: %s, Model: %s",
        session_id,
        redact_pii(query_input.question),
        query_input.model.value,
    )
    if not session_id:
        session_id = str(uuid.uuid4())

    chat_history = get_chat_history(session_id)

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
            increment("prompt_tokens_est", estimate_tokens(query_input.question))
            increment("completion_tokens_est", estimate_tokens(full_answer))
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


@app.post("/upload-doc", response_model=UploadDocumentResponse)
def upload_and_index_document(
    file: UploadFile = FILE_REQUIRED,
    chunking_strategy: ChunkingStrategy = ChunkingStrategy.RECURSIVE,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    collection: str = DEFAULT_COLLECTION,
):
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
    try:
        collection_name = normalize_collection(collection)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    options = ChunkingOptions(
        strategy=chunking_strategy, chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )

    temp_file_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as buffer:
            shutil.copyfileobj(file.file, buffer)
            temp_file_path = buffer.name

        if os.path.getsize(temp_file_path) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file cannot be empty.")
        validate_upload_size(os.path.getsize(temp_file_path))

        file_id = insert_document_record(safe_filename, collection_name)
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


@app.get("/list-docs", response_model=list[DocumentInfo])
def list_documents(collection: str | None = None):
    if collection is None:
        return get_all_documents()
    try:
        return get_all_documents(normalize_collection(collection))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/collections", response_model=list[str])
def list_collections():
    return get_all_collections()


@app.get("/sessions", response_model=list[SessionInfo])
def list_sessions():
    return get_all_sessions()


@app.get("/sessions/{session_id}/history", response_model=list[ChatMessage])
def session_history(session_id: str):
    if not session_id.strip():
        raise HTTPException(status_code=400, detail="session_id must not be empty.")
    return [ChatMessage(**message) for message in get_chat_history(session_id)]


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
