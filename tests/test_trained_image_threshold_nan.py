"""Regression tests: NaN / non-finite checkpoint thresholds must not loosen policy.

Adversarial finding: ``_threshold`` in safety/littlenet_trained_image.py did
``min(NaN, 0.89)`` -> NaN, and the outer ``min(0.99, NaN)`` then yielded
0.99 -- silently loosening the policy threshold to its weakest value
(tighten-only defeated). Non-finite or non-numeric checkpoint values must
fall back to the policy default instead.

These tests import only the pure ``_threshold`` helper; no torch, no
checkpoint files, no Postgres required.
"""
import math

import pytest

from safety import littlenet_trained_image as trained


def _ckpt(value):
    return {"thresholds": {"nudity": value}}


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_threshold_falls_back_to_policy_default(bad):
    assert trained._threshold(_ckpt(bad), "nudity", 0.89) == 0.89


@pytest.mark.parametrize("bad", [None, "0.5", "nan", object(), [0.5], {"v": 0.5}])
def test_non_numeric_threshold_falls_back_to_policy_default(bad):
    assert trained._threshold(_ckpt(bad), "nudity", 0.89) == 0.89


def test_nan_never_loosens_to_099():
    # The exact adversarial case: NaN must not become the 0.99 clamp ceiling.
    result = trained._threshold(_ckpt(float("nan")), "nudity", 0.89)
    assert result != 0.99
    assert result == 0.89


def test_missing_label_uses_fallback():
    assert trained._threshold({"thresholds": {}}, "nudity", 0.89) == 0.89
    assert trained._threshold({}, "nudity", 0.89) == 0.89


def test_tightening_threshold_still_accepted():
    assert trained._threshold(_ckpt(0.5), "nudity", 0.89) == 0.5


def test_loosening_threshold_still_capped_at_fallback():
    assert trained._threshold(_ckpt(0.95), "nudity", 0.89) == 0.89


def test_result_is_always_finite():
    for bad in [float("nan"), float("inf"), float("-inf"), None, "x"]:
        assert math.isfinite(trained._threshold(_ckpt(bad), "nudity", 0.89))
