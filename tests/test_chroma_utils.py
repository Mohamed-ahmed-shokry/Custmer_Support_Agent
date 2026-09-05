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

    def as_retriever(self, search_kwargs=None):
        self.search_kwargs = search_kwargs
        return ("retriever", search_kwargs)


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

    monkeypatch.setattr(
        chroma_utils, "load_and_split_document", lambda file_path, *args, **kwargs: documents
    )
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
        "collection": "default",
    }
    assert vectorstore.added_documents[1].metadata == {
        "page": 2,
        "file_id": 42,
        "filename": "lease.pdf",
        "chunk_index": 1,
        "collection": "default",
    }


def test_index_document_stamps_custom_collection(monkeypatch):
    documents = [Document(page_content="Chunk", metadata={})]
    vectorstore = FakeVectorstore()

    monkeypatch.setattr(
        chroma_utils, "load_and_split_document", lambda file_path, *args, **kwargs: documents
    )
    monkeypatch.setattr(chroma_utils, "get_vectorstore", lambda: vectorstore)

    assert (
        chroma_utils.index_document_to_chroma(
            "upload.pdf", file_id=42, filename="lease.pdf", collection="clients-acme"
        )
        is True
    )
    assert vectorstore.added_documents[0].metadata["collection"] == "clients-acme"


def test_metadata_filter_combines_scopes():
    assert chroma_utils._metadata_filter() is None
    assert chroma_utils._metadata_filter([7], ["acme"]) == {
        "file_id": {"$in": [7]},
        "collection": {"$in": ["acme"]},
    }


def test_matches_scope_filters_by_collection():
    assert (
        chroma_utils._matches_scope({"file_id": 7, "collection": "acme"}, [7], ["acme"])
        is True
    )
    assert (
        chroma_utils._matches_scope({"file_id": 7, "collection": "other"}, [7], ["acme"])
        is False
    )
    assert chroma_utils._matches_scope({"file_id": 7}, None, None) is True


def test_filtered_retriever_forwards_collection_filter(monkeypatch):
    vectorstore = FakeVectorstore()
    monkeypatch.setattr(chroma_utils, "get_vectorstore", lambda: vectorstore)

    chroma_utils.get_filtered_retriever(k=5, file_ids=[7], collections=["acme"])

    assert vectorstore.search_kwargs == {
        "k": 5,
        "filter": {"file_id": {"$in": [7]}, "collection": {"$in": ["acme"]}},
    }


def test_index_document_returns_false_when_document_has_no_chunks(monkeypatch):
    vectorstore = FakeVectorstore()

    monkeypatch.setattr(
        chroma_utils, "load_and_split_document", lambda file_path, *args, **kwargs: []
    )
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


def test_index_document_retries_transient_failures(monkeypatch):
    documents = [Document(page_content="Chunk", metadata={})]

    class FlakyVectorstore(FakeVectorstore):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def add_documents(self, documents, ids=None):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("transient")
            return super().add_documents(documents, ids=ids)

    vectorstore = FlakyVectorstore()
    monkeypatch.setattr(
        chroma_utils, "load_and_split_document", lambda file_path, *args, **kwargs: documents
    )
    monkeypatch.setattr(chroma_utils, "get_vectorstore", lambda: vectorstore)
    monkeypatch.setattr(chroma_utils.time, "sleep", lambda seconds: None)

    assert (
        chroma_utils.index_document_to_chroma("retry.pdf", file_id=42, filename="retry.pdf")
        is True
    )
    expected_attempts = 2
    assert vectorstore.calls == expected_attempts
    assert vectorstore.added_ids == ["42:0"]


def test_index_document_returns_false_after_retries_exhausted(monkeypatch):
    documents = [Document(page_content="Chunk", metadata={})]

    class AlwaysFailingVectorstore(FakeVectorstore):
        def add_documents(self, documents, ids=None):
            raise RuntimeError("persistent")

    monkeypatch.setattr(
        chroma_utils, "load_and_split_document", lambda file_path, *args, **kwargs: documents
    )
    monkeypatch.setattr(chroma_utils, "get_vectorstore", AlwaysFailingVectorstore)
    monkeypatch.setattr(chroma_utils.time, "sleep", lambda seconds: None)

    assert (
        chroma_utils.index_document_to_chroma("fail.pdf", file_id=42, filename="fail.pdf")
        is False
    )
