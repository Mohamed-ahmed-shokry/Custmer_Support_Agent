"""Unit tests for the eval harness (fakes only — no OpenAI calls)."""

import json
from types import SimpleNamespace

from langchain_core.documents import Document
from scripts import eval_retrieval


class FakeVectorstore:
    def __init__(self, docs_by_query):
        self.docs_by_query = docs_by_query

    def similarity_search(self, query, k=5, **kwargs):
        return self.docs_by_query.get(query, [])[:k]


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

    assert code == 1  # baseline misses, so overall fails
    output = capsys.readouterr().out
    assert "0/1 baseline cases passed" in output
    assert "1/1 expanded cases passed" in output
