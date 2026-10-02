import base64
import hashlib
import hmac
import json
import time

from flask import Flask


def _signed_headers(secret: str, body: bytes) -> dict[str, str]:
    msg_id = "msg_test_1"
    timestamp = str(int(time.time()))
    raw_secret = base64.b64decode(secret.removeprefix("whsec_"))
    signed = msg_id.encode() + b"." + timestamp.encode() + b"." + body
    signature = base64.b64encode(hmac.new(raw_secret, signed, hashlib.sha256).digest()).decode()
    return {
        "svix-id": msg_id,
        "svix-timestamp": timestamp,
        "svix-signature": f"v1,{signature}",
        "Content-Type": "application/json",
    }


def test_dev_otp_never_enabled_in_production(monkeypatch):
    from auth import parent_email_otp as otp

    monkeypatch.setattr(otp.Config, "_PRODUCTION", True)
    monkeypatch.setenv("ENABLE_DEV_OTP", "1")
    assert otp._dev_otp_enabled() is False


def test_dev_otp_requires_explicit_nonproduction_override(monkeypatch):
    from auth import parent_email_otp as otp

    monkeypatch.setattr(otp.Config, "_PRODUCTION", False)
    monkeypatch.delenv("ENABLE_DEV_OTP", raising=False)
    assert otp._dev_otp_enabled() is False

    monkeypatch.setenv("ENABLE_DEV_OTP", "1")
    assert otp._dev_otp_enabled() is True


def test_resend_webhook_rejects_invalid_signature(monkeypatch):
    from mailg.webhooks import resend_webhook_bp

    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", "whsec_" + base64.b64encode(b"secret").decode())
    app = Flask(__name__)
    app.config["TESTING"] = True
    from mailg import webhooks as webhook_module
    webhook_module.csrf.init_app(app)
    webhook_module.limiter.init_app(app)
    app.register_blueprint(resend_webhook_bp)

    client = app.test_client()
    response = client.post(
        "/webhooks/resend",
        data=b'{"type":"email.delivered","data":{"email_id":"x"}}',
        headers={
            "svix-id": "x",
            "svix-timestamp": str(int(time.time())),
            "svix-signature": "v1,invalid",
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 400


def test_resend_webhook_updates_delivery_state(monkeypatch):
    import mailg.webhooks as webhooks

    secret = "whsec_" + base64.b64encode(b"secret").decode()
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", secret)

    calls = []
    monkeypatch.setattr(webhooks, "execute", lambda sql, params=(): calls.append((sql, params)))

    app = Flask(__name__)
    app.config["TESTING"] = True
    webhooks.csrf.init_app(app)
    webhooks.limiter.init_app(app)
    app.register_blueprint(webhooks.resend_webhook_bp)

    payload = {
        "type": "email.bounced",
        "data": {
            "email_id": "email_123",
            "to": ["parent@example.com"],
            "bounce": {"message": "Mailbox does not exist", "type": "Permanent"},
        },
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    response = app.test_client().post(
        "/webhooks/resend",
        data=body,
        headers=_signed_headers(secret, body),
    )

    assert response.status_code == 204
    assert len(calls) == 1
    params = calls[0][1]
    assert params[0] == "email_123"
    assert params[1] == "parent@example.com"
    assert params[2] == "BOUNCED"
    assert "Mailbox does not exist" in params[3]


def test_cloudflare_stream_requires_complete_opt_in(monkeypatch):
    from services.video_delivery import CloudflareStreamDeliveryProvider

    monkeypatch.setenv("CLOUDFLARE_STREAM_ENABLED", "1")
    monkeypatch.setenv("CLOUDFLARE_STREAM_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_STREAM_API_TOKEN", "token")
    monkeypatch.delenv("CLOUDFLARE_STREAM_SUBDOMAIN", raising=False)
    assert CloudflareStreamDeliveryProvider().is_configured() is False

    monkeypatch.setenv("CLOUDFLARE_STREAM_SUBDOMAIN", "customer-test")
    assert CloudflareStreamDeliveryProvider().is_configured() is True

def test_historical_stream_asset_falls_back_to_private_r2(monkeypatch):
    import services.video_delivery as vd

    asset = {
        "media_id": 9,
        "post_id": 77,
        "provider": "CLOUDFLARE_STREAM",
        "playback_id": "placeholder_stream_id",
        "published_reference": "uploads/r2/published/reel-77.mp4",
        "poster_reference": None,
        "duration_ms": 15000,
        "width": 720,
        "height": 1280,
        "aspect_ratio": "9:16",
    }
    monkeypatch.setattr(vd, "get_video_asset", lambda post_id: asset)

    seen = {}
    def fake_r2_playback(self, media_asset, viewer_id, viewer_role, expires_seconds=vd.DEFAULT_SIGNED_URL_TTL):
        seen["provider"] = self.provider_name
        seen["asset"] = media_asset
        return {"playback_url": "https://signed-r2.example/reel.mp4", "delivery_type": "MP4"}

    monkeypatch.setattr(vd.SanitizedMP4DeliveryProvider, "get_playback_info", fake_r2_playback)

    result = vd.resolve_video_playback(77, viewer_id=5, viewer_role="CHILD")

    assert seen["provider"] == "R2_SANITIZED_MP4"
    assert seen["asset"]["published_reference"].endswith("reel-77.mp4")
    assert result["delivery_type"] == "MP4"

