import logging
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_chroma import Chroma
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, UnstructuredHTMLLoader
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from api.settings import settings

if TYPE_CHECKING:
    from langchain_community.document_loaders.base import BaseLoader

logger = logging.getLogger(__name__)
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000, chunk_overlap=200, length_function=len
)


def get_vectorstore() -> Chroma:
    if not hasattr(get_vectorstore, "_vectorstore"):
        embedding_function = OpenAIEmbeddings()
        get_vectorstore._vectorstore = Chroma(  # type: ignore[attr-defined]
            persist_directory=settings.chroma_persist_dir,
            embedding_function=embedding_function,
        )
    return get_vectorstore._vectorstore  # type: ignore[attr-defined, no-any-return]


def load_and_split_document(file_path: str) -> list[Document]:
    loader: BaseLoader
    if file_path.endswith(".pdf"):
        loader = PyPDFLoader(file_path)
    elif file_path.endswith(".docx"):
        loader = Docx2txtLoader(file_path)
    elif file_path.endswith(".html"):
        loader = UnstructuredHTMLLoader(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_path}")

    documents = loader.load()
    return text_splitter.split_documents(documents)


def build_chroma_document_ids(file_id: int, chunk_count: int) -> list[str]:
    return [f"{file_id}:{index}" for index in range(chunk_count)]


def index_document_to_chroma(file_path: str, file_id: int, filename: str | None = None) -> bool:
    try:
        splits = load_and_split_document(file_path)
        if not splits:
            logger.warning("Document %s produced no chunks for indexing", file_path)
            return False

        source_name = filename or Path(file_path).name

        for index, split in enumerate(splits):
            split.metadata["file_id"] = file_id
            split.metadata["filename"] = source_name
            split.metadata["chunk_index"] = index

        get_vectorstore().add_documents(splits, ids=build_chroma_document_ids(file_id, len(splits)))
        # vectorstore.persist()
        return True
    except Exception:
        logger.exception("Error indexing document %s", file_path)
        return False


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
