"""YOLO dangerous-object classification policy for LittleNet.

Detector confidence is evidence, not a child-safety probability. Vocabulary and
BLOCK/REVIEW families are versioned in config/safety_policy.yaml; deployment may
only tighten numeric thresholds through environment variables.
"""
from __future__ import annotations

import os
import re
from typing import Iterable

from .policy_config import load_policy


def _threshold(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(0.0, min(value, 1.0))


_POLICY = load_policy()
_THRESHOLDS = _POLICY["thresholds"]
YOLO_REVIEW_THRESHOLD = _threshold(
    "LITTLENET_YOLO_REVIEW_THRESHOLD", float(_THRESHOLDS["weapon_review"])
)
YOLO_BLOCK_THRESHOLD = _threshold(
    "LITTLENET_YOLO_BLOCK_THRESHOLD", float(_THRESHOLDS["weapon_block"])
)
if YOLO_BLOCK_THRESHOLD < YOLO_REVIEW_THRESHOLD:
    YOLO_BLOCK_THRESHOLD = YOLO_REVIEW_THRESHOLD


def normalize_label(label: str) -> str:
    value = str(label or "").strip().lower().replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", value)


def _family_index() -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for family, spec in _POLICY["object_families"].items():
        action = str(spec["action"]).upper()
        for label in spec["labels"]:
            out[normalize_label(label)] = (str(family), action)
    return out


_FAMILY_INDEX = _family_index()


def _extra_terms() -> set[str]:
    raw = os.getenv("LITTLENET_DANGEROUS_OBJECTS", "")
    return {normalize_label(x) for x in raw.split(",") if normalize_label(x)}


def classify_label(label: str) -> tuple[str, str] | None:
    norm = normalize_label(label)
    if not norm:
        return None
    configured = _FAMILY_INDEX.get(norm)
    if configured:
        return configured
    if norm in _extra_terms():
        # Custom deployment labels are conservative by default: medium evidence
        # is reviewed and high-confidence evidence is blocked.
        return "custom_dangerous", "BLOCK"
    return None


def classify_detections(detections: Iterable[dict] | None) -> dict:
    dangerous: list[dict] = []
    max_score = 0.0
    should_block = False
    should_review = False

    for row in detections or []:
        label = normalize_label(row.get("label", ""))
        classification = classify_label(label)
        if not classification:
            continue
        family, configured_action = classification
        try:
            confidence = float(row.get("confidence", 0) or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(confidence, 1.0))
        max_score = max(max_score, confidence)

        effective_action = "NONE"
        if configured_action == "BLOCK":
            if confidence >= YOLO_BLOCK_THRESHOLD:
                should_block = True
                effective_action = "BLOCK"
            elif confidence >= YOLO_REVIEW_THRESHOLD:
                should_review = True
                effective_action = "REVIEW"
        elif confidence >= YOLO_REVIEW_THRESHOLD:
            should_review = True
            effective_action = "REVIEW"

        dangerous.append(
            {
                "label": label,
                "family": family,
                "configured_action": configured_action,
                "effective_action": effective_action,
                "confidence": round(confidence, 4),
            }
        )

    dangerous.sort(key=lambda x: x["confidence"], reverse=True)
    return {
        "dangerous": dangerous[:25],
        "score": max_score,
        "block": should_block,
        "review": bool(should_review and not should_block),
        "review_threshold": YOLO_REVIEW_THRESHOLD,
        "block_threshold": YOLO_BLOCK_THRESHOLD,
        "configured_label_count": int(_POLICY.get("object_label_count") or 0),
        "policy_version": int(_POLICY.get("version") or 0),
    }


def _walk_model_signals(value):
    if isinstance(value, dict):
        yolo = value.get("yolo")
        if isinstance(yolo, dict):
            yield from yolo.get("detections") or []
        for child in value.values():
            yield from _walk_model_signals(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_model_signals(child)


def classify_signals(signals: dict | None) -> dict:
    """Classify YOLO detections from image or sampled-video diagnostics."""
    model_signals = (signals or {}).get("model_signals") or {}
    return classify_detections(list(_walk_model_signals(model_signals)))


def dangerous_label_coverage(model_names) -> list[str]:
    """Return configured dangerous labels exposed by a loaded checkpoint."""
    if isinstance(model_names, dict):
        names = model_names.values()
    else:
        names = model_names or []
    return sorted(
        {
            normalize_label(name)
            for name in names
            if classify_label(name) is not None
        }
    )
