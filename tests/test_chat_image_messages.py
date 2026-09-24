"""Wave 3 contracts: private safety-checked image messages."""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_chat_image_schema_is_peer_bound_and_idempotent():
    migration = text("db/migrations/20260924000006_chat_image_upload.sql")
    assert "target_id INTEGER REFERENCES users(user_id)" in migration
    assert "('POST','REEL','STORY','MESSAGE')" in migration
    assert "ADD COLUMN IF NOT EXISTS upload_id UUID REFERENCES upload_sessions" in migration
    assert "idx_child_messages_upload_id_uniq" in migration


def test_message_upload_session_is_relationship_and_parent_gated():
    api = text("mobile/api.py")
    start = api.index('def mobile_v2_upload_session')
    end = api.index('@bp.route("/api/mobile/v2/uploads/mock-put', start)
    block = api[start:end]
    assert '"message"' in block
    assert 'feature = (' in block and '"messaging" if kind == "message"' in block
    assert "can_interact(uid, target_id)" in block
    assert 'feature_allowed(target_id, "messaging")' in block
    assert 'message_image_only' in block
    assert 'max_bytes = 10 * 1024 * 1024' in block
    assert 'target_id' in block
    assert 'quarantine_scope = f"messages/{uid}"' in block


def test_chat_image_review_routes_as_message_not_post_image():
    service = text("services/chat_media.py")
    assert 'merged["message_media_type"] = "IMAGE"' in service
    assert 'record(child_id, "MESSAGE", message_id, merged, decision)' in service
    assert 'record(child_id, "IMAGE", message_id' not in service


def test_chat_image_sanitization_strips_exif(tmp_path):
    from services.chat_media import _sanitize_image

    source = tmp_path / "source.jpg"
    clean = tmp_path / "clean.jpg"
    image = Image.new("RGB", (32, 32), (100, 120, 140))
    exif = image.getexif()
    exif[315] = "LittleMuse test artist"
    image.save(source, format="JPEG", exif=exif)

    with Image.open(source) as original:
        assert original.getexif().get(315) == "LittleMuse test artist"

    _sanitize_image(source, clean)

    with Image.open(clean) as result:
        assert result.mode == "RGB"
        assert len(result.getexif()) == 0


def test_reviewed_chat_photo_never_delivers_before_allow_and_block_deletes_media():
    service = text("childMessage/service.py")
    api = text("mobile/api.py")
    chat_media = text("services/chat_media.py")

    # Receiver sees only ALLOWED; sender can see own pending REVIEW row.
    assert "m.moderation_status = 'ALLOWED' OR m.sender_child_id" in service

    # New image is born as REVIEW with no media exposure before moderation.
    assert "'IMAGE','Photo',NULL,%s,'REVIEW'" in chat_media

    # Parent BLOCK atomically clears the DB reference before post-commit deletion.
    assert "message_block_media_ref = review_message" in api
    assert "SET moderation_status='BLOCKED',media_path=NULL" in api
    commit = api.index("conn.commit()", api.index("def _resolve_parent_review"))
    cleanup = api.index("if message_block_media_ref:", api.index("def _resolve_parent_review"))
    assert commit < cleanup
    assert "_message_storage.delete_reference(message_block_media_ref)" in api


def test_chat_image_completion_uses_same_image_safety_evidence_pipeline():
    service = text("services/chat_media.py")
    assert "_make_image_moderation_proxy" in service
    assert "cached_or_none_for_file" in service
    assert "moderate_image_upload" in service
    assert 'evaluate(child_id, "IMAGE"' in service
    assert "decide(merged, safety_level(child_id), Config.ADULT_HARD_BLOCK_THRESHOLD)" in service
    assert "parent_notify(child_id, "MESSAGE_BLOCKED"" in service
    assert "A photo message needs safety review" in service
