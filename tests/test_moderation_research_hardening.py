from safety import text_service, visual_service
from safety.policy import decide


def test_single_frame_is_complete_coverage(monkeypatch):
    # Single-frame policy (2026-09-23): one frame is the complete temporal
    # budget, so even a long video stays eligible for auto-allow on that
    # frame's own merits.
    monkeypatch.setattr(visual_service, "video_duration_seconds", lambda _path: 600.0)
    coverage = visual_service.video_sampling_coverage("video.mp4", requested=1)
    assert coverage["coverage_complete"] is True
    assert coverage["required_frames_for_auto_allow"] == 1
    signals = {
        "category": "VIDEO",
        "adult_score": 0,
        "sexual_score": 0,
        "violence_score": 0,
        "weapon_score": 0,
        "toxicity_score": 0,
        "general_score": 0,
        "partial_safety_failure": False,
        "model_signals": coverage,
    }
    assert decide(signals).action == "ALLOW"


def test_covered_short_video_remains_eligible_for_allow(monkeypatch):
    monkeypatch.setattr(visual_service, "video_duration_seconds", lambda _path: 30.0)
    monkeypatch.setenv("LITTLENET_VIDEO_MAX_AUTO_ALLOW_GAP_SECONDS", "4")
    assert visual_service.video_sampling_coverage("video.mp4", requested=10)["coverage_complete"] is True


def test_text_canonicalization_catches_common_sexual_evasion():
    variants = [
        "s.e.n.d me n.u.d.e pics",
        "send me n\u200budes",
        "s3nd me nud3 pics",
    ]
    for value in variants:
        normalized = text_service._normalized_text(value)
        assert "send me nude" in normalized
        assert text_service.check_text(value)["deterministic_sexual"] is True
