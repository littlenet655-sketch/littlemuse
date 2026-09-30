"""Regression tests for media-worker moderation signal merging."""

import pytest


def test_merge_preserves_visual_category_and_scores_for_model_specific_policy():
    from safety.policy import decide
    from services.media_processor import _merge_signals

    media = {
        "category": "ADULT",
        "adult_score": 0.645,
        "sexual_score": 0.645,
        "violence_score": 0.078,
        "weapon_score": 0.002,
        "toxicity_score": 0.03,
        "general_score": 0.645,
        "total_safety_failure": False,
        "partial_safety_failure": False,
        "model_signals": {
            "legacy": {
                "clip": {
                    "adult": 0.645,
                    "sexual": 0.645,
                    "violence": 0.078,
                    "weapon": 0.002,
                    "general": 0.645,
                },
                "nudenet": 0.0,
                "falconsai": 0.0,
            },
            "littlenet_trained_image": {
                "triggered": {
                    "nudity": False,
                    "sexy": False,
                    "weapons": False,
                    "violence": False,
                }
            },
        },
    }

    merged = _merge_signals({}, media)

    assert merged["category"] == "ADULT"
    assert merged["sexual_score"] == pytest.approx(0.645)
    assert merged["general_score"] == pytest.approx(0.645)

    # CLIP 0.645 is above its REVIEW line (0.40) but below its BLOCK line
    # (0.65). Preserving visual provenance must therefore avoid the generic
    # adult >= 0.40 hard block.
    decision = decide(merged, "STRICT")
    assert decision.action == "REVIEW"
    assert "parent review" in decision.reason.lower()


def test_merge_keeps_trained_image_hard_block_behavior():
    from safety.policy import decide
    from services.media_processor import _merge_signals

    media = {
        "category": "ADULT",
        "adult_score": 0.95,
        "sexual_score": 0.95,
        "violence_score": 0.01,
        "weapon_score": 0.0,
        "toxicity_score": 0.0,
        "general_score": 0.95,
        "total_safety_failure": False,
        "partial_safety_failure": False,
        "model_signals": {
            "littlenet_trained_image": {
                "triggered": {
                    "nudity": True,
                    "sexy": False,
                    "weapons": False,
                    "violence": False,
                }
            }
        },
    }

    decision = decide(_merge_signals({}, media), "STRICT")
    assert decision.action == "BLOCK"

def test_merge_preserves_deterministic_ocr_pii_even_when_visual_category_wins():
    from safety.policy import decide
    from services.media_processor import _merge_signals

    text = {
        "category": "TEXT",
        "adult_score": 0.0,
        "sexual_score": 0.0,
        "violence_score": 0.0,
        "toxicity_score": 0.0,
        "general_score": 0.0,
        "deterministic_ocr_pii": True,
    }
    media = {
        "category": "IMAGE",
        "adult_score": 0.0,
        "sexual_score": 0.0,
        "violence_score": 0.0,
        "weapon_score": 0.0,
        "toxicity_score": 0.0,
        "general_score": 0.0,
    }

    merged = _merge_signals(text, media)

    assert merged["category"] == "IMAGE"
    assert merged["text_category"] == "TEXT"
    assert merged["media_category"] == "IMAGE"
    assert merged["deterministic_ocr_pii"] is True
    decision = decide(merged, "STRICT")
    assert decision.action == "BLOCK"
    assert "pii" in decision.reason.lower()


def test_merge_preserves_true_deterministic_text_abuse_flags():
    from safety.policy import decide
    from services.media_processor import _merge_signals

    text = {
        "category": "SEVERE_ABUSE",
        "violence_score": 1.0,
        "toxicity_score": 1.0,
        "general_score": 1.0,
        "deterministic_severe_abuse": True,
    }
    media = {
        "category": "IMAGE",
        "adult_score": 0.0,
        "sexual_score": 0.0,
        "violence_score": 0.0,
        "weapon_score": 0.0,
        "toxicity_score": 0.0,
        "general_score": 0.0,
    }

    merged = _merge_signals(text, media)

    # Visual category stays available for visual-model policy, while the
    # deterministic text flag remains authoritative for hard safety rules.
    assert merged["category"] == "IMAGE"
    assert merged["deterministic_severe_abuse"] is True
    assert decide(merged, "STRICT").action == "BLOCK"

def test_explicit_text_still_hard_blocks_when_visual_evidence_is_benign():
    from safety.policy import decide
    from services.media_processor import _merge_signals

    text = {
        "category": "SEXUAL_LANGUAGE",
        "adult_score": 0.50,
        "sexual_score": 0.50,
        "violence_score": 0.0,
        "toxicity_score": 0.0,
        "general_score": 0.50,
    }
    media = {
        "category": "IMAGE",
        "adult_score": 0.10,
        "sexual_score": 0.10,
        "violence_score": 0.0,
        "weapon_score": 0.0,
        "toxicity_score": 0.0,
        "general_score": 0.10,
        "model_signals": {
            "legacy": {
                "clip": {
                    "adult": 0.10,
                    "sexual": 0.10,
                    "violence": 0.0,
                    "weapon": 0.0,
                    "general": 0.10,
                }
            }
        },
    }

    merged = _merge_signals(text, media)

    assert merged["category"] == "IMAGE"
    assert merged["text_category"] == "SEXUAL_LANGUAGE"
    assert merged["text_adult_score"] == pytest.approx(0.50)
    assert merged["media_adult_score"] == pytest.approx(0.10)
    decision = decide(merged, "STRICT")
    assert decision.action == "BLOCK"
    assert "text" in decision.reason.lower()

