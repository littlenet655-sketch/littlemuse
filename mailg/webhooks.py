"""Verified Resend webhook receiver for transactional delivery state.

The endpoint stores only provider message identifiers, recipient address,
coarse delivery state, and a bounded provider failure reason. OTP bodies and
codes are never persisted by this webhook.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import time
from typing import Any

from flask import Blueprint, Response, request

from database.connection import execute
from extensions import csrf, limiter

resend_webhook_bp = Blueprint("resend_webhook", __name__)

_STATUS_MAP = {
    "email.sent": "SENT",
    "email.delivered": "DELIVERED",
    "email.delivery_delayed": "DELIVERY_DELAYED",
    "email.bounced": "BOUNCED",
    "email.suppressed": "SUPPRESSED",
    "email.failed": "FAILED",
    "email.complained": "COMPLAINED",
}
_MAX_TIMESTAMP_SKEW_SECONDS = 300


def _decode_webhook_secret(secret: str) -> bytes:
    value = secret.strip()
    if value.startswith("whsec_"):
        value = value[len("whsec_"):]
    padding = "=" * (-len(value) % 4)
    return base64.b64decode(value + padding, validate=True)


def _verify_svix_signature(raw_body: bytes) -> bool:
    secret = (os.getenv("RESEND_WEBHOOK_SECRET") or "").strip()
    msg_id = (request.headers.get("svix-id") or "").strip()
    timestamp = (request.headers.get("svix-timestamp") or "").strip()
    signatures = (request.headers.get("svix-signature") or "").strip()

    if not secret or not msg_id or not timestamp or not signatures:
        return False

    try:
        ts = int(timestamp)
        if abs(int(time.time()) - ts) > _MAX_TIMESTAMP_SKEW_SECONDS:
            return False
        signing_secret = _decode_webhook_secret(secret)
    except (ValueError, TypeError, binascii.Error):
        return False

    signed_payload = msg_id.encode("utf-8") + b"." + timestamp.encode("ascii") + b"." + raw_body
    expected = base64.b64encode(
        hmac.new(signing_secret, signed_payload, hashlib.sha256).digest()
    ).decode("ascii")

    for candidate in signatures.split():
        if "," not in candidate:
            continue
        version, supplied = candidate.split(",", 1)
        if version == "v1" and hmac.compare_digest(expected, supplied):
            return True
    return False


def _failure_reason(event_type: str, data: dict[str, Any]) -> str | None:
    detail_key = {
        "email.bounced": "bounce",
        "email.suppressed": "suppressed",
        "email.failed": "failed",
        "email.delivery_delayed": "delivery_delayed",
        "email.complained": "complaint",
    }.get(event_type)
    if not detail_key:
        return None
    detail = data.get(detail_key)
    if isinstance(detail, dict):
        reason = detail.get("message") or detail.get("reason") or detail.get("type")
        if reason:
            return str(reason)[:500]
    if isinstance(detail, str):
        return detail[:500]
    return None


@resend_webhook_bp.post("/webhooks/resend")
@csrf.exempt
@limiter.limit("120 per minute")
def resend_webhook() -> Response:
    raw_body = request.get_data(cache=True)
    if not _verify_svix_signature(raw_body):
        return Response("invalid webhook signature", status=400, mimetype="text/plain")

    try:
        event = json.loads(raw_body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return Response("invalid payload", status=400, mimetype="text/plain")

    event_type = str(event.get("type") or "")
    status = _STATUS_MAP.get(event_type)
    if not status:
        return Response(status=204)

    data = event.get("data")
    if not isinstance(data, dict):
        return Response("invalid event data", status=400, mimetype="text/plain")

    provider_message_id = str(data.get("email_id") or data.get("id") or "").strip()
    if not provider_message_id:
        return Response("missing email id", status=400, mimetype="text/plain")

    recipients = data.get("to") or []
    recipient = ""
    if isinstance(recipients, list) and recipients:
        recipient = str(recipients[0]).strip().lower()
    elif isinstance(recipients, str):
        recipient = recipients.strip().lower()

    reason = _failure_reason(event_type, data)
    execute(
        """
        INSERT INTO email_delivery_events(
            provider_message_id, recipient, provider, email_type, status,
            failure_reason, created_at, updated_at, last_event_at
        )
        VALUES(%s,%s,'RESEND','TRANSACTIONAL',%s,%s,NOW(),NOW(),NOW())
        ON CONFLICT(provider_message_id) DO UPDATE SET
            recipient=CASE
                WHEN EXCLUDED.recipient <> '' THEN EXCLUDED.recipient
                ELSE email_delivery_events.recipient
            END,
            status=EXCLUDED.status,
            failure_reason=EXCLUDED.failure_reason,
            updated_at=NOW(),
            last_event_at=NOW()
        """,
        (provider_message_id, recipient, status, reason),
    )

    return Response(status=204)
