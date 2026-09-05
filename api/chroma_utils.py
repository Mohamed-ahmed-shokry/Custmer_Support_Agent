import logging
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from langchain_chroma import Chroma
from langchain_community.document_loaders import (
    Docx2txtLoader,
    PyPDFLoader,
    TextLoader,
    UnstructuredHTMLLoader,
    UnstructuredMarkdownLoader,
)
from langchain_community.document_loaders.csv_loader import CSVLoader
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from api.settings import settings

if TYPE_CHECKING:
    from langchain_community.document_loaders.base import BaseLoader

logger = logging.getLogger(__name__)


class ChunkingStrategy(StrEnum):
    RECURSIVE = "recursive"
    MARKDOWN = "markdown"


_DEFAULT_CHUNK_SIZE = 1000
_DEFAULT_CHUNK_OVERLAP = 200


@dataclass
class ChunkingOptions:
    strategy: ChunkingStrategy = ChunkingStrategy.RECURSIVE
    chunk_size: int = _DEFAULT_CHUNK_SIZE
    chunk_overlap: int = _DEFAULT_CHUNK_OVERLAP


def _get_text_splitter(options: ChunkingOptions):
    if options.strategy == ChunkingStrategy.MARKDOWN:
        return MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "Header 1"),
                ("##", "Header 2"),
                ("###", "Header 3"),
            ]
        )
    return RecursiveCharacterTextSplitter(
        chunk_size=options.chunk_size,
        chunk_overlap=options.chunk_overlap,
        length_function=len,
    )


def get_vectorstore() -> Chroma:
    if not hasattr(get_vectorstore, "_vectorstore"):
        embedding_function = OpenAIEmbeddings()
        get_vectorstore._vectorstore = Chroma(  # type: ignore[attr-defined]
            persist_directory=settings.chroma_persist_dir,
            embedding_function=embedding_function,
        )
    return get_vectorstore._vectorstore  # type: ignore[attr-defined, no-any-return]


def load_and_split_document(
    file_path: str,
    options: ChunkingOptions | None = None,
) -> list[Document]:
    if options is None:
        options = ChunkingOptions()

    loader: BaseLoader
    if file_path.endswith(".pdf"):
        loader = PyPDFLoader(file_path)
    elif file_path.endswith(".docx"):
        loader = Docx2txtLoader(file_path)
    elif file_path.endswith(".html"):
        loader = UnstructuredHTMLLoader(file_path)
    elif file_path.endswith(".md"):
        loader = UnstructuredMarkdownLoader(file_path)
    elif file_path.endswith(".txt"):
        loader = TextLoader(file_path, encoding="utf-8")
    elif file_path.endswith(".csv"):
        loader = CSVLoader(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_path}")

    documents = loader.load()
    splitter = _get_text_splitter(options)
    return splitter.split_documents(documents)  # type: ignore[no-any-return]


def build_chroma_document_ids(file_id: int, chunk_count: int) -> list[str]:
    return [f"{file_id}:{index}" for index in range(chunk_count)]


def index_document_to_chroma(
    file_path: str,
    file_id: int,
    filename: str | None = None,
    options: ChunkingOptions | None = None,
) -> bool:
    if options is None:
        options = ChunkingOptions()

    try:
        splits = load_and_split_document(file_path, options)
        if not splits:
            logger.warning("Document %s produced no chunks for indexing", file_path)
            return False

        source_name = filename or Path(file_path).name

        for index, split in enumerate(splits):
            split.metadata["file_id"] = file_id
            split.metadata["filename"] = source_name
            split.metadata["chunk_index"] = index

        document_ids = build_chroma_document_ids(file_id, len(splits))
        _add_documents_with_retry(get_vectorstore(), splits, document_ids, file_path)
        return True
    except Exception:
        logger.exception("Error indexing document %s", file_path)
        return False


INDEX_MAX_ATTEMPTS = 3
INDEX_RETRY_BASE_DELAY_S = 0.5


