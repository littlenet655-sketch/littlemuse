from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def text(path):
    return (ROOT / path).read_text(encoding="utf-8")

def test_creator_chat_schema_and_api_are_server_side_and_niche_locked():
    migration = text("db/migrations/20261006154500_creator_ai_chat.sql")
    assert "creator_chat_messages" in migration
    assert "curated_creators(creator_id)" in migration
    mobile = text("mobile/api.py")
    assert "/api/mobile/v1/kids/creators/<int:creator_id>/chat" in mobile
    assert "generate_creator_reply" in mobile
    client = text("services/ai/client.py")
    assert "def generate_creator_reply" in client
    assert "Never reveal or discuss the underlying model" in client
    assert "Stay inside this creator niche" in client

def test_creator_chat_mobile_route_is_only_for_curated_creators():
    reels = text("mobile_app/src/screens/kids/ReelsScreen.tsx")
    assert "CreatorChat" in reels
    assert "item.source_type !== 'SOCIAL'" in reels
    types = text("mobile_app/src/navigation/types.ts")
    assert "CreatorChat:" in types


def test_creator_reply_is_safety_checked_before_storage():
    mobile = text("mobile/api.py")
    body = mobile.split("def mobile_kids_creator_chat")[1].split("def mobile_kids_message_reaction")[0]
    assert 'reply_decision = evaluate(uid, "TEXT", reply_text)' in body
    assert "reply_pii = scan_pii(reply_text)" in body
    assert "reply_decision.action != \"ALLOW\"" in body


def test_creator_chat_mobile_uses_bounded_generation_timeout_and_feed_entrypoint():
    api = text("mobile_app/src/api/creatorChat.ts")
    assert "timeoutMs: 35_000" in api
    feed = text("mobile_app/src/screens/kids/FeedScreen.tsx")
    assert "item.source_type === 'CURATED' && item.creator_id" in feed
    assert "nav.navigate('CreatorChat', creatorChat)" in feed


def test_creator_chat_review_like_input_fails_closed_without_fake_parent_queue():
    mobile = text("mobile/api.py")
    body = mobile.split("def mobile_kids_creator_chat")[1].split("def mobile_kids_message_reaction")[0]
    assert '"CREATOR_CHAT_MESSAGE_HELD"' in body
    assert '"MESSAGE_BLOCKED"' in body
    assert '"REVIEW_REQUIRED"' not in body


def test_creator_reply_uses_single_bounded_provider_attempt():
    client = text("services/ai/client.py")
    body = client.split("def generate_creator_reply")[1].split("# ── 6.")[0]
    assert "read_timeout=20.0" in body
    assert "max_retries=0" in body
    provider = text("services/ai/providers/k2.py")
    assert "read_timeout: Optional[float] = None" in provider
    assert "max_retries: Optional[int] = None" in provider
