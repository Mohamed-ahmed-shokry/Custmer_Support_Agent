import sys
from unittest.mock import MagicMock

from api import langchain_utils


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


def test_get_rag_chain_construction(monkeypatch):
    mock_retriever = MagicMock()
    mock_select_retriever = MagicMock(return_value=mock_retriever)
    monkeypatch.setattr(langchain_utils, "select_retriever", mock_select_retriever)

    mock_llm = MagicMock()
    monkeypatch.setattr(langchain_utils, "ChatOpenAI", lambda model: mock_llm)

    mock_history_aware = MagicMock()
    mock_stuff_chain = MagicMock()
    mock_rag_chain = MagicMock()

    mock_create_history_aware = MagicMock(return_value=mock_history_aware)
    mock_create_stuff = MagicMock(return_value=mock_stuff_chain)
    mock_create_retrieval = MagicMock(return_value=mock_rag_chain)

    mock_chains_module = MagicMock()
    mock_chains_module.create_history_aware_retriever = mock_create_history_aware
    mock_chains_module.create_retrieval_chain = mock_create_retrieval

    mock_combine_module = MagicMock()
    mock_combine_module.create_stuff_documents_chain = mock_create_stuff

    monkeypatch.setitem(sys.modules, "langchain.chains", mock_chains_module)
    monkeypatch.setitem(sys.modules, "langchain.chains.combine_documents", mock_combine_module)

    result = langchain_utils.get_rag_chain(
        model="gpt-4o",
        file_ids=[10, 20],
        source_filename="doc.pdf",
        use_hybrid=True,
        collections=["test_col"],
        expand_query=True,
        rerank=True,
    )

    assert result is mock_rag_chain
    mock_select_retriever.assert_called_once()
    _, kwargs = mock_select_retriever.call_args
    assert kwargs["file_ids"] == [10, 20]
    assert kwargs["source_filename"] == "doc.pdf"
    assert kwargs["use_hybrid"] is True
    assert kwargs["collections"] == ["test_col"]
    assert kwargs["expand_query"] is True
    assert kwargs["rerank"] is True
    assert kwargs["llm"] is mock_llm

    mock_create_history_aware.assert_called_once_with(
        mock_llm, mock_retriever, langchain_utils.contextualize_q_prompt
    )
    mock_create_stuff.assert_called_once_with(mock_llm, langchain_utils.qa_prompt)
    mock_create_retrieval.assert_called_once_with(mock_history_aware, mock_stuff_chain)


def test_get_rag_chain_defaults(monkeypatch):
    mock_retriever = MagicMock()
    mock_select = MagicMock(return_value=mock_retriever)
    monkeypatch.setattr(langchain_utils, "select_retriever", mock_select)
    monkeypatch.setattr(langchain_utils, "ChatOpenAI", lambda model: MagicMock())

    mock_chains = MagicMock()
    mock_combine = MagicMock()
    monkeypatch.setitem(sys.modules, "langchain.chains", mock_chains)
    monkeypatch.setitem(sys.modules, "langchain.chains.combine_documents", mock_combine)

    langchain_utils.get_rag_chain()
    mock_select.assert_called_once()
    _, kwargs = mock_select.call_args
    assert kwargs["file_ids"] is None
    assert kwargs["source_filename"] is None
    assert kwargs["collections"] is None
