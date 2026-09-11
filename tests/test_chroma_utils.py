from api import chroma_utils
from api.expansion import ExpandedVectorRetriever
from api.rerank import RerankingRetriever
from langchain_core.documents import Document

EXPECTED_RETRIEVER_K = 5


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


def test_select_retriever_wraps_base_with_rerank(monkeypatch):
    vectorstore = FakeVectorstore()
    monkeypatch.setattr(chroma_utils, "get_vectorstore", lambda: vectorstore)

    retriever = chroma_utils.select_retriever(k=EXPECTED_RETRIEVER_K, rerank=True)

    assert isinstance(retriever, RerankingRetriever)
    assert retriever.top_n == EXPECTED_RETRIEVER_K
    assert vectorstore.search_kwargs == {
        "k": EXPECTED_RETRIEVER_K * chroma_utils.RERANK_CANDIDATE_MULTIPLIER
    }


def test_select_retriever_prefers_expansion(monkeypatch):
    vectorstore = FakeVectorstore()
    monkeypatch.setattr(chroma_utils, "get_vectorstore", lambda: vectorstore)

    retriever = chroma_utils.select_retriever(
        k=EXPECTED_RETRIEVER_K, file_ids=[7], use_hybrid=True, expand_query=True
    )

    assert isinstance(retriever, ExpandedVectorRetriever)
    assert retriever.k == EXPECTED_RETRIEVER_K


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


def test_delete_collection_from_chroma_returns_chunk_count(monkeypatch):
    class CollectionVectorstore(FakeVectorstore):
        def get(self, where):
            assert where == {"collection": "acme"}
            return {"ids": self.ids}

    vectorstore = CollectionVectorstore(ids=["1:0", "1:1", "2:0"])
    monkeypatch.setattr(chroma_utils, "get_vectorstore", lambda: vectorstore)

    expected_chunks = ["1:0", "1:1", "2:0"]
    assert chroma_utils.delete_collection_from_chroma("acme") == len(expected_chunks)
    assert vectorstore.deleted_ids == expected_chunks


def test_delete_collection_from_chroma_reports_errors(monkeypatch):
    class ExplodingVectorstore(FakeVectorstore):
        def get(self, where):
            raise RuntimeError("vector store down")

    monkeypatch.setattr(chroma_utils, "get_vectorstore", ExplodingVectorstore)

    assert chroma_utils.delete_collection_from_chroma("acme") == -1


def test_rename_collection_in_chroma_retags_chunks(monkeypatch):
    class RenamingVectorstore(FakeVectorstore):
        def __init__(self):
            super().__init__(ids=["1:0", "1:1"])
            self.updated = None

        def get(self, where, include=None):
            assert where == {"collection": "acme"}
            assert include == ["documents", "metadatas"]
            return {
                "ids": self.ids,
                "documents": ["first chunk", "second chunk"],
                "metadatas": [
                    {"file_id": 1, "chunk_index": 0, "collection": "acme"},
                    {"file_id": 1, "chunk_index": 1, "collection": "acme"},
                ],
            }

        def update_documents(self, ids, documents):
            self.updated = (ids, documents)

    vectorstore = RenamingVectorstore()
    monkeypatch.setattr(chroma_utils, "get_vectorstore", lambda: vectorstore)

    expected_ids = ["1:0", "1:1"]
    assert chroma_utils.rename_collection_in_chroma("acme", "globex") == len(expected_ids)
    ids, documents = vectorstore.updated
    assert ids == expected_ids
    assert all(doc.metadata["collection"] == "globex" for doc in documents)
    assert documents[0].metadata["file_id"] == 1


def test_rename_collection_in_chroma_handles_empty_collection(monkeypatch):
    class EmptyVectorstore(FakeVectorstore):
        def get(self, where, include=None):
            return {"ids": [], "documents": [], "metadatas": []}

    monkeypatch.setattr(chroma_utils, "get_vectorstore", EmptyVectorstore)

    assert chroma_utils.rename_collection_in_chroma("acme", "globex") == 0


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
