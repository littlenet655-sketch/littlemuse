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

def test_native_social_stitch_routes_are_registered_once():
    auth_api=text("auth/api.py")
    stitch=text("mobile/stitch_api.py")
    assert "from mobile.stitch_api import register_mobile_stitch_api" in auth_api
    assert "register_mobile_stitch_api(api_bp)" in auth_api
    assert "/api/mobile/v1/kids/saved" in stitch
    assert "/api/mobile/v1/kids/profiles/<int:target_id>" in stitch
    assert "/api/mobile/v1/kids/profiles/<int:target_id>/actions" in stitch
    assert "/api/mobile/v1/kids/reports" in stitch
    assert "/api/mobile/v1/kids/chat/<int:peer_id>/share" in stitch
    # Post detail already lives in mobile/api.py; stitch registration must not
    # add a second Flask rule for the same URL.
    assert "/api/mobile/v1/kids/posts/<int:post_id>" not in stitch


def test_parent_viewing_insights_uses_bearer_mobile_alias():
    client=text("mobile_app/src/api/client.ts")
    api=text("mobile/api.py")
    assert "/api/mobile/v1/parent/child/<int:child_id>/viewing-insights" in api
    assert "/api/mobile/v1/parent/child/${childId}/viewing-insights" in client
    assert "parentViewingInsights: (childId: number) => `/api/parent/child/" not in client

