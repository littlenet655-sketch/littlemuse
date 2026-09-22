from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_final_child_creation_range_is_6_to_16():
    src = read("auth/child_provisioning.py")
    assert "if not 6 <= age <= 16:" in src
    assert "Child age must be between 6 and 16." in src


def test_parent_activity_returns_privacy_respecting_viewing_insights():
    src = read("mobile/api.py")
    assert '"views_7d"' in src
    assert '"reels_watched_7d"' in src
    assert '"reel_watch_minutes_7d"' in src
    assert '"top_categories"' in src
    assert "FROM content_impressions" in src
    assert "NOW() - INTERVAL '7 days'" in src


def test_production_modal_image_runtime_enables_ocr():
    src = read("modal_ai.py")
    assert '"rapidocr-onnxruntime>=1.4,<2"' in src
    assert '"LITTLENET_ENABLE_OCR": "1"' in src


def test_native_safe_delete_endpoints_remain_bearer_authorized():
    src = read("mobile/api.py")
    assert '@bp.route("/api/mobile/v1/kids/posts/<int:post_id>", methods=["DELETE"])' in src
    assert '@bp.route("/api/mobile/v2/kids/stories/<int:story_id>", methods=["DELETE"])' in src
    assert 'def mobile_kids_delete_post(post_id):' in src
    assert 'def mobile_kids_delete_story(story_id):' in src
