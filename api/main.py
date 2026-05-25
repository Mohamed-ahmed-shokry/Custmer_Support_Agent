import logging
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
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
from api.langchain_utils import get_rag_chain
from api.db_utils import insert_application_logs, get_chat_history, get_all_documents, insert_document_record, delete_document_record
from api.chroma_utils import index_document_to_chroma, delete_doc_from_chroma
from api.settings import settings

logging.basicConfig(filename='app.log', level=logging.INFO)
app = FastAPI(
    title=settings.app_name,
    description="Document-grounded customer support assistant API.",
    version=settings.app_version,
)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".html"}


def sanitize_filename(filename: str) -> str:
    cleaned = filename.replace("\\", "/")
    return Path(cleaned).name.replace("\x00", "").strip()


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


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", app=settings.app_name, version=settings.app_version)

@app.post("/chat", response_model=QueryResponse)
def chat(query_input: QueryInput):
    session_id = query_input.session_id
    logging.info(f"Session ID: {session_id}, User Query: {query_input.question}, Model: {query_input.model.value}")
    if not session_id:
        session_id = str(uuid.uuid4())

    

    chat_history = get_chat_history(session_id)
    rag_chain = get_rag_chain(query_input.model.value)
    result = rag_chain.invoke({
        "input": query_input.question,
        "chat_history": chat_history
    })
    answer = result["answer"]
    sources = build_sources(result.get("context"))
    
    insert_application_logs(session_id, query_input.question, answer, query_input.model.value)
    logging.info(f"Session ID: {session_id}, AI Response: {answer}")
    return QueryResponse(answer=answer, session_id=session_id, model=query_input.model, sources=sources)

@app.post("/upload-doc", response_model=UploadDocumentResponse)
def upload_and_index_document(file: UploadFile = File(...)):
    safe_filename = sanitize_filename(file.filename or "")
    file_extension = os.path.splitext(safe_filename)[1].lower()
    
    if not safe_filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")

    if file_extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed types are: {allowed}")
    
    temp_file_path = None
    
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as buffer:
            shutil.copyfileobj(file.file, buffer)
            temp_file_path = buffer.name
        
        file_id = insert_document_record(safe_filename)
        success = index_document_to_chroma(temp_file_path, file_id, safe_filename)
        
        if success:
            return UploadDocumentResponse(message=f"File {safe_filename} has been successfully uploaded and indexed.", file_id=file_id)

        delete_document_record(file_id)
        raise HTTPException(status_code=500, detail=f"Failed to index {safe_filename}.")
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)

@app.get("/list-docs", response_model=list[DocumentInfo])
def list_documents():
    return get_all_documents()

@app.post("/delete-doc", response_model=DeleteDocumentResponse)
def delete_document(request: DeleteFileRequest):
    chroma_delete_success = delete_doc_from_chroma(request.file_id)

    if not chroma_delete_success:
        raise HTTPException(status_code=500, detail=f"Failed to delete document with file_id {request.file_id} from Chroma.")

    db_delete_success = delete_document_record(request.file_id)
    if not db_delete_success:
        raise HTTPException(status_code=500, detail=f"Deleted from Chroma but failed to delete document with file_id {request.file_id} from the database.")

    return DeleteDocumentResponse(message=f"Successfully deleted document with file_id {request.file_id} from the system.")
