"""Per-model NSFW policy for LittleNet image/video moderation.

Raw scores from NudeNet, FalconsAI and CLIP are not directly comparable. This
module keeps model-specific review/block thresholds and converts their evidence
into a consistent child-safety action. Raw scores remain available in
``model_signals`` for later benchmark calibration.

TIGHTEN-ONLY DEPLOYMENT CONTRACT
--------------------------------
The built-in defaults below are the child-safety baseline. Deployment may only
make blocking STRICTER through environment variables (lower review/block
thresholds). Any of the following is a hard configuration error and raises
``SafetyConfigError`` at import time (fail fast, fail closed):

* an env value HIGHER than the built-in default (would loosen blocking),
* an env value that is not a finite number (malformed/ambiguous config),
* an env value outside [0, 1].

There is no silent fallback to the default and no clamping of a loosening
value: silently weakening the baseline is never acceptable. Set

    LITTLENET_<MODEL>_REVIEW_THRESHOLD / LITTLENET_<MODEL>_BLOCK_THRESHOLD

to a value *at or below* the default to tighten, or leave them unset.

This mirrors the tighten-only pattern in ``safety/yolo_policy.py``.
"""
from __future__ import annotations

import math
import os


class SafetyConfigError(RuntimeError):
    """Raised when safety configuration would weaken the built-in baseline."""


def _tighten_only_env(name: str, default: float) -> float:
    """Read a threshold env var that may only tighten the default.

    Returns the default when the variable is unset/blank. Raises
    ``SafetyConfigError`` when the value is malformed, non-finite, outside
    [0, 1], or higher than ``default`` (i.e. it would loosen blocking).
    """
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise SafetyConfigError(
            f"{name}={raw!r} is not a valid number; refusing to run with "
            f"ambiguous NSFW safety configuration"
        )
    if not math.isfinite(value):
        raise SafetyConfigError(
            f"{name}={raw!r} is not finite; refusing to run with ambiguous "
            f"NSFW safety configuration"
        )
    if value < 0.0 or value > 1.0:
        raise SafetyConfigError(
            f"{name}={value} is outside [0, 1]; refusing to run with invalid "
            f"NSFW safety configuration"
        )
    if value > default:
        raise SafetyConfigError(
            f"{name}={value} would loosen the built-in default {default}; "
            f"NSFW thresholds are tighten-only"
        )
    return value


_DEFAULTS = {
    'nudenet': (0.20, 0.45),
    'falconsai': (0.40, 0.70),
    'clip': (0.40, 0.65),
    'opennsfw2': (0.35, 0.70),
    'extra_nsfw': (0.40, 0.75),
    # LittleNet's trained EfficientNet ensemble. Its per-class thresholds are
    # already applied inside littlenet_trained_image.predict(); here a
    # triggered class counts as full-strength (1.0) evidence so the per-model
    # BLOCK path fires with the same fail-closed semantics as the legacy
    # models. Sub-threshold classes contribute no evidence here — they are
    # already capped below the global block threshold by predict().
    'trained_image': (0.50, 0.80),
}


def _resolve_thresholds() -> dict[str, tuple[float, float]]:
    """Validate every model threshold once, at import time (fail fast)."""
    resolved = {}
    for model, (review_default, block_default) in _DEFAULTS.items():
        key = model.upper().replace('-', '_')
        review = _tighten_only_env(f'LITTLENET_{key}_REVIEW_THRESHOLD', review_default)
        block = _tighten_only_env(f'LITTLENET_{key}_BLOCK_THRESHOLD', block_default)
        resolved[model] = (review, max(review, block))
    return resolved


# Validated once at import so a loosening/malformed deployment config fails
# fast instead of silently moderating with weakened thresholds.
_THRESHOLDS = _resolve_thresholds()


def thresholds(model: str) -> tuple[float, float]:
    return _THRESHOLDS[model]


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _score_from_node(model: str, node: dict):
    if model == 'clip':
        clip = node.get('clip')
        if isinstance(clip, dict):
            return max(float(clip.get('adult', 0) or 0), float(clip.get('sexual', 0) or 0))
        return None
    if model == 'trained_image':
        sub = node.get('littlenet_trained_image')
        if isinstance(sub, dict):
            triggered = sub.get('triggered') or {}
            if any(triggered.values()):
                return 1.0
        return None
    value = node.get(model)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def classify_signals(signals: dict | None) -> dict:
    model_signals = (signals or {}).get('model_signals') or {}
    evidence = []
    for node in _walk(model_signals):
        for model in _DEFAULTS:
            score = _score_from_node(model, node)
            if score is None:
                continue
            review_t, block_t = thresholds(model)
            evidence.append({
                'model': model,
                'score': max(0.0, min(1.0, score)),
                'review_threshold': review_t,
                'block_threshold': block_t,
            })

    block_rows = [e for e in evidence if e['score'] >= e['block_threshold']]
    review_rows = [e for e in evidence if e['review_threshold'] <= e['score'] < e['block_threshold']]
    top = max(evidence, key=lambda e: e['score'], default=None)
    return {
        'has_evidence': bool(evidence),
        'block': bool(block_rows),
        'review': bool(review_rows) and not bool(block_rows),
        'top': top,
        'evidence': sorted(evidence, key=lambda e: e['score'], reverse=True)[:25],
    }
