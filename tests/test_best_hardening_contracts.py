"""Release contracts for the final BEST-level social/supervision hardening."""
from pathlib import Path

import services.controls as controls

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_explicit_empty_parent_categories_fail_closed(monkeypatch):
    monkeypatch.setattr(
        controls,
        "controls_for_child",
        lambda child_id: {
            "allowed_categories": [],
            "educational_only_feed": False,
        },
    )
    assert controls._effective_categories_uncached(42) == []


def test_comment_controls_are_server_authoritative_and_cursor_paginated():
    api = text("mobile/api.py")
    migration = text("db/migrations/20260924000004_social_supervision_hardening.sql")
    assert 'feature_allowed(uid, "comments")' in api
    assert 'comments_enabled' in api
    assert 'before_id' in api
    assert 'mobile_delete_comment' in api
    assert 'mobile_comments_setting' in api
    assert '@limiter.limit("12 per minute", methods=["POST"])' in api
    assert 'ADD COLUMN IF NOT EXISTS allow_comments BOOLEAN NOT NULL DEFAULT TRUE' in migration
    assert 'ADD COLUMN IF NOT EXISTS comments_enabled BOOLEAN NOT NULL DEFAULT TRUE' in migration
    assert 'idx_comments_post_cursor' in migration


def test_parent_activity_is_paginated_and_chat_visibility_is_metadata_only():
    api = text("mobile/api.py")
    mobile = text("mobile_app/src/screens/parent/ParentScreens.tsx")
    assert 'recent_chat_partners' in api
    assert 'messages_30d' in api
    assert 'next_cursor' in api
    assert 'Load older activity' in mobile
    assert 'Shows who your child has interacted with, not private message content.' in mobile
    # The supervision query must not select message_text or media_path.
    start = api.index('recent_chat_partners = fetch_all(')
    end = api.index('return jsonify(', start)
    query_block = api[start:end]
    assert 'message_text' not in query_block
    assert 'media_path' not in query_block


def test_profile_story_rings_are_real_buttons_to_exact_story_viewer():
    own = text("mobile_app/src/screens/kids/OwnProfileScreen.tsx")
    other = text("mobile_app/src/screens/kids/OtherProfileScreen.tsx")
    for source in (own, other):
        assert 'const openStory = ' in source
        assert "nav.navigate('Stories'" in source
        assert 'accessibilityRole="button"' in source
        assert 'onPress={() => openStory(s)}' in source


def test_child_share_actions_do_not_open_unrestricted_os_share_sheet():
    feed_card = text("mobile_app/src/kids/PostCard.tsx")
    reels = text("mobile_app/src/screens/kids/ReelsScreen.tsx")
    feed = text("mobile_app/src/screens/kids/FeedScreen.tsx")
    assert 'Share.share' not in feed_card
    assert 'Share.share' not in reels
    assert "openShare: true" in feed
    assert "openShare: true" in reels
    assert 'Sharing stays inside LittleMuse' in feed_card
    assert 'Sharing stays inside LittleMuse' in reels


def test_stale_offline_policy_has_separate_server_freshness_clock():
    core = text("mobile_app/src/kids/offlinePolicyCore.ts")
    storage = text("mobile_app/src/kids/offlineScreenTime.ts")
    assert 'OFFLINE_POLICY_MAX_AGE_MS = 24 * 60 * 60 * 1000' in core
    assert 'server_synced_at_ms' in core
    assert 'gateForOfflinePolicy' in core
    assert 'server_synced_at_ms: confirmedAt' in storage
    assert 'saved_at_ms: Date.now()' in storage
