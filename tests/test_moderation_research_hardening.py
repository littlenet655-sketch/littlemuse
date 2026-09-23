from safety import text_service, visual_service
from safety.policy import decide


def test_long_video_without_temporal_coverage_cannot_auto_publish(monkeypatch):
    monkeypatch.setattr(visual_service, "video_duration_seconds", lambda _path: 180.0)
    monkeypatch.setenv("LITTLENET_VIDEO_MAX_AUTO_ALLOW_GAP_SECONDS", "12")
    coverage = visual_service.video_sampling_coverage("video.mp4", requested=8)
    assert coverage["coverage_complete"] is False
    signals = {
        "category": "VIDEO",
        "adult_score": 0,
        "sexual_score": 0,
        "violence_score": 0,
        "weapon_score": 0,
        "toxicity_score": 0,
        "general_score": 0,
        "partial_safety_failure": True,
        "model_signals": coverage,
    }
    assert decide(signals).action == "REVIEW"


def test_covered_short_video_remains_eligible_for_allow(monkeypatch):
    monkeypatch.setattr(visual_service, "video_duration_seconds", lambda _path: 30.0)
    monkeypatch.setenv("LITTLENET_VIDEO_MAX_AUTO_ALLOW_GAP_SECONDS", "12")
    assert visual_service.video_sampling_coverage("video.mp4", requested=4)["coverage_complete"] is True


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
