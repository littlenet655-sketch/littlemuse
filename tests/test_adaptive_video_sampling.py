from safety.video_service import _initial_frame_indices, _signals_uncertain


def _signals(**overrides):
    base = {
        "category": "IMAGE",
        "adult_score": 0.0,
        "sexual_score": 0.0,
        "weapon_score": 0.0,
        "violence_score": 0.0,
        "toxicity_score": 0.0,
        "general_score": 0.0,
        "partial_safety_failure": False,
        "total_safety_failure": False,
    }
    base.update(overrides)
    return base


def test_first_pass_is_first_plus_later_frame():
    assert _initial_frame_indices(100, 8) == [0, 69]
    assert _initial_frame_indices(2, 8) == [0, 1]
    assert _initial_frame_indices(1, 8) == [0]
    assert _initial_frame_indices(100, 1) == [0]


def test_clear_low_risk_frame_does_not_expand(monkeypatch):
    monkeypatch.setenv("LITTLENET_VIDEO_EXPAND_SCORE", "0.15")
    assert _signals_uncertain(_signals()) is False
    assert _signals_uncertain(_signals(general_score=0.10)) is False


def test_near_threshold_or_incomplete_frame_expands(monkeypatch):
    monkeypatch.setenv("LITTLENET_VIDEO_EXPAND_SCORE", "0.15")
    assert _signals_uncertain(_signals(general_score=0.15)) is True
    assert _signals_uncertain(_signals(adult_score=0.20)) is True
    assert _signals_uncertain(_signals(partial_safety_failure=True)) is True


def test_legacy_visual_entry_point_delegates_to_adaptive_sampler():
    from pathlib import Path

    source = Path("safety/visual_service.py").read_text(encoding="utf-8")
    block = source.split("def check_video(path,max_frames=None):", 1)[1]
    assert "from .video_service import check_video as adaptive_check_video" in block
    assert "return adaptive_check_video(path,max_frames=max_frames)" in block
