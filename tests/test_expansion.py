from types import SimpleNamespace

from api import expansion
from langchain_core.documents import Document


class FakeLLM:
    def __init__(self, content="Alternative one\nAlternative two\n"):
        self.content = content
        self.seen_prompts = []

    def invoke(self, prompt):
        self.seen_prompts.append(prompt)
        return SimpleNamespace(content=self.content)


def test_rewrite_queries_returns_original_first():
    queries = expansion.rewrite_queries("How do I pay rent?", llm=FakeLLM(), count=3)

    assert queries[0] == "How do I pay rent?"
    assert queries == ["How do I pay rent?", "Alternative one", "Alternative two"]


def test_rewrite_queries_dedupes_and_falls_back():
    class ExplodingLLM:
        def invoke(self, prompt):
            raise RuntimeError("provider down")

    assert expansion.rewrite_queries("Hello?", llm=ExplodingLLM(), count=3) == ["Hello?"]
    assert expansion.rewrite_queries("  ", llm=FakeLLM(), count=3) == []
    assert expansion.rewrite_queries("Hello?", llm=FakeLLM(), count=1) == ["Hello?"]


def test_reciprocal_rank_fuse_prefers_shared_hits():
    shared = Document(page_content="shared", metadata={"file_id": 1, "chunk_index": 0})
    first_only = Document(page_content="first", metadata={"file_id": 2, "chunk_index": 0})
    second_only = Document(page_content="second", metadata={"file_id": 3, "chunk_index": 0})

    merged = expansion.reciprocal_rank_fuse(
        [[shared, first_only], [second_only, shared]], k=3
    )

    # shared wins (two hits); second_only outranks first_only (rank 1 vs 2).
    assert [doc.page_content for doc in merged] == ["shared", "second", "first"]


def test_expanded_retriever_fuses_per_variant_results():
    llm = FakeLLM("rent payment\npaying rent online\n")
    docs_by_query = {
        "Original?": [Document(page_content="a", metadata={"chunk_index": 0})],
        "rent payment": [Document(page_content="b", metadata={"chunk_index": 1})],
        "paying rent online": [Document(page_content="a", metadata={"chunk_index": 0})],
    }

    class FakeVectorstore:
        def similarity_search(self, query, k=5, **kwargs):
            return docs_by_query[query][:k]

    retriever = expansion.ExpandedVectorRetriever(
        vectorstore=FakeVectorstore(), k=5, llm=llm, expansion_count=3
    )

    merged = retriever.invoke("Original?")

    assert [doc.page_content for doc in merged] == ["a", "b"]
