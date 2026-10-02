"""Validated loader for LittleNet's versioned child-safety YAML policy.

The YAML is configuration, not an authorization bypass. Invalid/missing policy
fails closed by raising PolicyConfigError at import/use time in safety-critical
paths. Environment overrides remain supported only for numeric thresholds where
existing deployments already rely on them.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


class PolicyConfigError(RuntimeError):
    pass


_POLICY_PATH = Path(__file__).resolve().parents[1] / "config" / "safety_policy.yaml"


def _number(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise PolicyConfigError(f"{name} must be numeric") from exc
    if not 0.0 <= result <= 1.0:
        raise PolicyConfigError(f"{name} must be between 0 and 1")
    return result


def _labels(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise PolicyConfigError(f"{name} must be a non-empty list")
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        label = str(item or "").strip().lower().replace("_", " ").replace("-", " ")
        label = " ".join(label.split())
        if label and label not in seen:
            seen.add(label)
            out.append(label)
    if not out:
        raise PolicyConfigError(f"{name} contains no usable labels")
    return out


@lru_cache(maxsize=1)
def load_policy() -> dict[str, Any]:
    if not _POLICY_PATH.is_file():
        raise PolicyConfigError(f"missing safety policy: {_POLICY_PATH}")
    try:
        raw = yaml.safe_load(_POLICY_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PolicyConfigError(f"cannot parse safety policy: {exc}") from exc
    if not isinstance(raw, dict):
        raise PolicyConfigError("safety policy root must be a mapping")
    if int(raw.get("version") or 0) < 1:
        raise PolicyConfigError("safety policy version must be >= 1")
    if raw.get("fail_closed") is not True:
        raise PolicyConfigError("LittleNet safety policy must be fail_closed=true")

    thresholds = raw.get("thresholds")
    if not isinstance(thresholds, dict):
        raise PolicyConfigError("thresholds mapping is required")
    _number(thresholds.get("adult_block"), "thresholds.adult_block")
    review = _number(thresholds.get("weapon_review"), "thresholds.weapon_review")
    block = _number(thresholds.get("weapon_block"), "thresholds.weapon_block")
    if block < review:
        raise PolicyConfigError("weapon_block cannot be below weapon_review")

    levels = thresholds.get("levels")
    if not isinstance(levels, dict) or not levels:
        raise PolicyConfigError("thresholds.levels mapping is required")
    for level, values in levels.items():
        if not isinstance(values, dict):
            raise PolicyConfigError(f"thresholds.levels.{level} must be a mapping")
        review_t = _number(values.get("review"), f"{level}.review")
        block_t = _number(values.get("block"), f"{level}.block")
        if block_t < review_t:
            raise PolicyConfigError(f"{level}.block cannot be below review")

    families = raw.get("object_families")
    if not isinstance(families, dict) or not families:
        raise PolicyConfigError("object_families mapping is required")
    normalized_families: dict[str, dict[str, Any]] = {}
    all_labels: set[str] = set()
    for family, spec in families.items():
        if not isinstance(spec, dict):
            raise PolicyConfigError(f"object family {family} must be a mapping")
        action = str(spec.get("action") or "").upper()
        if action not in {"BLOCK", "REVIEW"}:
            raise PolicyConfigError(f"object family {family} has invalid action")
        labels = _labels(spec.get("labels"), f"object_families.{family}.labels")
        overlap = all_labels.intersection(labels)
        if overlap:
            raise PolicyConfigError(f"duplicate object labels across families: {sorted(overlap)}")
        all_labels.update(labels)
        normalized_families[str(family)] = {"action": action, "labels": labels}

    raw["object_families"] = normalized_families
    raw["object_label_count"] = len(all_labels)
    raw["adult_categories"] = {str(x).upper() for x in raw.get("adult_categories") or []}
    raw["hard_text_categories"] = {str(x).upper() for x in raw.get("hard_text_categories") or []}
    if not raw["adult_categories"] or not raw["hard_text_categories"]:
        raise PolicyConfigError("adult_categories and hard_text_categories are required")
    return raw


def reset_policy_cache() -> None:
    load_policy.cache_clear()
