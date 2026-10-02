"""Server-side enforcement of the trained 18+/violence/weapons moderation.

Proves, without any UI involved:
- a flagged upload (image via the trained ensemble, text via the trained
  text model) is BLOCKED at the backend service layer;
- a clean upload passes (ALLOW);
- YOLO dangerous-object evidence and the OCR burned-in-text stage run on the
  trained-ensemble image path (defense in depth, not bypassed);
- the trained text artifact gate (env flag + staged directory) behaves.

Heavy ML is always mocked; what is exercised for real is the wiring:
trained model -> signals -> policy.decide -> moderation_service.evaluate.
"""
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flagged_image_predict(path):
    return {
        "adult_score": 0.95,
        "sexual_score": 0.95,
        "violence_score": 0.05,
        "weapon_score": 0.0,
        "toxicity_score": 0.0,
        "general_score": 0.95,
        "category": "ADULT",
        "total_safety_failure": False,
        "partial_safety_failure": False,
        "errors": [],
        "model_signals": {
            "littlenet_trained_image": {
                "raw_probabilities": {"nudity": 0.96, "sexy": 0.40, "weapons": 0.02, "violence": 0.05},
                "thresholds": {"nudity": 0.89, "sexy": 0.82, "weapons": 0.59, "violence": 0.49},
                "triggered": {"nudity": True, "sexy": False, "weapons": False, "violence": False},
                "source": {"v2": "v2.pth", "v3": "v3.pth"},
            }
        },
        "trained_image_ensemble": True,
    }


def _clean_image_predict(path):
    return {
        "adult_score": 0.02,
        "sexual_score": 0.02,
        "violence_score": 0.01,
        "weapon_score": 0.0,
        "toxicity_score": 0.0,
        "general_score": 0.02,
        "category": "IMAGE",
        "total_safety_failure": False,
        "partial_safety_failure": False,
        "errors": [],
        "model_signals": {
            "littlenet_trained_image": {
                "raw_probabilities": {"nudity": 0.02, "sexy": 0.01, "weapons": 0.03, "violence": 0.01},
                "thresholds": {"nudity": 0.89, "sexy": 0.82, "weapons": 0.59, "violence": 0.49},
                "triggered": {"nudity": False, "sexy": False, "weapons": False, "violence": False},
                "source": {"v2": "v2.pth", "v3": "v3.pth"},
            }
        },
        "trained_image_ensemble": True,
    }


@pytest.fixture
def local_ai_env(monkeypatch):
    """Force the local inference tier: no Modal CPU tier, no remote AI."""
    monkeypatch.setenv("LITTLENET_AI_SERVER", "1")
    monkeypatch.delenv("AI_SERVICE_URL", raising=False)
    # OCR is on by default; keep it off in this file so the deterministic
    # ALLOW/REVIEW assertions below don't trip on ocr_unavailable.
    monkeypatch.setenv("LITTLENET_ENABLE_OCR", "0")
    monkeypatch.delenv("LITTLENET_ENABLE_TEXT_CLASSIFIER", raising=False)
    return monkeypatch


@pytest.fixture
def trained_image_on(monkeypatch):
    from safety import littlenet_trained_image as trained

    monkeypatch.setattr(trained, "available", lambda: True)
    return trained


# ---------------------------------------------------------------------------
# Trained image ensemble: flagged upload blocked server-side
# ---------------------------------------------------------------------------

def test_flagged_image_blocked_on_trained_path(local_ai_env, trained_image_on, monkeypatch):
    from safety import visual_service
    from safety.moderation_service import evaluate
    from safety import moderation_service

    monkeypatch.setattr(trained_image_on, "predict", _flagged_image_predict)
    monkeypatch.setattr(
        visual_service, "_yolo_objects",
        lambda path: {"weapon": 0.0, "danger": 0.0, "detections": []},
    )
    monkeypatch.setattr(moderation_service, "safety_level", lambda child_id: "STRICT")

    signals, decision = evaluate(123, "IMAGE", "unused.jpg")

    assert decision.action == "BLOCK"
    assert "18+" in decision.reason


