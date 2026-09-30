"""Regression tests for media-worker moderation signal merging."""

import pytest

from safety.policy import decide
from services.media_processor import _merge_signals


def test_merge_preserves_visual_category_and_scores_for_model_specific_policy():
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
