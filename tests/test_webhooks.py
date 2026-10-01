from unittest.mock import MagicMock, patch

import pytest
import requests
from api import db_utils, webhooks
from tests.test_db_utils import initialize_temp_db


def test_sign_and_verify_signature():
    secret = "test-secret-key-12345"
    timestamp = "2026-10-01T12:00:00Z"
    payload = '{"event":"session.escalated","data":{"session_id":"s-1"}}'

    sig = webhooks.sign_payload(secret, timestamp, payload)
    assert isinstance(sig, str)
    expected_hex_length = 64
    assert len(sig) == expected_hex_length

    # Verification passes with correct parameters
    assert webhooks.verify_signature(secret, timestamp, payload, sig) is True

    # Verification fails if secret differs
    assert webhooks.verify_signature("wrong-secret", timestamp, payload, sig) is False

    # Verification fails if timestamp differs
    assert webhooks.verify_signature(secret, "2026-10-01T12:00:01Z", payload, sig) is False

    # Verification fails if payload differs
    tampered_payload = '{"event":"session.escalated","data":{"session_id":"s-2"}}'
    assert webhooks.verify_signature(secret, timestamp, tampered_payload, sig) is False

    # Empty secret returns empty signature and fails verification
    assert webhooks.sign_payload("", timestamp, payload) == ""
    assert webhooks.sign_payload(None, timestamp, payload) == ""
    assert webhooks.verify_signature("", timestamp, payload, sig) is False
    assert webhooks.verify_signature(secret, timestamp, payload, "") is False
    assert webhooks.verify_signature(secret, timestamp, payload, None) is False


def test_build_event_envelope():
    data = {"session_id": "test-123", "status": "escalated"}
    envelope = webhooks.build_event_envelope("session.escalated", data)

    assert envelope["event"] == "session.escalated"
    assert envelope["data"] == data
    assert "id" in envelope and len(envelope["id"]) > 0
    assert "timestamp" in envelope and "T" in envelope["timestamp"]

    # Explicit id and timestamp
    custom_envelope = webhooks.build_event_envelope(
        event="ping",
        data={},
        event_id="custom-uuid-1",
        timestamp="2026-10-01T00:00:00Z",
    )
    assert custom_envelope["id"] == "custom-uuid-1"
    assert custom_envelope["timestamp"] == "2026-10-01T00:00:00Z"