def test_clean_image_passes_on_trained_path(local_ai_env, trained_image_on, monkeypatch):
    from safety import visual_service
    from safety.moderation_service import evaluate
    from safety import moderation_service

    monkeypatch.setattr(trained_image_on, "predict", _clean_image_predict)
    monkeypatch.setattr(
        visual_service, "_yolo_objects",
        lambda path: {"weapon": 0.0, "danger": 0.0, "detections": []},
    )
    # Heavy ML is always mocked in this file: the legacy stack runs
    # unconditionally on the trained path now, so mock it clean too --
    # otherwise the real detectors error on the fixture path and the item
    # fail-closes to REVIEW, which is not what this test exercises.
    monkeypatch.setattr(
        visual_service, "_legacy_image_scores",
        lambda path, **kw: {
            "adult": 0.0, "sexual": 0.0, "violence": 0.0, "weapon": 0.0,
            "general": 0.0, "ran": 4, "errors": [], "details": {},
        },
    )
    monkeypatch.setattr(moderation_service, "safety_level", lambda child_id: "STRICT")

    signals, decision = evaluate(123, "IMAGE", "unused.jpg")

    assert decision.action == "ALLOW"
    assert signals["total_safety_failure"] is False


def test_yolo_weapon_evidence_merges_on_trained_path(local_ai_env, trained_image_on, monkeypatch):
    """YOLO is not bypassed when the trained ensemble runs: a YOLO gun
    detection on an otherwise-clean trained result still blocks."""
    from safety import visual_service
    from safety.policy import decide

    monkeypatch.setattr(trained_image_on, "predict", _clean_image_predict)
    monkeypatch.setattr(
        visual_service, "_yolo_objects",
        lambda path: {
            "weapon": 0.93,
            "danger": 0.0,
            "detections": [{"label": "gun", "confidence": 0.93}],
        },
    )

    signals = visual_service.check_image("unused.jpg")

    assert signals["weapon_score"] == pytest.approx(0.93)
    assert signals["model_signals"]["yolo"]["detections"][0]["label"] == "gun"
    assert decide(signals, "STRICT").action == "BLOCK"


def test_yolo_failure_on_trained_path_is_review_not_bypass(local_ai_env, trained_image_on, monkeypatch):
    """If YOLO fails on the trained path the item goes to parent review,
    never to a silent allow."""
    from safety import visual_service
    from safety.policy import decide

    monkeypatch.setattr(trained_image_on, "predict", _clean_image_predict)

    def _boom(path):
        raise RuntimeError("yolo_weights_missing")

    monkeypatch.setattr(visual_service, "_yolo_objects", _boom)

    signals = visual_service.check_image("unused.jpg")

    assert signals["partial_safety_failure"] is True
    assert "yolo" in signals["errors"]
    assert decide(signals, "STRICT").action == "REVIEW"


def test_ocr_stage_runs_on_trained_path(local_ai_env, trained_image_on, monkeypatch):
    """Burned-in text screening is not skipped when the trained ensemble runs."""
    from safety import visual_service
    from safety.policy import decide

    monkeypatch.setenv("LITTLENET_ENABLE_OCR", "1")
    monkeypatch.setattr(trained_image_on, "predict", _clean_image_predict)
    monkeypatch.setattr(
        visual_service, "_yolo_objects",
        lambda path: {"weapon": 0.0, "danger": 0.0, "detections": []},
    )
    monkeypatch.setattr(visual_service, "_ocr_extract_text", lambda path: ("some text", None))

    def _fake_apply(result, ocr_text):
        result["deterministic_ocr_pii"] = True
        result["errors"] = list(result.get("errors") or []) + ["ocr_pii_block"]

    monkeypatch.setattr(visual_service, "_apply_ocr_evidence", _fake_apply)

    signals = visual_service.check_image("unused.jpg")

    assert signals.get("deterministic_ocr_pii") is True
    assert decide(signals, "STRICT").action == "BLOCK"


