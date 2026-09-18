"""Unit tests for the eval harness (fakes only — no OpenAI calls)."""

import json
from types import SimpleNamespace

from langchain_core.documents import Document
from scripts import eval_retrieval


class FakeVectorstore:
    def __init__(self, docs_by_query, hybrid_docs=None):
        self.docs_by_query = docs_by_query
        self.hybrid_docs = hybrid_docs if hybrid_docs is not None else docs_by_query

    def similarity_search(self, query, k=5, **kwargs):
        return self.docs_by_query.get(query, [])[:k]

    def hybrid_search(self, query, k=5, collection=None):
        return self.hybrid_docs.get(query, [])[:k]


class FakeLLM:
    def __init__(self, content):
        self.content = content

    def invoke(self, prompt):
        return SimpleNamespace(content=self.content)


def _vectorstore():
    return FakeVectorstore(
        {
            "Original wording?": [Document(page_content="a", metadata={"filename": "other.pdf"})],
            "Better phrasing?": [Document(page_content="b", metadata={"filename": "lease.pdf"})],
        }
    )


def test_evaluate_case_baseline_misses_without_expansion():
    case = {"id": "x", "question": "Original wording?", "expected_filename": "lease.pdf"}

    passed, retrieved = eval_retrieval.evaluate_case(_vectorstore(), case, k=5)

    assert passed is False
    assert retrieved == {"other.pdf"}


def test_evaluate_case_expansion_finds_expected_file():
    case = {"id": "x", "question": "Original wording?", "expected_filename": "lease.pdf"}
    llm = FakeLLM("Better phrasing?\n")

    passed, retrieved = eval_retrieval.evaluate_case(
        _vectorstore(), case, k=5, expand=True, llm=llm
    )

    assert passed is True
    assert retrieved == {"other.pdf", "lease.pdf"}


def test_evaluate_compare_counts_both_modes(monkeypatch, tmp_path, capsys):
    expected_exit_code = 1
    golden = tmp_path / "golden.json"
    golden.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "x",
                        "question": "Original wording?",
                        "expected_filename": "lease.pdf",
                        "k": 5,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(eval_retrieval, "get_vectorstore", _vectorstore)

    code = eval_retrieval.evaluate(
        golden, compare=True, llm=FakeLLM("Better phrasing?\n")
    )

    assert code == expected_exit_code
    output = capsys.readouterr().out
    assert "0/1 baseline cases passed" in output
    assert "1/1 expanded cases passed" in output


def test_evaluate_case_hybrid_finds_expected_file():
    case = {"id": "h", "question": "security deposit", "expected_filename": "deposit.pdf"}
    vs = FakeVectorstore(
        docs_by_query={
            "security deposit": [
                Document(page_content="misc rules", metadata={"filename": "rules.pdf"})
            ]
        },
        hybrid_docs={
            "security deposit": [
                Document(page_content="deposit return", metadata={"filename": "deposit.pdf"})
            ]
        },
    )
    passed, retrieved = eval_retrieval.evaluate_case(vs, case, k=5, hybrid=True)
    assert passed is True
    assert retrieved == {"deposit.pdf"}


def test_evaluate_case_rerank_orders_hits():
    top_k = 1
    case = {"id": "r", "question": "pet policy terms", "expected_filename": "policy.pdf"}
    doc_noise = Document(
        page_content="general company overview", metadata={"filename": "noise.pdf"}
    )
    doc_policy = Document(
        page_content="pet policy terms agreement", metadata={"filename": "policy.pdf"}
    )
    vs = FakeVectorstore(docs_by_query={"pet policy terms": [doc_noise, doc_policy]})

    passed_no_rerank, retrieved_no_rerank = eval_retrieval.evaluate_case(
        vs, case, k=top_k, rerank=False
    )
    assert passed_no_rerank is False
    assert retrieved_no_rerank == {"noise.pdf"}

    passed_rerank, retrieved_rerank = eval_retrieval.evaluate_case(
        vs, case, k=top_k, rerank=True
    )
    assert passed_rerank is True
    assert retrieved_rerank == {"policy.pdf"}


def test_evaluate_case_collection_filter():
    case = {
        "id": "c",
        "question": "parking rules",
        "expected_filename": "commercial_parking.pdf",
    }
    doc_default = Document(
        page_content="residential parking rules",
        metadata={"filename": "residential_parking.pdf", "collection": "default"},
    )
    doc_commercial = Document(
        page_content="commercial parking rules",
        metadata={"filename": "commercial_parking.pdf", "collection": "commercial"},
    )
    vs = FakeVectorstore(docs_by_query={"parking rules": [doc_default, doc_commercial]})

    passed, retrieved = eval_retrieval.evaluate_case(
        vs, case, k=5, collection="commercial"
    )
    assert passed is True
    assert retrieved == {"commercial_parking.pdf"}

    passed_default, retrieved_default = eval_retrieval.evaluate_case(
        vs, case, k=5, collection="default"
    )
    assert passed_default is False
    assert retrieved_default == {"residential_parking.pdf"}


def test_evaluate_json_output(monkeypatch, tmp_path):
    expected_exit_code = 0
    expected_cases = 1
    golden = tmp_path / "golden.json"
    golden.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "case1",
                        "question": "Original wording?",
                        "expected_filename": "lease.pdf",
                        "k": 5,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(eval_retrieval, "get_vectorstore", _vectorstore)
    out_json = tmp_path / "reports" / "eval.json"

    code = eval_retrieval.evaluate(
        golden,
        expand=True,
        llm=FakeLLM("Better phrasing?\n"),
        json_output=out_json,
    )
    assert code == expected_exit_code
    assert out_json.is_file()
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["summary"]["total_cases"] == expected_cases
    assert data["summary"]["modes"]["expanded"]["passed"] == expected_cases
    assert data["summary"]["modes"]["expanded"]["pass_rate"] == 1.0
    assert len(data["results"]) == expected_cases
    assert data["results"][0]["id"] == "case1"
    assert data["results"][0]["modes"]["expanded"]["passed"] is True


def test_main_cli_parses_options(monkeypatch, tmp_path):
    expected_exit_code = 0
    golden = tmp_path / "golden.json"
    golden.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "cli_case",
                        "question": "Original wording?",
                        "expected_filename": "other.pdf",
                        "k": 5,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    cli_vs = FakeVectorstore(
        {
            "Original wording?": [
                Document(
                    page_content="a",
                    metadata={"filename": "other.pdf", "collection": "commercial"},
                )
            ]
        }
    )
    monkeypatch.setattr(eval_retrieval, "get_vectorstore", lambda: cli_vs)
    out_json = tmp_path / "cli_report.json"

    exit_code = eval_retrieval.main(
        [
            "--golden",
            str(golden),
            "--hybrid",
            "--rerank",
            "--collection",
            "commercial",
            "--json-output",
            str(out_json),
        ]
    )
    assert exit_code == expected_exit_code
    assert out_json.is_file()

