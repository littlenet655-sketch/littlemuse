from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]

def text(path):
    return (ROOT / path).read_text(encoding="utf-8")

def test_react_native_expo_is_only_mobile_source():
    pkg=json.loads(text("mobile_app/package.json"))
    app=json.loads(text("mobile_app/app.json"))
    assert str(pkg["dependencies"]["expo"]).startswith("57.")
    assert str(pkg["dependencies"]["react-native"]).startswith("0.86.")
    assert app["expo"]["android"]["package"] == "com.littlenet.app"
    assert not (ROOT / "mobile_flutter").exists()
    assert not (ROOT / "android").exists()

def test_mobile_api_identifies_react_native_expo():
    api=text("mobile/api.py")
    assert 'client="react-native"' in api
    assert 'framework="expo"' in api

def test_v2_direct_upload_and_processing_contract_is_mapped():
    api=text("mobile/api.py")
    client=text("mobile_app/src/api/client.ts")
    assert '/api/mobile/v2/uploads/session' in api
    assert '/api/mobile/v2/uploads/<upload_id>/complete' in api
    assert '/api/mobile/v2/posts/<int:post_id>/processing-status' in api
    assert '/api/mobile/v2/uploads/session' in client
    assert 'processing-status' in client

def test_scene_aware_video_moderation_is_active():
    visual=text("safety/visual_service.py")
    assert 'from .scene_sampler import combined_frame_indices' in visual
    assert 'combined_frame_indices(path,total,max_frames)' in visual

def test_replit_contract_points_to_single_stack():
    docs='\\n'.join(text(p) for p in ["AGENTS.md","STACK.md","REPLIT.md","README.md"])
    assert 'mobile_app/' in docs
    assert 'React Native' in docs
    assert 'EXPO_PUBLIC_API_BASE_URL' in docs


def test_production_image_ocr_is_shipped_enabled_and_preflighted():
    modal_ai = text("modal_ai.py")
    req = text("requirements-ai.txt")
    docs = text("docs/IMAGE_OCR_SAFETY.md")
    assert "rapidocr-onnxruntime" in modal_ai
    assert "rapidocr-onnxruntime" in req
    assert '"LITTLENET_ENABLE_OCR": "1"' in modal_ai
    assert '"LITTLENET_ENABLE_OCR_VIDEO_FRAMES": "0"' in modal_ai
    assert 'report["ocr"]' in modal_ai
    assert "future work" not in docs.lower()
