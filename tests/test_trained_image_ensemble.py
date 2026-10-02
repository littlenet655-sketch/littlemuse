from pathlib import Path
from unittest.mock import patch

import pytest


def test_trained_image_ensemble_requires_both_checkpoint_files(tmp_path, monkeypatch):
    from safety import littlenet_trained_image as trained

    v2 = tmp_path / "v2.pth"
    v3 = tmp_path / "v3.pth"
    monkeypatch.setenv("LITTLENET_ENABLE_TRAINED_IMAGE_ENSEMBLE", "1")
    monkeypatch.setenv("LITTLENET_TRAINED_IMAGE_V2_PATH", str(v2))
    monkeypatch.setenv("LITTLENET_TRAINED_IMAGE_V3_PATH", str(v3))

    assert trained.available() is False

    v2.write_bytes(b"v2")
    assert trained.available() is False

    v3.write_bytes(b"v3")
    assert trained.available() is True


def test_trained_image_prediction_respects_checkpoint_thresholds(monkeypatch):
    from safety import littlenet_trained_image as trained

    fake_v2 = object()
    fake_v3 = object()
    v2_ckpt = {
        "labels": ["nudity", "sexy"],
        "thresholds": {"nudity": 0.89, "sexy": 0.82},
    }
    v3_ckpt = {
        "labels": ["weapons", "violence"],
        "thresholds": {"weapons": 0.59, "violence": 0.49},
    }

    monkeypatch.setattr(trained, "_models", lambda: (fake_v2, v2_ckpt, fake_v3, v3_ckpt))
    monkeypatch.setattr(trained, "_transform", lambda path: object())

    def fake_scores(model, checkpoint, tensor):
        if model is fake_v2:
            return {"nudity": 0.20, "sexy": 0.30}
        return {"weapons": 0.70, "violence": 0.20}

    monkeypatch.setattr(trained, "_scores", fake_scores)

    result = trained.predict("unused.jpg")

    assert result["trained_image_ensemble"] is True
    assert result["category"] == "WEAPON"
    assert result["weapon_score"] >= 0.80
    assert result["violence_score"] == 0.0
    assert result["adult_score"] < 0.40
    assert result["model_signals"]["littlenet_trained_image"]["triggered"] == {
        "nudity": False,
        "sexy": False,
        "weapons": True,
        "violence": False,
    }


def test_trained_image_nudity_maps_to_policy_hard_block(monkeypatch):
    from safety import littlenet_trained_image as trained
    from safety.policy import decide

    fake_v2 = object()
    fake_v3 = object()
    v2_ckpt = {
        "labels": ["nudity", "sexy"],
        "thresholds": {"nudity": 0.89, "sexy": 0.82},
    }
    v3_ckpt = {
        "labels": ["weapons", "violence"],
        "thresholds": {"weapons": 0.59, "violence": 0.49},
    }

    monkeypatch.setattr(trained, "_models", lambda: (fake_v2, v2_ckpt, fake_v3, v3_ckpt))
    monkeypatch.setattr(trained, "_transform", lambda path: object())

    def fake_scores(model, checkpoint, tensor):
        if model is fake_v2:
            return {"nudity": 0.95, "sexy": 0.40}
        return {"weapons": 0.10, "violence": 0.15}

    monkeypatch.setattr(trained, "_scores", fake_scores)

    result = trained.predict("unused.jpg")
    decision = decide(result, "STRICT", 0.40)

    assert result["category"] == "ADULT"
    assert decision.action == "BLOCK"


def test_visual_service_falls_back_when_private_checkpoints_are_missing(tmp_path, monkeypatch):
    from safety import visual_service
    from safety import littlenet_trained_image as trained

    monkeypatch.setenv("LITTLENET_AI_SERVER", "1")
    monkeypatch.setenv("LITTLENET_TRAINED_IMAGE_V2_PATH", str(tmp_path / "missing-v2.pth"))
    monkeypatch.setenv("LITTLENET_TRAINED_IMAGE_V3_PATH", str(tmp_path / "missing-v3.pth"))
    monkeypatch.setenv("LITTLENET_ENABLE_TRAINED_IMAGE_ENSEMBLE", "1")

    with patch.object(trained, "predict") as predict,          patch.object(visual_service, "_nudenet", return_value=0.01),          patch.object(visual_service, "_falconsai", return_value=0.02),          patch.object(visual_service, "_yolo_objects", return_value={"weapon": 0.0, "danger": 0.0, "detections": []}),          patch.object(visual_service, "_clip_score", return_value={"adult": 0.01, "sexual": 0.01, "violence": 0.01, "weapon": 0.01, "general": 0.01}):
        result = visual_service.check_image("unused.jpg")

    predict.assert_not_called()
    assert result["total_safety_failure"] is False
    assert result["adult_score"] < 0.40


def test_trained_image_checkpoint_thresholds_are_tighten_only():
    """A checkpoint may only tighten the policy-default thresholds, never
    loosen them: effective threshold = min(checkpoint_value, policy_default),
    still clamped to [0.01, 0.99]."""
    from safety import littlenet_trained_image as trained

    # Loosening attempt: checkpoint 0.95 is clamped down to the 0.89 default.
    assert trained._threshold({"thresholds": {"nudity": 0.95}}, "nudity", 0.89) == pytest.approx(0.89)
    # Tightening is honored.
    assert trained._threshold({"thresholds": {"nudity": 0.50}}, "nudity", 0.89) == pytest.approx(0.50)
    # Missing / malformed values fall back to the policy default.
    assert trained._threshold({}, "nudity", 0.89) == pytest.approx(0.89)
    assert trained._threshold({"thresholds": {"nudity": "high"}}, "nudity", 0.89) == pytest.approx(0.89)
    # The [0.01, 0.99] clamp is preserved on both ends.
    assert trained._threshold({"thresholds": {"nudity": 5.0}}, "nudity", 0.89) == pytest.approx(0.89)
    assert trained._threshold({"thresholds": {"nudity": 0.0}}, "nudity", 0.89) == pytest.approx(0.01)