def test_deliver_webhook_success(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    hook = db_utils.create_webhook(
        url="https://example.com/receiver",
        events="*",
        secret="whsec_abc123",
    )

    envelope = webhooks.build_event_envelope(
        "session.escalated",
        {"session_id": "s-1"},
        event_id="ev-1",
        timestamp="2026-10-01T12:00:00Z",
    )

    mock_resp = MagicMock()
    expected_status_code = 200
    mock_resp.status_code = expected_status_code
    mock_resp.ok = True
    mock_resp.text = '{"received": true}'

    with patch("requests.post", return_value=mock_resp) as mock_post:
        result = webhooks.deliver_webhook(hook, "session.escalated", envelope)

        assert mock_post.called
        call_args, call_kwargs = mock_post.call_args
        assert call_args[0] == "https://example.com/receiver"
        headers = call_kwargs["headers"]
        assert headers["Content-Type"] == "application/json"
        assert headers["X-Webhook-Event"] == "session.escalated"
        assert headers["X-Webhook-Timestamp"] == "2026-10-01T12:00:00Z"
        assert "X-Webhook-Signature" in headers

        expected_sig = webhooks.sign_payload(
            "whsec_abc123", "2026-10-01T12:00:00Z", call_kwargs["data"]
        )
        assert headers["X-Webhook-Signature"] == expected_sig

        assert result["webhook_id"] == hook["id"]
        assert result["success"] is True
        assert result["status_code"] == expected_status_code
        assert result["error"] is None

    # Check delivery log in DB
    logs, total = db_utils.get_webhook_delivery_logs(webhook_id=hook["id"])
    assert total == 1
    assert logs[0]["success"] is True
    assert logs[0]["status_code"] == expected_status_code
    assert "session.escalated" in logs[0]["payload_preview"]


def test_deliver_webhook_http_error(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    hook = db_utils.create_webhook(
        url="https://example.com/server-error",
        events="*",
    )

    envelope = webhooks.build_event_envelope("session.escalated", {"session_id": "s-fail"})

    mock_resp = MagicMock()
    err_status_code = 500
    mock_resp.status_code = err_status_code
    mock_resp.ok = False
    mock_resp.text = "Internal Server Error"

    with patch("requests.post", return_value=mock_resp):
        result = webhooks.deliver_webhook(hook, "session.escalated", envelope)

        assert result["success"] is False
        assert result["status_code"] == err_status_code
        assert "HTTP 500" in (result["error"] or "")

    refreshed_hook = db_utils.get_webhook(hook["id"])
    assert refreshed_hook is not None
    assert refreshed_hook["failure_count"] == 1


def test_deliver_webhook_network_exception(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    hook = db_utils.create_webhook(
        url="https://timeout.example.com/hook",
        events="*",
    )

    envelope = webhooks.build_event_envelope("ping", {})

    timeout_err = requests.exceptions.ConnectTimeout("Connection timed out")
    with patch("requests.post", side_effect=timeout_err):
        result = webhooks.deliver_webhook(hook, "ping", envelope)

        assert result["success"] is False
        assert result["status_code"] is None
        assert "Connection timed out" in (result["error"] or "")

    refreshed_hook = db_utils.get_webhook(hook["id"])
    assert refreshed_hook is not None
    assert refreshed_hook["failure_count"] == 1


def test_deliver_webhook_no_secret_omits_signature_header(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    hook = db_utils.create_webhook(
        url="https://example.com/no-secret",
        events="*",
        secret="",
    )

    envelope = webhooks.build_event_envelope("ping", {})

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.ok = True

    with patch("requests.post", return_value=mock_resp) as mock_post:
        webhooks.deliver_webhook(hook, "ping", envelope)
        headers = mock_post.call_args[1]["headers"]
        assert "X-Webhook-Signature" not in headers


def test_dispatch_event_filters_and_delivers(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    h_all = db_utils.create_webhook(url="https://example.com/all", events="*")
    h_esc = db_utils.create_webhook(url="https://example.com/esc", events="session.escalated")
    h_res = db_utils.create_webhook(url="https://example.com/res", events="session.resolved")
    db_utils.create_webhook(url="https://example.com/inactive", events="*", is_active=False)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.ok = True

    with patch("requests.post", return_value=mock_resp) as mock_post:
        # Dispatch session.escalated
        results = webhooks.dispatch_event("session.escalated", {"session_id": "s-100"})
        expected_results_count = 2
        assert len(results) == expected_results_count
        delivered_ids = {r["webhook_id"] for r in results}
        assert delivered_ids == {h_all["id"], h_esc["id"]}
        assert h_res["id"] not in delivered_ids
        assert mock_post.call_count == expected_results_count

    # Dispatch event with no subscribers
    with patch("requests.post", return_value=mock_resp):
        results = webhooks.dispatch_event("ping", {"msg": "test"})
        # Only h_all receives ping (because h_esc and h_res do not match ping)
        assert len(results) == 1
        assert results[0]["webhook_id"] == h_all["id"]


def test_ping_webhook(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    hook = db_utils.create_webhook(url="https://example.com/ping-target")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.ok = True

    with patch("requests.post", return_value=mock_resp):
        res = webhooks.ping_webhook(hook["id"])
        assert res["success"] is True
        assert res["event"] == "ping"

    with pytest.raises(ValueError, match="Webhook 999 not found"):
        webhooks.ping_webhook(999)


def test_deliver_webhook_db_failure_does_not_raise(monkeypatch, tmp_path):
    initialize_temp_db(monkeypatch, tmp_path)

    hook = db_utils.create_webhook(url="https://example.com/db-fail")
    envelope = webhooks.build_event_envelope("ping", {})

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.ok = True

    db_err = RuntimeError("DB disk full")
    with (
        patch("requests.post", return_value=mock_resp),
        patch("api.db_utils.record_webhook_delivery", side_effect=db_err),
    ):
        res = webhooks.deliver_webhook(hook, "ping", envelope)
        assert res["success"] is True