def test_nsfw_policy_recognises_trained_ensemble():
    from safety.nsfw_policy import classify_signals

    idle = {"model_signals": {"littlenet_trained_image": {"triggered": {
        "nudity": False, "sexy": False, "weapons": False, "violence": False}}}}
    out = classify_signals(idle)
    assert out["has_evidence"] is False

    fired = {"model_signals": {"littlenet_trained_image": {"triggered": {
        "nudity": True, "sexy": False, "weapons": False, "violence": False}}}}
    out = classify_signals(fired)
    assert out["has_evidence"] is True
    assert out["block"] is True
    assert out["top"]["model"] == "trained_image"


# ---------------------------------------------------------------------------
# Trained 18+ text model: flagged text blocked, clean text passes
# ---------------------------------------------------------------------------

def _mock_trained_text(monkeypatch, rows):
    from safety import littlenet_trained_text as trained_text

    monkeypatch.setattr(trained_text, "available", lambda: True)
    monkeypatch.setattr(trained_text, "_pipeline", lambda: (lambda snippet: rows))
    return trained_text


def test_flagged_text_blocked_via_trained_text_model(local_ai_env, monkeypatch):
    from safety import text_service
    from safety.moderation_service import evaluate
    from safety import moderation_service

    _mock_trained_text(monkeypatch, [{"label": "sexual_explicit", "score": 0.97}])
    # Detoxify stays clean so the block must come from the trained model.
    monkeypatch.setattr(text_service, "_detox_scores", lambda text: {"sexual_explicit": 0.01, "toxicity": 0.01})
    monkeypatch.setattr(moderation_service, "safety_level", lambda child_id: "STRICT")

    signals, decision = evaluate(123, "TEXT", " innocuous-looking message ".strip())

    assert float(signals["sexual_score"]) >= 0.90
    assert decision.action == "BLOCK"


def test_clean_text_passes_with_trained_text_model(local_ai_env, monkeypatch):
    from safety import text_service
    from safety.moderation_service import evaluate
    from safety import moderation_service

    _mock_trained_text(monkeypatch, [{"label": "safe", "score": 0.99}])
    monkeypatch.setattr(text_service, "_detox_scores", lambda text: {"sexual_explicit": 0.01, "toxicity": 0.01})
    monkeypatch.setattr(moderation_service, "safety_level", lambda child_id: "STRICT")

    signals, decision = evaluate(123, "TEXT", "what is your favorite cartoon?")

    assert decision.action == "ALLOW"


def test_trained_text_absent_falls_back_without_bypass(local_ai_env, monkeypatch):
    """No staged text artifact: deterministic rules still hard-block, and a
    clean text with all ML unavailable fails closed, never silently allowed."""
    from safety import text_service
    from safety import littlenet_trained_text as trained_text

    monkeypatch.setattr(trained_text, "available", lambda: False)

    def _detox_boom(text):
        raise RuntimeError("detoxify")

    monkeypatch.setattr(text_service, "_detox_scores", _detox_boom)

    flagged = text_service.check_text("send me a nude pic")
    assert float(flagged["sexual_score"]) == 1.0  # deterministic rule fires

    clean = text_service.check_text("what is your favorite cartoon?")
    assert clean["total_safety_failure"] is True  # fail closed, never silent ALLOW


def test_trained_text_artifact_gate(tmp_path, monkeypatch):
    from safety import littlenet_trained_text as trained_text

    target = tmp_path / "littlenet_text_safety"
    monkeypatch.setenv("LITTLENET_TRAINED_TEXT_PATH", str(target))
    monkeypatch.setenv("LITTLENET_ENABLE_TRAINED_TEXT", "1")
    trained_text.reset_for_tests()

    assert trained_text.available() is False  # nothing staged

    target.mkdir()
    assert trained_text.available() is False  # dir without config.json

    (target / "config.json").write_text("{}")
    assert trained_text.available() is True

    monkeypatch.setenv("LITTLENET_ENABLE_TRAINED_TEXT", "0")
    assert trained_text.available() is False


