from api import chroma_utils
from langchain_core.documents import Document


class FakeVectorstore:
    def __init__(self, ids=None):
        self.added_documents = None
        self.added_ids = None
        self.deleted_ids = None
        self.ids = ids or []

    def add_documents(self, documents, ids=None):
        self.added_documents = documents
        self.added_ids = ids

    def get(self, where):
        assert where == {"file_id": 42}
        return {"ids": self.ids}

    def delete(self, ids):
        self.deleted_ids = ids


def test_build_chroma_document_ids_uses_file_id_and_chunk_index():
    assert chroma_utils.build_chroma_document_ids(file_id=42, chunk_count=3) == [
        "42:0",
        "42:1",
        "42:2",
    ]


def test_index_document_adds_metadata_and_deterministic_ids(monkeypatch):
    documents = [
        Document(page_content="First chunk", metadata={}),
        Document(page_content="Second chunk", metadata={"page": 2}),
    ]
    vectorstore = FakeVectorstore()

    monkeypatch.setattr(chroma_utils, "load_and_split_document", lambda file_path: documents)
    monkeypatch.setattr(chroma_utils, "get_vectorstore", lambda: vectorstore)

    assert (
        chroma_utils.index_document_to_chroma("upload.pdf", file_id=42, filename="lease.pdf")
        is True
    )
    assert vectorstore.added_ids == ["42:0", "42:1"]
    assert vectorstore.added_documents[0].metadata == {
        "file_id": 42,
        "filename": "lease.pdf",
        "chunk_index": 0,
    }
    assert vectorstore.added_documents[1].metadata == {
        "page": 2,
        "file_id": 42,
        "filename": "lease.pdf",
        "chunk_index": 1,
    }


def test_index_document_returns_false_when_document_has_no_chunks(monkeypatch):
    vectorstore = FakeVectorstore()

    monkeypatch.setattr(chroma_utils, "load_and_split_document", lambda file_path: [])
    monkeypatch.setattr(chroma_utils, "get_vectorstore", lambda: vectorstore)

    assert (
        chroma_utils.index_document_to_chroma("empty.pdf", file_id=42, filename="empty.pdf")
        is False
    )
    assert vectorstore.added_documents is None


def test_delete_doc_from_chroma_deletes_found_ids(monkeypatch):
    vectorstore = FakeVectorstore(ids=["42:0", "42:1"])

    monkeypatch.setattr(chroma_utils, "get_vectorstore", lambda: vectorstore)

    assert chroma_utils.delete_doc_from_chroma(42) is True
    assert vectorstore.deleted_ids == ["42:0", "42:1"]


def test_delete_doc_from_chroma_succeeds_when_no_chunks_exist(monkeypatch):
    vectorstore = FakeVectorstore(ids=[])

    monkeypatch.setattr(chroma_utils, "get_vectorstore", lambda: vectorstore)

    assert chroma_utils.delete_doc_from_chroma(42) is True
    assert vectorstore.deleted_ids is None
