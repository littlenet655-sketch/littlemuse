from pathlib import Path

from safety import pii_service, scene_sampler

ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_deterministic_pii_remains_authoritative_without_presidio(monkeypatch):
    # Optional OSS enrichment can never remove LittleNet's hard phone blocker.
    monkeypatch.setenv("LITTLENET_ENABLE_PRESIDIO", "0")
    result = pii_service.scan_pii("call me at 9876543210")
    assert result["detected"] is True
    assert result["policy_action"] == "BLOCK"
    assert "PHONE_NUMBER" in result["categories"]
    assert "[PHONE]" in result["redacted_text"]


def test_scene_and_uniform_samples_share_one_hard_budget(monkeypatch):
    monkeypatch.setattr(scene_sampler, "scene_sample_indices", lambda *_args, **_kwargs: [3, 17, 33])
    indices = scene_sampler.combined_frame_indices("fake.mp4", total_frames=100, requested=8)
    assert 3 in indices and 17 in indices and 33 in indices
    assert len(indices) <= 8
    assert len(indices) == len(set(indices))


def test_runtime_video_paths_use_scene_aware_service():
    moderation = text("safety/moderation_service.py")
    server = text("ai_server.py")
    assert "from .video_service import check_video" in moderation
    assert "from safety.video_service import check_video" in server
    assert '"sampling_strategy":"adaptive_first_later_then_scene_uniform_if_uncertain"' in text("safety/video_service.py")
    assert "from .scene_sampler import combined_frame_indices" in text("safety/video_service.py")
    assert "planned=combined_frame_indices(path,total,budget)" in text("safety/video_service.py")


def test_presidio_is_local_optional_enrichment_with_fail_safe_rules():
    adapter = text("safety/presidio_adapter.py")
    pii = text("safety/pii_service.py")
    assert "presidio_analyzer" in adapter
    assert "en_core_web_sm" in adapter
    assert "Presidio" in pii
    assert "deterministic" in pii.lower()
    assert "presidio-analyzer" in text("requirements-safety.txt")


def test_ai_runtime_declares_scene_detection_dependency():
    assert "scenedetect-headless" in text("requirements-ai.txt")
