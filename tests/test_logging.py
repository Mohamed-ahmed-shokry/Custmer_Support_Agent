import json
import logging
import sys

from api.main import JsonLogFormatter, build_log_formatter, configure_logging
from api.settings import settings


def _record(message="boom", exc_info=None) -> logging.LogRecord:
    return logging.LogRecord(
        name="api.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=exc_info,
    )


def test_json_formatter_emits_structured_payload():
    payload = json.loads(JsonLogFormatter().format(_record("boom")))

    assert payload["message"] == "boom"
    assert payload["level"] == "ERROR"
    assert payload["logger"] == "api.test"
    assert payload["time"]


def test_json_formatter_includes_exc_info_when_present():
    try:
        raise RuntimeError("kaboom")
    except RuntimeError:
        record = _record(exc_info=sys.exc_info())

    payload = json.loads(JsonLogFormatter().format(record))

    assert "kaboom" in payload["exc_info"]


def test_build_log_formatter_selects_json(monkeypatch):
    monkeypatch.setattr(settings, "log_format", "json")

    assert isinstance(build_log_formatter(), JsonLogFormatter)


def test_build_log_formatter_defaults_to_text(monkeypatch):
    monkeypatch.setattr(settings, "log_format", "text")

    formatter = build_log_formatter()

    assert isinstance(formatter, logging.Formatter)
    assert not isinstance(formatter, JsonLogFormatter)


def test_configure_logging_ships_to_stream_by_default():
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    try:
        root.handlers.clear()
        configure_logging()

        assert root.level == logging.INFO
        assert any(isinstance(handler, logging.StreamHandler) for handler in root.handlers)
        assert not any(isinstance(handler, logging.FileHandler) for handler in root.handlers)
    finally:
        root.handlers[:] = saved_handlers


def test_configure_logging_adds_file_handler_when_log_path_set(tmp_path, monkeypatch):
    log_path = tmp_path / "app.log"
    monkeypatch.setattr(settings, "log_path", str(log_path))
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    try:
        root.handlers.clear()
        configure_logging()

        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1
        assert any(isinstance(handler, logging.StreamHandler) for handler in root.handlers)
    finally:
        root.handlers[:] = saved_handlers
        monkeypatch.setattr(settings, "log_path", "")