def test_trained_text_label_bucketing(monkeypatch):
    from safety import littlenet_trained_text as trained_text

    trained_text.reset_for_tests()
    monkeypatch.setattr(
        trained_text, "_pipeline",
        lambda: (lambda snippet: [
            {"label": "sexual_explicit", "score": 0.92},
            {"label": "toxic", "score": 0.10},
        ]),
    )

    out = trained_text.predict("some text")

    assert out["sexual_score"] == pytest.approx(0.92)
    assert out["adult_score"] == pytest.approx(0.92)
    assert out["category"] == "SEXUAL_LANGUAGE"
    assert out["trained_text_model"] is True
    assert out["model_signals"]["littlenet_trained_text"]["labels"]["sexual_explicit"] == pytest.approx(0.92)


# ---------------------------------------------------------------------------
# Sub-threshold band regression (FIX 11): trained nudity=0.88 (below the 0.89
# trained threshold, above the 0.40 legacy block line) must still BLOCK via
# merged legacy evidence, through the real check_image -> evaluate -> decide
# wiring. Only model inference is mocked, as the existing tests do.
# ---------------------------------------------------------------------------

def _band_image_predict(path):
    """Trained ensemble output for nudity=0.88: sub-threshold, so predict()
    caps the 18+ scores below the 0.40 policy block line."""
    return {
        "adult_score": 0.386,
        "sexual_score": 0.386,
        "violence_score": 0.0,
        "weapon_score": 0.0,
        "toxicity_score": 0.0,
        "general_score": 0.386,
        "category": "IMAGE",
        "total_safety_failure": False,
        "partial_safety_failure": False,
        "errors": [],
        "model_signals": {
            "littlenet_trained_image": {
                "raw_probabilities": {"nudity": 0.88, "sexy": 0.10, "weapons": 0.02, "violence": 0.01},
                "thresholds": {"nudity": 0.89, "sexy": 0.82, "weapons": 0.59, "violence": 0.49},
                "triggered": {"nudity": False, "sexy": False, "weapons": False, "violence": False},
                "source": {"v2": "v2.pth", "v3": "v3.pth"},
            }
        },
        "trained_image_ensemble": True,
    }


def test_subthreshold_band_blocks_via_legacy_merge(local_ai_env, trained_image_on, monkeypatch):
    from safety import visual_service
    from safety.moderation_service import evaluate
    from safety import moderation_service

    monkeypatch.setattr(trained_image_on, "predict", _band_image_predict)
    # Legacy NudeNet sees the same 0.88 evidence the trained model scored.
    monkeypatch.setattr(visual_service, "_nudenet", lambda path: 0.88)
    monkeypatch.setattr(visual_service, "_falconsai", lambda path: 0.0)
    monkeypatch.setattr(visual_service, "_clip_score", lambda path: None)
    monkeypatch.setattr(
        visual_service, "_yolo_objects",
        lambda path: {"weapon": 0.0, "danger": 0.0, "detections": []},
    )
    monkeypatch.setattr(moderation_service, "safety_level", lambda child_id: "STRICT")

    signals, decision = evaluate(123, "IMAGE", "unused.jpg")

    assert signals["adult_score"] == pytest.approx(0.88)
    assert signals["category"] == "ADULT"
    assert decision.action == "BLOCK"


def test_subthreshold_band_legacy_failure_cannot_downgrade(local_ai_env, trained_image_on, monkeypatch):
    """Fail-closed: if every legacy detector throws while the trained result
    sits in the sub-threshold band, the item goes to REVIEW (partial safety
    evidence) -- never to a silent ALLOW, and a trained BLOCK is never
    downgraded."""
    from safety import visual_service
    from safety.policy import decide

    monkeypatch.setattr(trained_image_on, "predict", _band_image_predict)

    def _boom(path):
        raise RuntimeError("legacy detector unavailable")

    monkeypatch.setattr(visual_service, "_nudenet", _boom)
    monkeypatch.setattr(visual_service, "_falconsai", _boom)
    monkeypatch.setattr(visual_service, "_clip_score", lambda path: None)
    monkeypatch.setattr(
        visual_service, "_yolo_objects",
        lambda path: {"weapon": 0.0, "danger": 0.0, "detections": []},
    )

    signals = visual_service.check_image("unused.jpg")

    assert signals["partial_safety_failure"] is True
    assert "nudenet" in signals["errors"]
    assert decide(signals, "STRICT").action == "REVIEW"

    # And a trained BLOCK stays a BLOCK even when legacy detectors explode.
    monkeypatch.setattr(trained_image_on, "predict", _flagged_image_predict)
    signals = visual_service.check_image("unused.jpg")
    assert decide(signals, "STRICT").action == "BLOCK"


