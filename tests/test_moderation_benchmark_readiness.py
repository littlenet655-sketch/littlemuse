"""Deterministic submission checks for the offline moderation benchmark."""

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

import evaluate_toxicity as benchmark  # noqa: E402


def test_evaluator_reports_fixed_action_metrics_without_model_loading():
    rows = [
        {"id": "a", "expected_action": "ALLOW", "predicted_action": "ALLOW"},
        {"id": "b", "expected_action": "ALLOW", "predicted_action": "REVIEW"},
        {"id": "c", "expected_action": "REVIEW", "predicted_action": "REVIEW"},
        {"id": "d", "expected_action": "BLOCK", "predicted_action": "BLOCK"},
        {"id": "e", "expected_action": "BLOCK", "predicted_action": "REVIEW"},
    ]

    result = benchmark.evaluate_rows(rows)

    assert result["scope"] == "offline_decision_benchmark"
    assert result["n"] == 5
    assert result["offline_exact_action_agreement"] == 0.6
    assert result["confusion_matrix"]["ALLOW"]["REVIEW"] == 1
    assert result["per_action"]["BLOCK"]["recall"] == 0.5
    assert result["macro_f1"] == 0.611111
    assert "live effectiveness" in result["interpretation"]


def test_evaluator_rejects_invalid_and_duplicate_prediction_rows():
    with pytest.raises(ValueError, match="one of ALLOW, REVIEW, BLOCK"):
        benchmark.evaluate_rows(
            [{"id": "bad", "expected_action": "TOXIC", "predicted_action": "BLOCK"}]
        )

    with pytest.raises(ValueError, match="duplicate"):
        benchmark.evaluate_rows(
            [
                {"id": "same", "expected_action": "ALLOW", "predicted_action": "ALLOW"},
                {"id": "same", "expected_action": "BLOCK", "predicted_action": "BLOCK"},
            ]
        )


def test_protocol_distinguishes_policy_metrics_and_external_validation():
    protocol = (
        ROOT / "docs" / "MODERATION_BENCHMARK_PROTOCOL.md"
    ).read_text(encoding="utf-8")
    evidence = (
        ROOT / "docs" / "MODERATION_BENCHMARK_EVIDENCE_TEMPLATE.md"
    ).read_text(encoding="utf-8")

    for phrase in (
        "Thresholds are policy, not accuracy",
        "Offline dataset metrics",
        "real-world effectiveness",
        "External validation is still required",
        "not an 18+ accuracy result",
        "NOT RUN",
    ):
        assert phrase in protocol
    assert "18+ accuracy claim:** `NONE" in evidence
    assert "config/safety_policy.yaml" in evidence


def test_legacy_evaluation_script_is_dependency_free_and_does_not_sample_rows():
    source = (ROOT / "evaluate_toxicity.py").read_text(encoding="utf-8")
    assert "transformers" not in source
    assert "pandas" not in source
    assert ".head(" not in source
    assert "prediction CSV" in source