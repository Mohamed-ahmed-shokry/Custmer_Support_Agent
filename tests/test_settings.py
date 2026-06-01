from api.settings import Settings, get_positive_int_env


def test_get_positive_int_env_uses_default_when_missing(monkeypatch):
    monkeypatch.delenv("RETRIEVER_K", raising=False)

    assert get_positive_int_env("RETRIEVER_K", 5) == 5


def test_get_positive_int_env_uses_default_for_invalid_value(monkeypatch):
    monkeypatch.setenv("RETRIEVER_K", "many")

    assert get_positive_int_env("RETRIEVER_K", 5) == 5


def test_get_positive_int_env_uses_default_for_non_positive_value(monkeypatch):
    monkeypatch.setenv("RETRIEVER_K", "0")

    assert get_positive_int_env("RETRIEVER_K", 5) == 5


def test_settings_reads_retriever_k_from_environment(monkeypatch):
    monkeypatch.setenv("RETRIEVER_K", "8")

    assert Settings().retriever_k == 8