def test_unmapped_trained_text_labels_fail_closed_to_review(local_ai_env, monkeypatch):
    """A classifier output no bucket can interpret ([{"label": "UNSAFE",
    "score": 0.99}]) must record partial_safety_failure and REVIEW -- never a
    silent ALLOW. Only model inference is mocked, as the existing tests do."""
    from safety import text_service
    from safety.moderation_service import evaluate
    from safety import moderation_service

    _mock_trained_text(monkeypatch, [{"label": "UNSAFE", "score": 0.99}])
    monkeypatch.setattr(text_service, "_detox_scores", lambda text: {"sexual_explicit": 0.01, "toxicity": 0.01})
    monkeypatch.setattr(moderation_service, "safety_level", lambda child_id: "STRICT")

    signals, decision = evaluate(123, "TEXT", "what is your favorite cartoon?")

    assert signals["partial_safety_failure"] is True
    assert "trained_text_unmapped_labels" in signals["errors"]
    assert decision.action == "REVIEW"


def test_benign_safe_label_still_allows(local_ai_env, monkeypatch):
    """The conventional benign classifier output (exactly "safe") keeps its
    established contract: no failure recorded, clean text ALLOWs."""
    from safety import littlenet_trained_text as trained_text

    _mock_trained_text(monkeypatch, [{"label": "safe", "score": 0.99}])

    out = trained_text.predict("what is your favorite cartoon?")

    assert out["partial_safety_failure"] is False
    assert out["errors"] == []
    assert out["sexual_score"] == pytest.approx(0.0)


def _low_trained_image_predict(path):
    """Trained ensemble scores the image well below every legacy block line
    (nudity raw 0.10) -- the legacy stack must still get its say."""
    return {
        "adult_score": 0.10,
        "sexual_score": 0.10,
        "violence_score": 0.0,
        "weapon_score": 0.0,
        "toxicity_score": 0.0,
        "general_score": 0.10,
        "category": "IMAGE",
        "total_safety_failure": False,
        "partial_safety_failure": False,
        "errors": [],
        "model_signals": {
            "littlenet_trained_image": {
                "raw_probabilities": {"nudity": 0.10, "sexy": 0.05, "weapons": 0.02, "violence": 0.01},
                "thresholds": {"nudity": 0.89, "sexy": 0.82, "weapons": 0.59, "violence": 0.49},
                "triggered": {"nudity": False, "sexy": False, "weapons": False, "violence": False},
                "source": {"v2": "v2.pth", "v3": "v3.pth"},
            }
        },
        "trained_image_ensemble": True,
    }


def test_legacy_merge_blocks_when_trained_scores_low(local_ai_env, trained_image_on, monkeypatch):
    """Unconditional max-merge: even when the trained ensemble scores an
    image far below its own thresholds, legacy evidence at block level must
    still BLOCK. This closes the residual hole where a low trained score
    would otherwise skip the legacy stack entirely."""
    from safety import visual_service
    from safety.moderation_service import evaluate
    from safety import moderation_service

    monkeypatch.setattr(trained_image_on, "predict", _low_trained_image_predict)
    # Legacy NudeNet fires on the same image the ensemble scored 0.10.
    monkeypatch.setattr(visual_service, "_nudenet", lambda path: 0.88)
    monkeypatch.setattr(visual_service, "_falconsai", lambda path: 0.0)
    monkeypatch.setattr(visual_service, "_clip_score", lambda path: None)
    monkeypatch.setattr(
        visual_service, "_yolo_objects",
        lambda path: {"weapon": 0.0, "danger": 0.0, "detections": []},
    )
    monkeypatch.setattr(moderation_service, "safety_level", lambda child_id: "STRICT")

    signals, decision = evaluate(123, "IMAGE", "unused.jpg")

    assert signals["adult_score"] == pytest.approx(0.88)
    assert signals["category"] == "ADULT"
    assert decision.action == "BLOCK"
