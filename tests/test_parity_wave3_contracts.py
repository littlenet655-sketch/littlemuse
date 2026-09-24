"""Contracts for LittleMuse Parity Wave 3 messaging."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_message_replies_are_same_conversation_targets_only():
    api = text("mobile/api.py")
    migration = text("db/migrations/20260924000006_message_replies_reactions.sql")
    service = text("childMessage/service.py")
    assert "reply_to_message_id" in migration
    assert "REFERENCES child_messages(child_message_id) ON DELETE SET NULL" in migration
    assert 'AND conversation_id=%s' in api
    assert "reply_target_unavailable" in api
    assert "reply_message_text" in service
    assert "reply_sender_child_id" in service


def test_message_reactions_are_allowlisted_and_conversation_gated():
    api = text("mobile/api.py")
    migration = text("db/migrations/20260924000006_message_replies_reactions.sql")
    assert "CREATE TABLE IF NOT EXISTS message_reactions" in migration
    assert 'allowed = {"❤️", "😂", "😮", "👏", "🔥", "⭐"}' in api
    assert "def mobile_kids_message_reaction" in api
    assert 'conversation(uid, peer_id)' in api
    assert "message_not_found" in api


def test_sender_can_only_read_review_not_blocked_messages():
    service = text("childMessage/service.py")
    assert "m.moderation_status = 'ALLOWED'" in service
    assert "m.sender_child_id = %s AND m.moderation_status = 'REVIEW'" in service
    assert "OR m.sender_child_id = %s)" not in service


def test_chat_media_is_bounded_direct_r2_and_fail_closed():
    api = text("mobile/api.py")
    migration = text("db/migrations/20260924000007_chat_media_uploads.sql")
    chat_media = text("services/chat_media.py")
    assert "CREATE TABLE IF NOT EXISTS chat_upload_sessions" in migration
    assert "media_type IN ('IMAGE','VIDEO')" in migration
    assert 'max_bytes = 10 * 1024 * 1024 if media_type == "IMAGE" else 30 * 1024 * 1024' in api
    assert "signed_upload_url" in api
    assert "media_size_mismatch" in api
    assert "media_mime_mismatch" in api
    assert "moderate_chat_media" in api
    assert 'if media_type not in {"IMAGE", "VIDEO"}' in chat_media
    assert 'decision.action == "ALLOW"' in chat_media
    assert 'decision.action == "BLOCK"' in chat_media
    assert '"action": "REVIEW"' in chat_media


def test_review_media_is_private_until_parent_sanitized_approval():
    api = text("mobile/api.py")
    chat_media = text("services/chat_media.py")
    assert 'm.get("moderation_status") != "ALLOWED"' in api
    assert 'uid == m["sender_child_id"]' in api
    assert 'role_u == "PARENT"' in api
    assert 'm.get("moderation_status") == "REVIEW"' in api
    assert "promote_reviewed_chat_media" in api
    assert "block_reviewed_chat_media" in api
    assert "sanitize_and_promote_media" in chat_media
    assert '"chat"' in chat_media


def test_abandoned_chat_quarantine_has_bounded_reaper():
    media = text("services/chat_media.py")
    api = text("mobile/api.py")
    assert "def reconcile_abandoned_chat_upload_sessions" in media
    assert "LIMIT %s" in media
    assert "status IN ('PENDING','EXPIRED')" in media
    assert "REVIEW sessions are intentionally excluded" in media
    assert 'res["abandoned_chat_uploads"]' in api
