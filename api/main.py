import logging
import os
import shutil
import tempfile
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from api.chroma_utils import (
    ChunkingOptions,
    ChunkingStrategy,
    delete_doc_from_chroma,
    index_document_to_chroma,
)
from api.db_utils import (
    delete_document_record,
    get_all_documents,
    get_chat_history,
    get_document_record,
    insert_application_logs,
    insert_document_record,
)
from api.pydantic_models import (
    DeleteDocumentResponse,
    DeleteFileRequest,
    DocumentInfo,
    HealthResponse,
    QueryInput,
    QueryResponse,
    SourceInfo,
    UploadDocumentResponse,
)
from api.settings import settings

logging.basicConfig(filename="app.log", level=logging.INFO)
logger = logging.getLogger(__name__)
app = FastAPI(
    title=settings.app_name,
    description="Document-grounded customer support assistant API.",
    version=settings.app_version,
)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".html", ".md", ".txt", ".csv"}


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
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
):
    # ruff: noqa: PLC0415 - lazy import required for Python 3.14 compatibility
    from api.langchain_utils import get_rag_chain

    return get_rag_chain(
        model,
        file_ids=file_ids,
        source_filename=source_filename,
        use_hybrid=use_hybrid,
    )


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", app=settings.app_name, version=settings.app_version)


@app.post("/chat", response_model=QueryResponse)
def chat(query_input: QueryInput):
    session_id = query_input.session_id
    logger.info(
        "Session ID: %s, User Query: %s, Model: %s",
        session_id,
        query_input.question,
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
    )
    try:
        result = rag_chain.invoke({"input": query_input.question, "chat_history": chat_history})
    except Exception as exc:
        logger.exception("RAG chain failed for session_id %s", session_id)
        raise HTTPException(
            status_code=502, detail="Failed to generate a response from the retrieval pipeline."
        ) from exc

    answer = result.get("answer") if isinstance(result, dict) else None
    if not isinstance(answer, str):
        logger.error("RAG chain returned an invalid response for session_id %s", session_id)
        raise HTTPException(
            status_code=502, detail="The retrieval pipeline returned an invalid response."
        )

    sources = build_sources(result.get("context"))

    insert_application_logs(session_id, query_input.question, answer, query_input.model.value)
    logger.info("Session ID: %s, AI Response: %s", session_id, answer)
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
                    import json

                    source_data = json.dumps([s.model_dump() for s in sources])
                    yield f"event: sources\ndata: {source_data}\n\n"
    except Exception:
        logger.exception("RAG chain streaming failed for session_id %s", session_id)
        yield "event: error\ndata: Failed to generate response\n\n"


@app.post("/chat/stream")
async def chat_stream(query_input: QueryInput):
    session_id = query_input.session_id
    logger.info(
        "Stream Session ID: %s, User Query: %s, Model: %s",
        session_id,
        query_input.question,
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
            logger.info("Stream Session ID: %s, AI Response: %s", session_id, full_answer)

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

        file_id = insert_document_record(safe_filename)
        success = index_document_to_chroma(
            temp_file_path,
            file_id,
            safe_filename,
            options=options,
        )

        if success:
            return UploadDocumentResponse(
                message=f"File {safe_filename} has been successfully uploaded and indexed.",
                file_id=file_id,
            )

        if not delete_document_record(file_id):
            logger.warning(
                "Failed to remove document metadata after indexing failed for file_id %s", file_id
            )
        raise HTTPException(status_code=500, detail=f"Failed to index {safe_filename}.")
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)


@app.get("/list-docs", response_model=list[DocumentInfo])
def list_documents():
    return get_all_documents()


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

    return DeleteDocumentResponse(
        message=f"Successfully deleted document with file_id {request.file_id} from the system."
    )
