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
