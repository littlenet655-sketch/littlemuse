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


def test_default_video_coverage_boundary_is_intentional(monkeypatch):
    monkeypatch.setenv("LITTLENET_VIDEO_SAMPLE_INTERVAL_SECONDS", "8")
    monkeypatch.setenv("LITTLENET_VIDEO_MIN_FRAMES", "3")
    monkeypatch.setenv("LITTLENET_VIDEO_MAX_FRAMES", "8")
    monkeypatch.setenv("LITTLENET_VIDEO_MAX_AUTO_ALLOW_GAP_SECONDS", "12")

    expected = {
        30.0: (5, True),
        60.0: (8, True),
        84.0: (8, True),
        90.0: (8, False),
        180.0: (8, False),
    }
    for duration, (requested, complete) in expected.items():
        monkeypatch.setattr(
            visual_service,
            "video_duration_seconds",
            lambda _path, d=duration: d,
        )
        actual_requested = visual_service._video_sample_count("video.mp4")
        coverage = visual_service.video_sampling_coverage("video.mp4", actual_requested)
        assert actual_requested == requested
        assert coverage["coverage_complete"] is complete


def test_incomplete_default_video_coverage_routes_safe_signal_to_review(monkeypatch):
    monkeypatch.setattr(visual_service, "video_duration_seconds", lambda _path: 90.0)
    monkeypatch.setenv("LITTLENET_VIDEO_MAX_AUTO_ALLOW_GAP_SECONDS", "12")
    coverage = visual_service.video_sampling_coverage("video.mp4", requested=8)
    signals = {
        "category": "VIDEO",
        "adult_score": 0,
        "sexual_score": 0,
        "violence_score": 0,
        "weapon_score": 0,
        "toxicity_score": 0,
        "general_score": 0,
        "partial_safety_failure": not coverage["coverage_complete"],
        "model_signals": coverage,
    }
    assert coverage["coverage_complete"] is False
    assert decide(signals).action == "REVIEW"


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
