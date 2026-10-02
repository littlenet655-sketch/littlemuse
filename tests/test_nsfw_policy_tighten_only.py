"""Tighten-only contract for safety/nsfw_policy.py.

The built-in NSFW thresholds are the child-safety baseline: deployment env
vars may only make blocking STRICTER (lower thresholds). Loosening values,
malformed values, and out-of-range values must raise SafetyConfigError at
import time (fail fast) -- never silently weaken the baseline.

Import-time behavior is tested in fresh subprocesses so a deliberately bad
config cannot poison the in-process module for other tests.
"""
import os
import subprocess
import sys

import pytest

from safety.nsfw_policy import classify_signals, thresholds

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EXPECTED_DEFAULTS = {
    'nudenet': (0.20, 0.45),
    'falconsai': (0.40, 0.70),
    'clip': (0.40, 0.65),
    'opennsfw2': (0.35, 0.70),
    'extra_nsfw': (0.40, 0.75),
}

PROBE = (
    "import safety.nsfw_policy as m; "
    "print({k: m.thresholds(k) for k in "
    "('nudenet','falconsai','clip','opennsfw2','extra_nsfw')})"
)


def _import_with_env(env):
    """Import safety.nsfw_policy in a fresh interpreter with the given env."""
    merged = dict(os.environ)
    for key in [k for k in merged if k.startswith('LITTLENET_') and 'THRESHOLD' in k]:
        del merged[key]
    merged.update(env)
    return subprocess.run(
        [sys.executable, '-c', PROBE],
        cwd=REPO_ROOT,
        env=merged,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_builtin_defaults_are_the_documented_baseline():
    for model, expected in EXPECTED_DEFAULTS.items():
        assert thresholds(model) == expected


def test_classify_signals_honors_defaults():
    assert classify_signals({'model_signals': {'nudenet': 0.30}})['review'] is True
    assert classify_signals({'model_signals': {'nudenet': 0.60}})['block'] is True


def test_tightening_block_threshold_is_accepted():
    proc = _import_with_env({'LITTLENET_NUDENET_BLOCK_THRESHOLD': '0.30'})
    assert proc.returncode == 0, proc.stderr
    assert "'nudenet': (0.2, 0.3)" in proc.stdout


def test_tightening_review_threshold_is_accepted():
    proc = _import_with_env({'LITTLENET_CLIP_REVIEW_THRESHOLD': '0.10'})
    assert proc.returncode == 0, proc.stderr
    assert "'clip': (0.1, 0.65)" in proc.stdout


def test_threshold_equal_to_default_is_accepted():
    proc = _import_with_env({'LITTLENET_NUDENET_BLOCK_THRESHOLD': '0.45'})
    assert proc.returncode == 0, proc.stderr


def test_blank_env_value_means_default():
    proc = _import_with_env({'LITTLENET_NUDENET_BLOCK_THRESHOLD': '   '})
    assert proc.returncode == 0, proc.stderr
    assert "'nudenet': (0.2, 0.45)" in proc.stdout


def test_loosening_block_threshold_fails_fast():
    # 1.0 would effectively disable NudeNet blocking: must fail fast.
    proc = _import_with_env({'LITTLENET_NUDENET_BLOCK_THRESHOLD': '1.0'})
    assert proc.returncode != 0
    assert 'SafetyConfigError' in proc.stderr
    assert 'tighten-only' in proc.stderr


def test_loosening_review_threshold_fails_fast():
    proc = _import_with_env({'LITTLENET_FALCONSAI_REVIEW_THRESHOLD': '0.90'})
    assert proc.returncode != 0
    assert 'SafetyConfigError' in proc.stderr


def test_slightly_loosened_threshold_fails_fast():
    proc = _import_with_env({'LITTLENET_CLIP_BLOCK_THRESHOLD': '0.66'})
    assert proc.returncode != 0
    assert 'SafetyConfigError' in proc.stderr


@pytest.mark.parametrize('bad', ['banana', 'nan', 'inf', '-inf'])
def test_malformed_threshold_fails_fast(bad):
    proc = _import_with_env({'LITTLENET_CLIP_BLOCK_THRESHOLD': bad})
    assert proc.returncode != 0
    assert 'SafetyConfigError' in proc.stderr


def test_out_of_range_threshold_fails_fast():
    proc = _import_with_env({'LITTLENET_NUDENET_BLOCK_THRESHOLD': '1.5'})
    assert proc.returncode != 0
    assert 'SafetyConfigError' in proc.stderr
    proc = _import_with_env({'LITTLENET_NUDENET_REVIEW_THRESHOLD': '-0.1'})
    assert proc.returncode != 0
    assert 'SafetyConfigError' in proc.stderr
