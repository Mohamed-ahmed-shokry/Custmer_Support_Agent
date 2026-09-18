import pytest
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

    def get(self, where=None, include=None):
        self.last_where = where
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
    assert vectorstore.last_where == {"file_id": 42}
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


def test_get_text_splitter_markdown():
    options = chroma_utils.ChunkingOptions(strategy=chroma_utils.ChunkingStrategy.MARKDOWN)
    splitter = chroma_utils._get_text_splitter(options)
    assert isinstance(splitter, chroma_utils.MarkdownHeaderTextSplitter)


def test_load_and_split_document_unsupported_type():
    with pytest.raises(ValueError, match="Unsupported file type"):
        chroma_utils.load_and_split_document("invalid.xyz")


def test_load_and_split_document_text_files(tmp_path):
    txt_file = tmp_path / "sample.txt"
    txt_file.write_text("Hello world text file", encoding="utf-8")
    docs = chroma_utils.load_and_split_document(str(txt_file))
    assert len(docs) >= 1
    assert "Hello world" in docs[0].page_content

    csv_file = tmp_path / "sample.csv"
    csv_file.write_text("col1,col2\nval1,val2\n", encoding="utf-8")
    csv_docs = chroma_utils.load_and_split_document(str(csv_file))
    assert len(csv_docs) >= 1

    md_file = tmp_path / "sample.md"
    md_file.write_text("# Title\nMarkdown content here.", encoding="utf-8")
    md_docs = chroma_utils.load_and_split_document(str(md_file))
    assert len(md_docs) >= 1


def test_load_and_split_document_mocked_loaders(monkeypatch):
    loaded_doc = [Document(page_content="mocked content")]

    class MockLoader:
        def __init__(self, file_path):
            self.file_path = file_path

        def load(self):
            return loaded_doc

    monkeypatch.setattr(chroma_utils, "PyPDFLoader", MockLoader)
    docs_pdf = chroma_utils.load_and_split_document("doc.pdf")
    assert docs_pdf[0].page_content == "mocked content"

    monkeypatch.setattr(chroma_utils, "Docx2txtLoader", MockLoader)
    docs_docx = chroma_utils.load_and_split_document("doc.docx")
    assert docs_docx[0].page_content == "mocked content"

    monkeypatch.setattr(chroma_utils, "UnstructuredHTMLLoader", MockLoader)
    docs_html = chroma_utils.load_and_split_document("doc.html")
    assert docs_html[0].page_content == "mocked content"


def test_delete_doc_from_chroma_exception(monkeypatch):
    class ExplodingGetVectorstore(FakeVectorstore):
        def get(self, where):
            raise RuntimeError("db error")

    monkeypatch.setattr(chroma_utils, "get_vectorstore", ExplodingGetVectorstore)
    assert chroma_utils.delete_doc_from_chroma(42) is False


def test_delete_collection_from_chroma_empty_ids(monkeypatch):
    vectorstore = FakeVectorstore(ids=[])
    monkeypatch.setattr(chroma_utils, "get_vectorstore", lambda: vectorstore)
    assert chroma_utils.delete_collection_from_chroma("empty_col") == 0
    assert vectorstore.deleted_ids is None


def test_rename_collection_in_chroma_mismatched_payload_and_exception(monkeypatch):
    class MismatchedVectorstore(FakeVectorstore):
        def get(self, where, include=None):
            return {"ids": ["1:0"], "documents": ["doc1", "doc2"], "metadatas": []}

    monkeypatch.setattr(chroma_utils, "get_vectorstore", MismatchedVectorstore)
    assert chroma_utils.rename_collection_in_chroma("col", "new_col") == -1

    class ExplodingUpdateVectorstore(FakeVectorstore):
        def get(self, where, include=None):
            raise RuntimeError("update failed")

    monkeypatch.setattr(chroma_utils, "get_vectorstore", ExplodingUpdateVectorstore)
    assert chroma_utils.rename_collection_in_chroma("col", "new_col") == -1


def test_hybrid_retriever_fallbacks(monkeypatch):
    class EmptyGetVectorstore(FakeVectorstore):
        def get(self):
            return {"documents": []}

    monkeypatch.setattr(chroma_utils, "get_vectorstore", EmptyGetVectorstore)
    retriever = chroma_utils.get_hybrid_retriever(k=5)
    assert retriever == ("retriever", {"k": 5})


def test_select_retriever_source_filename_filtering(monkeypatch):
    vectorstore = FakeVectorstore()
    monkeypatch.setattr(chroma_utils, "get_vectorstore", lambda: vectorstore)

    chroma_utils.select_retriever(k=5, source_filename="terms.pdf")
    assert vectorstore.search_kwargs["filter"]["filename"] == {"$eq": "terms.pdf"}

    expanded = chroma_utils.select_retriever(k=5, expand_query=True, source_filename="terms.pdf")
    assert isinstance(expanded, ExpandedVectorRetriever)
    assert expanded.search_kwargs["filter"]["filename"] == {"$eq": "terms.pdf"}


def test_get_doc_chunks_from_chroma_success(monkeypatch):
    expected_chunk_count = 2
    file_id = 42

    class ChunkVectorstore(FakeVectorstore):
        def get(self, where=None, include=None):
            return {
                "ids": ["42:1", "42:0"],
                "documents": ["Second page chunk", "First page chunk"],
                "metadatas": [
                    {"chunk_index": 1, "page": 2, "filename": "doc.pdf"},
                    {"chunk_index": 0, "page": 1, "filename": "doc.pdf"},
                ],
            }

    monkeypatch.setattr(chroma_utils, "get_vectorstore", ChunkVectorstore)
    chunks = chroma_utils.get_doc_chunks_from_chroma(file_id)
    assert len(chunks) == expected_chunk_count
    assert chunks[0]["chunk_id"] == "42:0"
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["page"] == 1
    assert chunks[0]["content"] == "First page chunk"
    assert chunks[0]["preview"] == "First page chunk"
    assert chunks[1]["chunk_id"] == "42:1"
    assert chunks[1]["chunk_index"] == 1


def test_get_doc_chunks_from_chroma_error_returns_empty(monkeypatch):
    file_id = 99

    class ErrorVectorstore:
        def get(self, *args, **kwargs):
            raise RuntimeError("Chroma connection error")

    monkeypatch.setattr(chroma_utils, "get_vectorstore", ErrorVectorstore)
    assert chroma_utils.get_doc_chunks_from_chroma(file_id) == []


