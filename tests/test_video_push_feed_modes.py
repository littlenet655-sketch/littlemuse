"""Tests for video delivery abstraction, push notifications, feed modes, and story views."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
import pytest

from services.curated_feed import get_feed_page
from services.push_notifications import (
    get_active_tokens_for_user,
    notify_child_content_status,
    notify_parent_safety_event,
    register_device_token,
    revoke_device_token,
    send_expo_push,
)
from services.video_delivery import (
    CloudflareStreamDeliveryProvider,
    SanitizedMP4DeliveryProvider,
    get_video_provider,
    probe_video_metadata,
    resolve_video_playback,
    video_delivery_healthcheck,
)


def test_probe_video_metadata_fallback():
    meta = probe_video_metadata("non_existent_file.mp4")
    assert meta["duration_ms"] == 15000
    assert meta["width"] == 1080
    assert meta["height"] == 1920
    assert meta["aspect_ratio"] == "9:16"


def test_video_delivery_provider_selection(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_STREAM_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_STREAM_API_TOKEN", raising=False)
    p = get_video_provider()
    assert isinstance(p, SanitizedMP4DeliveryProvider)
    assert p.provider_name == "R2_SANITIZED_MP4"

    # Stream activates only with an explicit flag and complete server-side config.
    monkeypatch.setenv("CLOUDFLARE_STREAM_ENABLED", "1")
    monkeypatch.setenv("CLOUDFLARE_STREAM_ACCOUNT_ID", "acc_123")
    monkeypatch.setenv("CLOUDFLARE_STREAM_API_TOKEN", "tok_abc")
    monkeypatch.setenv("CLOUDFLARE_STREAM_SUBDOMAIN", "customer-test")
    p2 = get_video_provider()
    assert isinstance(p2, CloudflareStreamDeliveryProvider)
    assert p2.provider_name == "CLOUDFLARE_STREAM"
    assert p2.is_configured() is True



def test_cloudflare_stream_ingest_uses_private_direct_upload(tmp_path, monkeypatch):
    video = tmp_path / "sanitized.mp4"
    video.write_bytes(b"video-bytes")

    monkeypatch.setenv("CLOUDFLARE_STREAM_ENABLED", "1")
    monkeypatch.setenv("CLOUDFLARE_STREAM_ACCOUNT_ID", "acc_123")
    monkeypatch.setenv("CLOUDFLARE_STREAM_API_TOKEN", "tok_abc")
    monkeypatch.setenv("CLOUDFLARE_STREAM_SUBDOMAIN", "customer-test")

    provider = CloudflareStreamDeliveryProvider()
    seen = {"api": [], "upload": []}

    def fake_api(method, suffix, json_body=None):
        seen["api"].append((method, suffix, json_body))
        if suffix == "/direct_upload":
            return {"uid": "stream_uid_1", "uploadURL": "https://upload.videodelivery.net/once"}
        if suffix == "/stream_uid_1":
            return {
                "uid": "stream_uid_1",
                "readyToStream": False,
                "status": {"state": "inprogress"},
                "duration": 12,
                "input": {"width": 720, "height": 1280},
            }
        raise AssertionError(suffix)

    upload_response = MagicMock()
    upload_response.raise_for_status.return_value = None

    monkeypatch.setattr(provider, "_api_request", fake_api)
    monkeypatch.setattr("services.video_delivery.requests.post", lambda url, files, timeout: (seen["upload"].append((url, timeout)) or upload_response))
    monkeypatch.setattr("services.video_delivery.fetch_one", lambda *a, **k: {"media_id": 44})
    writes = []
    monkeypatch.setattr("services.video_delivery.execute", lambda sql, params=(), **kwargs: writes.append((sql, params)))

    result = provider.ingest(
        post_id=101,
        source_r2_key="uploads/r2/quarantine/101/source.mp4",
        published_ref="uploads/r2/published/101/clean.mp4",
        poster_ref="uploads/r2/published/101/poster.jpg",
        local_file=video,
        metadata={"duration_ms": 12000, "width": 720, "height": 1280, "aspect_ratio": "9:16"},
    )

    provision = seen["api"][0]
    assert provision[0:2] == ("POST", "/direct_upload")
    assert provision[2]["requireSignedURLs"] is True
    assert seen["upload"][0][0].startswith("https://upload.videodelivery.net/")
    assert result["provider_asset_id"] == "stream_uid_1"
    assert result["status"] == "ENCODING"
    assert writes



def test_cloudflare_stream_ingest_reuses_existing_uid_on_retry(tmp_path, monkeypatch):
    video = tmp_path / "sanitized.mp4"
    video.write_bytes(b"video-bytes")
    monkeypatch.setenv("CLOUDFLARE_STREAM_ENABLED", "1")
    monkeypatch.setenv("CLOUDFLARE_STREAM_ACCOUNT_ID", "acc_123")
    monkeypatch.setenv("CLOUDFLARE_STREAM_API_TOKEN", "tok_abc")
    monkeypatch.setenv("CLOUDFLARE_STREAM_SUBDOMAIN", "customer-test")

    provider = CloudflareStreamDeliveryProvider()
    existing = {
        "media_id": 44,
        "post_id": 101,
        "provider": "CLOUDFLARE_STREAM",
        "provider_asset_id": "stream_uid_existing",
        "playback_id": "stream_uid_existing",
        "published_reference": "uploads/r2/published/101/clean.mp4",
        "status": "ENCODING",
    }
    monkeypatch.setattr("services.video_delivery.get_video_asset", lambda _post_id: existing)
    monkeypatch.setattr(
        provider,
        "_api_request",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("retry must not provision another Stream asset")),
    )

    result = provider.ingest(
        post_id=101,
        source_r2_key="uploads/r2/quarantine/101/source.mp4",
        published_ref=existing["published_reference"],
        poster_ref=None,
        local_file=video,
    )

    assert result["provider_asset_id"] == "stream_uid_existing"
    assert result["status"] == "ENCODING"

def test_cloudflare_stream_ready_playback_uses_signed_hls(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_STREAM_ENABLED", "1")
    monkeypatch.setenv("CLOUDFLARE_STREAM_ACCOUNT_ID", "acc_123")
    monkeypatch.setenv("CLOUDFLARE_STREAM_API_TOKEN", "tok_abc")
    monkeypatch.setenv("CLOUDFLARE_STREAM_SUBDOMAIN", "customer-test.cloudflarestream.com")

    provider = CloudflareStreamDeliveryProvider()
    asset = {
        "media_id": 44,
        "post_id": 101,
        "published_reference": "uploads/r2/published/101/clean.mp4",
        "poster_reference": None,
        "provider_asset_id": "stream_uid_1",
        "playback_id": "stream_uid_1",
        "status": "READY",
        "duration_ms": 12000,
        "width": 720,
        "height": 1280,
        "aspect_ratio": "9:16",
    }

    monkeypatch.setattr("services.video_delivery.is_authorized_viewer", lambda *a, **k: True)
    monkeypatch.setattr(provider, "_signed_token", lambda uid, expires_at: "signed.jwt.token")
    result = provider.get_playback_info(asset, viewer_id=7, viewer_role="CHILD", expires_seconds=300)

    assert result["delivery_type"] == "HLS"
    assert result["provider"] == "CLOUDFLARE_STREAM"
    assert result["playback_url"] == "https://customer-test.cloudflarestream.com/signed.jwt.token/manifest/video.m3u8"
    assert result["playback_expires_at"] > int(__import__("time").time())

def test_sanitized_mp4_playback_authorized():
    asset = {
        "media_id": 99,
        "post_id": 101,
        "published_reference": "uploads/r2/reels/1/clean.mp4",
        "poster_reference": "uploads/r2/reels/1/poster.jpg",
        "provider": "R2_SANITIZED_MP4",
        "playback_id": "play_101",
        "duration_ms": 12000,
        "width": 1080,
        "height": 1920,
        "aspect_ratio": "9:16",
    }
    provider = SanitizedMP4DeliveryProvider()
    with patch("services.video_delivery.resolve_media_delivery", return_value={"url": "https://signed.r2/clean.mp4", "delivery_mode": "DIRECT_SIGNED", "expires_at": 1700000600}):
        res = provider.get_playback_info(asset, viewer_id=1, viewer_role="CHILD")
        assert res["playback_url"] == "https://signed.r2/clean.mp4"
        assert res["delivery_type"] == "MP4"
        assert res["duration_ms"] == 12000
        assert res["aspect_ratio"] == "9:16"


def test_cloudflare_stream_playback_fail_closed_unauthorized():
    asset = {
        "media_id": 99,
        "post_id": 101,
        "published_reference": "uploads/r2/reels/1/clean.mp4",
        "playback_id": "cfs_101",
    }
    provider = CloudflareStreamDeliveryProvider()
    with patch("services.video_delivery.is_authorized_viewer", return_value=False):
        res = provider.get_playback_info(asset, viewer_id=2, viewer_role="CHILD")
        assert res["playback_url"] is None
        assert res["delivery_mode"] == "DENIED"



def test_video_delivery_healthcheck_private_r2_default(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_STREAM_ENABLED", raising=False)
    result = video_delivery_healthcheck()
    assert result == {
        "ok": True,
        "provider": "R2_SANITIZED_MP4",
        "adaptive_streaming": False,
        "mode": "private_r2_fallback",
    }


def test_video_delivery_healthcheck_stream_api(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_STREAM_ENABLED", "1")
    monkeypatch.setenv("CLOUDFLARE_STREAM_ACCOUNT_ID", "acc_123")
    monkeypatch.setenv("CLOUDFLARE_STREAM_API_TOKEN", "tok_abc")
    monkeypatch.setenv("CLOUDFLARE_STREAM_SUBDOMAIN", "customer-test")

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"success": True, "result": []}
    monkeypatch.setattr("services.video_delivery.requests.get", lambda *a, **k: response)

    result = video_delivery_healthcheck()
    assert result["ok"] is True
    assert result["provider"] == "CLOUDFLARE_STREAM"
    assert result["mode"] == "api_verified"

def test_push_notifications_privacy_filter():
    sent_payloads = []

    def mock_post(url, json=None, headers=None, timeout=None):
        sent_payloads.extend(json or [])
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"data": [{"status": "ok"}]}
        return mock_resp

    with patch("services.push_notifications.requests.post", side_effect=mock_post):
        tokens = ["ExponentPushToken[abc123xyz]"]
        leaky_data = {
            "postId": 42,
            "password": "supersecretpassword",
            "embedding": [0.1, 0.2, 0.3],
            "raw_text": "Private text",
            "safe_tag": "notification",
        }
        ok = send_expo_push(tokens, title="Test", body="Hello", data=leaky_data)
        assert ok is True
        assert len(sent_payloads) == 1
        msg = sent_payloads[0]
        # Ensure private/sensitive keys were stripped
        assert "password" not in msg["data"]
        assert "embedding" not in msg["data"]
        assert "raw_text" not in msg["data"]
        assert msg["data"]["postId"] == 42
        assert msg["data"]["safe_tag"] == "notification"


def test_feed_modes_server_filtering():
    sample_session_items = [
        {"source_type": "SOCIAL", "source_id": 1, "category": "General", "moderation_status": "ALLOWED", "ranking_metadata": {"is_following": True}},
        {"source_type": "CURATED", "source_id": 10, "category": "Science", "moderation_status": "ALLOWED"},
        {"source_type": "SOCIAL", "source_id": 2, "category": "Art", "moderation_status": "ALLOWED", "ranking_metadata": {"is_following": False}},
        {"source_type": "CURATED", "source_id": 20, "category": "Math", "moderation_status": "ALLOWED"},
    ]

    with patch("services.curated_feed.get_or_create_feed_session", return_value=("sess-123", sample_session_items)), \
         patch("services.curated_feed._has_refill_candidates", return_value=False):
        # For You: all items
        page_all = get_feed_page(child_id=1, surface="FEED", mode="for_you")
        assert len(page_all["items"]) == 4

        # Friends: only SOCIAL items from ACTIVE friendships
        page_friends = get_feed_page(child_id=1, surface="FEED", mode="friends")
        assert len(page_friends["items"]) == 1
        assert page_friends["items"][0]["source_id"] == 1

        # Learn: only CURATED or educational items
        page_learn = get_feed_page(child_id=1, surface="FEED", mode="learn")
        assert len(page_learn["items"]) == 3  # 2 curated + 1 art social
        assert all(it["source_type"] == "CURATED" or it["category"] in {"Science", "Math", "Art"} for it in page_learn["items"])
