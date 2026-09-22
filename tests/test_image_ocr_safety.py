"""OCR screening for burned-in text in images (safety/visual_service.py).

Covers: OCR text routed through the shared check_text + PII policy, PII
contact in burned-in text hard-blocking via policy.decide, deterministic text
flags propagating, visual evidence never weakened, OCR failures degrading to
partial safety evidence (REVIEW at most), the stage being a no-op when the
flag is off, and graceful degradation when no OCR backend is installed.

A synthetic PIL fixture stands in for a real OCR engine (no OCR dependency is
installed in this environment); extraction itself is monkeypatched while the
policy routing under test is real.
"""
import os

import pytest
from PIL import Image, ImageDraw

from safety import visual_service
from safety.policy import decide
from safety.visual_service import (
    _OCRUnavailable,
    _apply_ocr_evidence,
    _downscale_for_ocr,
    _load_ocr_backend,
    _ocr_extract_text,
    check_image,
)

PHONE_TEXT = "Call me now on 98765 43210"
GROOMING_TEXT = "dont tell your parents keep it secret"
BENIGN_TEXT = "sunny day at the park"


def _make_text_image(path, text=PHONE_TEXT):
    img = Image.new("RGB", (480, 160), "white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 60), text, fill="black")
    img.save(path)
    return path


def _neutral_models(monkeypatch):
    """Make the heavy visual models no-ops so check_image is fast/deterministic."""
    monkeypatch.setattr(visual_service, "_nudenet", lambda p: 0.0)
    monkeypatch.setattr(visual_service, "_falconsai", lambda p: 0.0)
    monkeypatch.setattr(
        visual_service, "_yolo_objects",
        lambda p: {"weapon": 0.0, "danger": 0.0, "detections": []},
    )
    monkeypatch.setattr(visual_service, "_clip_score", lambda p: None)


def _base_result(**overrides):
    result = {
        "adult_score": 0.0, "sexual_score": 0.0, "violence_score": 0.0,
        "weapon_score": 0.0, "toxicity_score": 0.0, "general_score": 0.0,
        "category": "IMAGE", "total_safety_failure": False,
        "partial_safety_failure": False, "errors": [],
    }
    result.update(overrides)
    return result


# --- policy routing -------------------------------------------------------

def test_burned_in_phone_number_routes_through_pii_block():
    result = _apply_ocr_evidence(_base_result(), PHONE_TEXT)
    assert result["deterministic_ocr_pii"] is True
    assert "ocr_pii_block" in result["errors"]
    assert any(e.startswith("ocr_pii_detected:") for e in result["errors"])
    # Only the redacted form is kept in evidence, never raw PII.
    assert "98765" not in result["ocr_redacted_text"]
    decision = decide(result)
    assert decision.action == "BLOCK"
    assert "OCR" in decision.reason


def test_burned_in_grooming_text_propagates_deterministic_flag():
    result = _apply_ocr_evidence(_base_result(), GROOMING_TEXT)
    assert result["deterministic_grooming"] is True
    assert decide(result).action == "BLOCK"


def test_benign_ocr_text_never_weakens_visual_evidence():
    result = _apply_ocr_evidence(_base_result(adult_score=0.9), BENIGN_TEXT)
    assert result["adult_score"] == 0.9
    assert "ocr_text_present" in result["errors"]
    assert result.get("deterministic_ocr_pii") is not True


def test_unmoderated_ocr_text_is_partial_evidence_only(monkeypatch):
    # Text models unavailable + no deterministic hits: REVIEW at most, and it
    # must not escalate the image to a total safety failure by itself.
    # Force the trained text model off so this tests the unmoderated path
    # even when the artifact is staged in the repo.
    monkeypatch.setenv("LITTLENET_ENABLE_TRAINED_TEXT", "0")
    result = _apply_ocr_evidence(_base_result(), BENIGN_TEXT)
    assert result["total_safety_failure"] is False
    assert result["partial_safety_failure"] is True
    assert "ocr_text_unmoderated" in result["errors"]
    assert decide(result).action == "REVIEW"


def test_empty_ocr_text_is_ignored():
    result = _apply_ocr_evidence(_base_result(), "   ")
    assert result["errors"] == []
    assert result["partial_safety_failure"] is False


# --- check_image integration ----------------------------------------------

def test_check_image_ocr_pii_blocks_end_to_end(tmp_path, monkeypatch):
    _neutral_models(monkeypatch)
    monkeypatch.setattr(
        visual_service, "_ocr_extract_text", lambda p: (PHONE_TEXT, None)
    )
    path = _make_text_image(str(tmp_path / "contact.png"))
    signals = check_image(path, ocr=True)
    assert signals["deterministic_ocr_pii"] is True
    assert decide(signals).action == "BLOCK"


def test_check_image_ocr_failure_degrades_to_review_at_most(tmp_path, monkeypatch):
    _neutral_models(monkeypatch)
    monkeypatch.setattr(
        visual_service, "_ocr_extract_text", lambda p: (None, "ocr_failed")
    )
    path = _make_text_image(str(tmp_path / "plain.png"), BENIGN_TEXT)
    signals = check_image(path, ocr=True)
    assert "ocr_failed" in signals["errors"]
    assert signals["total_safety_failure"] is False
    assert signals["partial_safety_failure"] is True
    # REVIEW at most: an OCR failure must never manufacture a BLOCK ...
    assert decide(signals).action == "REVIEW"
    # ... and never an ALLOW either.
    assert decide(signals).action != "ALLOW"


def test_check_image_skips_ocr_when_flag_off(tmp_path, monkeypatch):
    _neutral_models(monkeypatch)
    monkeypatch.delenv("LITTLENET_ENABLE_OCR", raising=False)

    def _must_not_run(_path):
        raise AssertionError("OCR stage must not run when the flag is off")

    monkeypatch.setattr(visual_service, "_ocr_extract_text", _must_not_run)
    path = _make_text_image(str(tmp_path / "plain.png"), BENIGN_TEXT)
    signals = check_image(path)
    assert "deterministic_ocr_pii" not in signals
    assert not any(str(e).startswith("ocr_") for e in signals["errors"])


def test_check_image_explicit_ocr_false_overrides_env(tmp_path, monkeypatch):
    _neutral_models(monkeypatch)
    monkeypatch.setenv("LITTLENET_ENABLE_OCR", "1")

    def _must_not_run(_path):
        raise AssertionError("OCR stage must not run when ocr=False")

    monkeypatch.setattr(visual_service, "_ocr_extract_text", _must_not_run)
    path = _make_text_image(str(tmp_path / "plain.png"), BENIGN_TEXT)
    signals = check_image(path, ocr=False)
    assert not any(str(e).startswith("ocr_") for e in signals["errors"])


# --- graceful degradation ---------------------------------------------------

def test_no_ocr_backend_installed_degrades_gracefully(monkeypatch, capsys):
    monkeypatch.setattr(visual_service, "_OCR_BACKEND_MISSING", False, raising=False)
    monkeypatch.setattr(visual_service, "_OCR_READER", None, raising=False)
    monkeypatch.setattr(visual_service, "_OCR_UNAVAILABLE_LOGGED", False, raising=False)
    with pytest.raises(_OCRUnavailable):
        _load_ocr_backend()
    text, error = _ocr_extract_text("/nonexistent.png")
    assert text is None
    assert error == "ocr_unavailable"
    # The missing-backend warning is logged exactly once.
    _ocr_extract_text("/nonexistent.png")
    out = capsys.readouterr().out
    assert out.count("no OCR backend is installed") == 1


def test_check_image_records_ocr_unavailable_as_partial_evidence(
    tmp_path, monkeypatch
):
    _neutral_models(monkeypatch)
    monkeypatch.setattr(visual_service, "_OCR_BACKEND_MISSING", False, raising=False)
    monkeypatch.setattr(visual_service, "_OCR_READER", None, raising=False)
    monkeypatch.setattr(visual_service, "_OCR_UNAVAILABLE_LOGGED", True, raising=False)
    path = _make_text_image(str(tmp_path / "plain.png"), BENIGN_TEXT)
    signals = check_image(path, ocr=True)
    assert "ocr_unavailable" in signals["errors"]
    # Enabled-but-broken OCR is partial safety evidence (fail closed).
    assert signals["partial_safety_failure"] is True
    assert signals["total_safety_failure"] is False


# --- bounded processing -----------------------------------------------------

def test_ocr_input_is_downscaled(tmp_path):
    big = Image.new("RGB", (3000, 2000), "white")
    src = str(tmp_path / "big.png")
    big.save(src)
    tmp = _downscale_for_ocr(src)
    try:
        with Image.open(tmp) as img:
            assert max(img.size) <= 1024
    finally:
        os.unlink(tmp)
