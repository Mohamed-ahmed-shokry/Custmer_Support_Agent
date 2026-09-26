import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

from api import langchain_utils
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable


def test_prompts_and_system_instructions_exist():
    assert "Ghalirealty" in langchain_utils.QA_SYSTEM_PROMPT
    assert "louisaghali@ghalirealty.com" in langchain_utils.QA_SYSTEM_PROMPT
    assert "407-776-4149" in langchain_utils.QA_SYSTEM_PROMPT

    # Verify message placeholders and input variables
    input_vars = langchain_utils.contextualize_q_prompt.input_variables
    assert "chat_history" in input_vars
    assert "input" in input_vars

    qa_input_vars = langchain_utils.qa_prompt.input_variables
    assert "context" in qa_input_vars
    assert "chat_history" in qa_input_vars
    assert "input" in qa_input_vars


def test_format_docs_joins_page_content():
    docs = [
        SimpleNamespace(page_content="first chunk"),
        SimpleNamespace(page_content="second chunk"),
    ]
    assert langchain_utils._format_docs(docs) == "first chunk\n\nsecond chunk"


def test_get_rag_chain_construction(monkeypatch):
    mock_retriever = MagicMock()
    mock_select_retriever = MagicMock(return_value=mock_retriever)
    monkeypatch.setattr(langchain_utils, "select_retriever", mock_select_retriever)

    mock_llm = MagicMock()
    monkeypatch.setattr(langchain_utils, "ChatOpenAI", lambda model: mock_llm)

    result = langchain_utils.get_rag_chain(
        model="gpt-4o",
        file_ids=[10, 20],
        source_filename="doc.pdf",
        use_hybrid=True,
        collections=["test_col"],
        expand_query=True,
        rerank=True,
    )

    assert isinstance(result, Runnable)

    mock_select_retriever.assert_called_once()
    _, kwargs = mock_select_retriever.call_args
    assert kwargs["file_ids"] == [10, 20]
    assert kwargs["source_filename"] == "doc.pdf"
    assert kwargs["use_hybrid"] is True
    assert kwargs["collections"] == ["test_col"]
    assert kwargs["expand_query"] is True
    assert kwargs["rerank"] is True
    assert kwargs["llm"] is mock_llm


def test_get_rag_chain_defaults(monkeypatch):
    mock_retriever = MagicMock()
    mock_select = MagicMock(return_value=mock_retriever)
    monkeypatch.setattr(langchain_utils, "select_retriever", mock_select)
    monkeypatch.setattr(langchain_utils, "ChatOpenAI", lambda model: MagicMock())

    result = langchain_utils.get_rag_chain()

    assert isinstance(result, Runnable)
    mock_select.assert_called_once()
    _, kwargs = mock_select.call_args
    assert kwargs["file_ids"] is None
    assert kwargs["source_filename"] is None
    assert kwargs["collections"] is None


class _EchoLLM:
    """Returns the rendered messages so the pipeline wiring is observable."""

    def __init__(self, model):
        self.model = model

    def __call__(self, value):
        if isinstance(value, list):
            messages = value
        elif hasattr(value, "messages"):
            messages = value.messages
        else:
            return str(value)
        return "".join(str(message.content) for message in messages)


class _FakeRetriever:
    def __init__(self):
        self.calls = []

    def __call__(self, question):
        self.calls.append(question)
        return [SimpleNamespace(page_content="RETRIEVED-CHUNK")]


def test_get_rag_chain_invokes_lcel_pipeline(monkeypatch):
    monkeypatch.setattr(
        langchain_utils,
        "contextualize_q_prompt",
        ChatPromptTemplate.from_template("Q:{input}"),
    )
    monkeypatch.setattr(
        langchain_utils,
        "qa_prompt",
        ChatPromptTemplate.from_template("C:{context} | I:{input}"),
    )
    fake_retriever = _FakeRetriever()
    monkeypatch.setattr(langchain_utils, "select_retriever", lambda **kwargs: fake_retriever)
    monkeypatch.setattr(langchain_utils, "ChatOpenAI", _EchoLLM)

    chain = langchain_utils.get_rag_chain()
    result = chain.invoke({"input": "hello", "chat_history": []})

    assert "RETRIEVED-CHUNK" in result
    assert "I:hello" in result
    assert fake_retriever.calls == ["Q:hello"]


def test_get_rag_chain_does_not_import_legacy_chains(monkeypatch):
    """The LCEL pipeline must not rely on the broken langchain.chains package."""
    monkeypatch.setattr(langchain_utils, "select_retriever", lambda **kwargs: MagicMock())
    monkeypatch.setattr(langchain_utils, "ChatOpenAI", lambda model: MagicMock())

    langchain_utils.get_rag_chain()

    assert "langchain.chains" not in sys.modules
    assert "langchain.chains.combine_documents" not in sys.modules
