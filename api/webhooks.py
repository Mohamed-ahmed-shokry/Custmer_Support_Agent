import hashlib
import hmac
import json
import logging
import uuid
from datetime import UTC, datetime

import requests

from api import db_utils
from api.settings import settings

logger = logging.getLogger(__name__)

WEBHOOK_USER_AGENT = f"Customer-Support-Agent-Webhook/{settings.app_version}"


def sign_payload(secret: str | None, timestamp: str, payload_str: str) -> str:
    """Compute HMAC-SHA256 hex signature over f'{timestamp}.{payload_str}'."""
    if not secret or not secret.strip():
        return ""
    signature_data = f"{timestamp}.{payload_str}".encode()
    return hmac.new(secret.strip().encode(), signature_data, hashlib.sha256).hexdigest()


def verify_signature(
    secret: str | None,
    timestamp: str,
    payload_str: str,
    signature: str | None,
) -> bool:
    """Verify HMAC-SHA256 signature using constant-time comparison."""
    if not secret or not signature:
        return False
    expected = sign_payload(secret, timestamp, payload_str)
    if not expected:
        return False
    return hmac.compare_digest(expected, signature.strip())


def build_event_envelope(
    event: str,
    data: dict,
    event_id: str | None = None,
    timestamp: str | None = None,
) -> dict:
    """Construct standard JSON event envelope for webhooks."""
    envelope_id = event_id or str(uuid.uuid4())
    envelope_timestamp = timestamp or datetime.now(UTC).isoformat()
    return {
        "id": envelope_id,
        "event": event,
        "timestamp": envelope_timestamp,
        "data": data,
    }


def deliver_webhook(
    webhook: dict,
    event: str,
    payload: dict,
    timeout: float | None = None,
) -> dict:
    """Send an HTTP POST webhook request, log the attempt, and update failure count."""
    request_timeout = timeout if timeout is not None else settings.webhook_timeout
    payload_str = json.dumps(payload, separators=(",", ":"))
    ts_str = str(payload.get("timestamp", ""))

    headers = {
        "Content-Type": "application/json",
        "User-Agent": WEBHOOK_USER_AGENT,
        "X-Webhook-Event": event,
        "X-Webhook-Timestamp": ts_str,
    }

    secret = webhook.get("secret", "")
    if secret:
        signature = sign_payload(secret, ts_str, payload_str)
        if signature:
            headers["X-Webhook-Signature"] = signature

    status_code: int | None = None
    success = False
    error_message: str | None = None

    try:
        response = requests.post(
            webhook["url"],
            data=payload_str,
            headers=headers,
            timeout=request_timeout,
        )
        status_code = response.status_code
        success = response.ok
        if not success:
            error_message = f"HTTP {status_code}: {response.text[:200]}"
    except requests.RequestException as exc:
        error_message = str(exc)

    try:
        db_utils.record_webhook_delivery(
            webhook_id=webhook["id"],
            event=event,
            url=webhook["url"],
            status_code=status_code,
            success=success,
            payload_preview=payload_str[:500],
            error_message=error_message,
        )
    except Exception as db_exc:
        logger.warning("Failed to record webhook delivery in db: %s", db_exc)

    return {
        "webhook_id": webhook["id"],
        "url": webhook["url"],
        "event": event,
        "status_code": status_code,
        "success": success,
        "error": error_message,
    }


def dispatch_event(
    event: str,
    data: dict,
    timeout: float | None = None,
) -> list[dict]:
    """Fan out an event envelope to all active subscribed webhooks."""
    webhooks = db_utils.list_webhooks(active_only=True, event=event)
    if not webhooks:
        return []

    payload = build_event_envelope(event, data)
    results = []
    for wh in webhooks:
        res = deliver_webhook(wh, event, payload, timeout=timeout)
        results.append(res)
    return results


def ping_webhook(webhook_id: int, timeout: float | None = None) -> dict:
    """Send a test ping event to a specific webhook."""
    wh = db_utils.get_webhook(webhook_id)
    if wh is None:
        raise ValueError(f"Webhook {webhook_id} not found.")

    payload = build_event_envelope(
        "ping",
        {"message": "Webhook test verification ping", "webhook_id": webhook_id},
    )
    return deliver_webhook(wh, "ping", payload, timeout=timeout)