def _add_documents_with_retry(vectorstore, splits, document_ids, file_path: str) -> None:
    """Persist chunks with exponential backoff on transient failures."""
    last_error: Exception | None = None
    for attempt in range(1, INDEX_MAX_ATTEMPTS + 1):
        try:
            vectorstore.add_documents(splits, ids=document_ids)
            return
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Indexing attempt %s/%s failed for %s",
                attempt,
                INDEX_MAX_ATTEMPTS,
                file_path,
            )
            if attempt < INDEX_MAX_ATTEMPTS:
                time.sleep(INDEX_RETRY_BASE_DELAY_S * (2 ** (attempt - 1)))
    if last_error is not None:
        raise last_error


def delete_doc_from_chroma(file_id: int):
    try:
        vectorstore = get_vectorstore()
        docs = vectorstore.get(where={"file_id": file_id})
        document_ids = docs.get("ids", [])
        chunk_count = len(document_ids)
        logger.info("Found %s document chunks for file_id %s", chunk_count, file_id)

        if not document_ids:
            return True

        vectorstore.delete(ids=document_ids)
        logger.info("Deleted all documents with file_id %s", file_id)

        return True
    except Exception:
        logger.exception("Error deleting document with file_id %s from Chroma", file_id)
        return False


def get_hybrid_retriever(
    k: int = 5,
    file_ids: list[int] | None = None,
    bm25_weight: float = 0.5,
    vector_weight: float = 0.5,
):
    """Create a hybrid retriever combining BM25 and vector search.

    Imports are lazy because ``langchain.retrievers`` pulls in legacy
    ``Chain`` classes that are incompatible with Python 3.14 + pydantic.
    Falls back to pure vector search when BM25/ensemble is unavailable.
    """
    vectorstore = get_vectorstore()
    vector_filter = {"file_id": {"$in": file_ids}} if file_ids else None
    vector_retriever = vectorstore.as_retriever(
        search_kwargs={"k": k, **({"filter": vector_filter} if vector_filter else {})}
    )

    try:
        from langchain_community.retrievers import BM25Retriever  # noqa: PLC0415

        all_docs = vectorstore.get()
        if not all_docs.get("documents"):
            return vector_retriever
        documents = [
            Document(page_content=doc, metadata=meta or {})
            for doc, meta in zip(
                all_docs["documents"], all_docs.get("metadatas") or [], strict=False
            )
        ]
        if file_ids:
            documents = [d for d in documents if d.metadata.get("file_id") in file_ids]
        if not documents:
            return vector_retriever
        bm25_retriever = BM25Retriever.from_documents(documents)
        bm25_retriever.k = k
    except Exception:
        logger.exception("BM25 retriever unavailable, falling back to vector search")
        return vector_retriever

    try:
        from langchain.retrievers import EnsembleRetriever  # noqa: PLC0415

        return EnsembleRetriever(
            retrievers=[bm25_retriever, vector_retriever],
            weights=[bm25_weight, vector_weight],
        )
    except Exception:
        logger.exception("EnsembleRetriever unavailable, falling back to vector search")
        return vector_retriever


def get_filtered_retriever(
    k: int = 5,
    file_ids: list[int] | None = None,
    source_filter: str | None = None,
):
    """Create a retriever with metadata filtering."""
    vectorstore = get_vectorstore()
    filter_dict: dict[str, Any] = {}
    if file_ids:
        filter_dict["file_id"] = {"$in": file_ids}
    if source_filter:
        filter_dict["filename"] = {"$eq": source_filter}

    search_kwargs: dict[str, Any] = {"k": k}
    if filter_dict:
        search_kwargs["filter"] = filter_dict

    return vectorstore.as_retriever(search_kwargs=search_kwargs)


def select_retriever(  # noqa: PLR0913, PLR0917 - explicit retriever options
    k: int = 5,
    file_ids: list[int] | None = None,
    source_filename: str | None = None,
    use_hybrid: bool = False,
    bm25_weight: float = 0.5,
    vector_weight: float = 0.5,
):
    """Pick vector / filtered / hybrid retriever based on request flags."""
    if use_hybrid:
        return get_hybrid_retriever(
            k=k,
            file_ids=file_ids,
            bm25_weight=bm25_weight,
            vector_weight=vector_weight,
        )
    if file_ids or source_filename:
        return get_filtered_retriever(k=k, file_ids=file_ids, source_filter=source_filename)
    return get_vectorstore().as_retriever(search_kwargs={"k": k})
