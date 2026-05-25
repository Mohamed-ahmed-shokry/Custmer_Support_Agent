from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader, UnstructuredHTMLLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from typing import List
from langchain_core.documents import Document
import os
from pathlib import Path
from api.settings import settings

text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200, length_function=len)
_vectorstore = None


def get_vectorstore():
    global _vectorstore
    if _vectorstore is None:
        embedding_function = OpenAIEmbeddings()
        _vectorstore = Chroma(persist_directory=settings.chroma_persist_dir, embedding_function=embedding_function)
    return _vectorstore

def load_and_split_document(file_path: str) -> List[Document]:
    if file_path.endswith('.pdf'):
        loader = PyPDFLoader(file_path)
    elif file_path.endswith('.docx'):
        loader = Docx2txtLoader(file_path)
    elif file_path.endswith('.html'):
        loader = UnstructuredHTMLLoader(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_path}")
    
    documents = loader.load()
    return text_splitter.split_documents(documents)

def index_document_to_chroma(file_path: str, file_id: int, filename: str | None = None) -> bool:
    try:
        splits = load_and_split_document(file_path)
        source_name = filename or Path(file_path).name
        
        for index, split in enumerate(splits):
            split.metadata["file_id"] = file_id
            split.metadata["filename"] = source_name
            split.metadata["chunk_index"] = index
        
        get_vectorstore().add_documents(splits)
        # vectorstore.persist()
        return True
    except Exception as e:
        print(f"Error indexing document: {e}")
        return False

def delete_doc_from_chroma(file_id: int):
    try:
        vectorstore = get_vectorstore()
        docs = vectorstore.get(where={"file_id": file_id})
        print(f"Found {len(docs['ids'])} document chunks for file_id {file_id}")
        
        vectorstore._collection.delete(where={"file_id": file_id})
        print(f"Deleted all documents with file_id {file_id}")
        
        return True
    except Exception as e:
        print(f"Error deleting document with file_id {file_id} from Chroma: {str(e)}")
        return False
