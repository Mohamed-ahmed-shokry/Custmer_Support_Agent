from api import rerank
from langchain_core.documents import Document


def _doc(text, **metadata):
    return Document(page_content=text, metadata=dict(metadata))


def test_tokenize_drops_stopwords_and_short_tokens():
    assert rerank.tokenize("What is the Rent due date?") == {"rent", "due", "date"}
    assert rerank.tokenize("!!!") == set()


def test_rerank_orders_by_coverage_then_hits():
    docs = [
        _doc("unrelated text here"),
        _doc("rent is due monthly, rent receipts kept"),
        _doc("when is the rent due"),
    ]

    ranked = rerank.rerank_by_term_overlap("When is rent due?", docs, top_n=3)

    assert [d.page_content for d in ranked] == [
        "rent is due monthly, rent receipts kept",
        "when is the rent due",
        "unrelated text here",
    ]


def test_rerank_respects_top_n_and_empty_query():
    docs = [_doc("alpha beta"), _doc("gamma delta")]

    assert rerank.rerank_by_term_overlap("alpha", docs, top_n=1) == [docs[0]]
    assert rerank.rerank_by_term_overlap("alpha", docs, top_n=0) == []
    assert rerank.rerank_by_term_overlap("!!!", docs, top_n=5) == docs


def test_reranking_retriever_wraps_base_retriever():
    docs = [_doc("unrelated"), _doc("rent due date")]

    class FakeBase:
        def invoke(self, query):
            return docs

    retriever = rerank.RerankingRetriever(base=FakeBase(), top_n=2)

    assert retriever.invoke("When is rent due?") == [docs[1], docs[0]]
