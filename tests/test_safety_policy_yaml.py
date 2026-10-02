from pathlib import Path

from safety.policy import decide
from safety.policy_config import load_policy
from safety.yolo_policy import classify_detections


def test_yaml_policy_is_fail_closed_and_has_broad_object_vocabulary():
    policy = load_policy()
    assert policy["fail_closed"] is True
    assert policy["thresholds"]["adult_block"] == 0.40
    assert policy["thresholds"]["weapon_block"] == 0.45
    assert policy["object_label_count"] >= 80
    assert Path("config/safety_policy.yaml").is_file()


def test_configured_high_confidence_firearm_hard_blocks():
    result = classify_detections([{"label": "handgun", "confidence": 0.91}])
    assert result["block"] is True
    assert result["dangerous"][0]["family"] == "firearm"
    decision = decide({"category": "IMAGE", "model_signals": {"yolo": {"detections": [{"label": "handgun", "confidence": 0.91}]}}})
    assert decision.action == "BLOCK"


def test_review_only_family_never_escalates_to_detector_hard_block_by_confidence_alone():
    result = classify_detections([{"label": "power drill", "confidence": 0.99}])
    assert result["block"] is False
    assert result["review"] is True
    decision = decide({"category": "IMAGE", "model_signals": {"yolo": {"detections": [{"label": "power drill", "confidence": 0.99}]}}})
    assert decision.action == "REVIEW"


def test_ai_total_failure_remains_fail_closed():
    decision = decide({"total_safety_failure": True})
    assert decision.action == "BLOCK"
