"""Contracts for LittleMuse Parity Wave 2."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_story_reactions_are_allowlisted_parent_gated_and_durable():
    api = text("mobile/api.py")
    migration = text("db/migrations/20260924000005_story_interactions.sql")
    assert 'def mobile_kids_story_reaction' in api
    assert 'allowed = {"❤️", "😂", "😮", "👏", "🔥", "⭐"}' in api
    assert 'feature_allowed(uid, "messaging")' in api
    assert 'feature_allowed(owner_id, "messaging")' in api
    assert 'ON CONFLICT(story_id,child_id)' in api
    assert 'CREATE TABLE IF NOT EXISTS story_reactions' in migration
    assert 'UNIQUE(story_id, child_id)' in migration


def test_story_replies_use_existing_moderated_message_channel():
    api = text("mobile/api.py")
    start = api.index("def _send_story_reply_message")
    end = api.index("def _serializer", start)
    block = api[start:end]
    assert "scan_pii(text)" in block
    assert 'evaluate(uid, "TEXT", text)' in block
    assert "contextual_chat_risk" in block
    assert "evaluate_chat_safety" in block
    assert "'SHARED_POST'" in block
    assert "shared_post_id" in block
    assert 'parent_notify(uid, "REVIEW_REQUIRED"' in block
    assert 'def mobile_kids_story_reply' in api
    assert '_child_gate("messaging")' in api


def test_story_music_reuses_curated_server_catalog_and_validated_upload_lookup():
    api = text("mobile/api.py")
    assert '@bp.route("/api/mobile/v1/music/curated", methods=["GET"])' in api
    assert "FROM curated_music WHERE is_active=TRUE" in api
    assert 'SELECT * FROM curated_music WHERE music_id=%s AND is_active=TRUE' in api
    assert 'story_music_id' in api
    assert 'story_music_url' in api


def test_create_category_policy_is_fail_closed_in_mobile_ui():
    create = text("mobile_app/src/screens/kids/CreateScreen.tsx")
    assert "const canPublishCategory = categoryPolicyReady && allowedCategories.length > 0" in create
    assert "Posting is paused until your parent allows at least one content category." in create
    assert "Parent controls could not be verified. Sharing stays locked until they refresh." in create
