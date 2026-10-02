"""LittleNet's trained four-category image-safety ensemble.

The two checkpoints are staged on the persistent Modal model cache volume
(``/cache/models/``), overridable per checkpoint with
``LITTLENET_TRAINED_IMAGE_V2_PATH`` / ``LITTLENET_TRAINED_IMAGE_V3_PATH``, or
dropped into ``<repo>/models/`` for local development:

- V2: ``littlenet_core_safety_v2.pth`` — nudity + sexy (other V2 outputs ignored)
- V3: ``littlenet_weapons_violence_v3.pth`` — weapons + violence

The ensemble is auto-enabled only when BOTH checkpoint files exist. If either
file is absent, callers fall back to the legacy detector stack. This lets code
deploy safely before the private model artifacts are staged.
"""
from __future__ import annotations

import os
import math
import threading
from pathlib import Path
from typing import Any

_DEFAULT_V2 = "/cache/models/littlenet_core_safety_v2.pth"
_DEFAULT_V3 = "/cache/models/littlenet_weapons_violence_v3.pth"
# Local-dev staging: <repo>/models/<name> (also ./models/<name>), so dropping
# the private checkpoints into models/ enables the ensemble without env vars.
_REPO_ROOT = Path(__file__).resolve().parent.parent

_LOCK = threading.Lock()
_MODELS: tuple[Any, dict[str, Any], Any, dict[str, Any]] | None = None


def _flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "auto"}


def _candidates(env_name: str, default: str, repo_name: str) -> list[Path]:
    raw = (os.getenv(env_name) or "").strip()
    if raw:
        return [Path(raw)]
    return [
        Path(default),
        _REPO_ROOT / "models" / repo_name,
        Path("models") / repo_name,
    ]


def _resolve(env_name: str, default: str, repo_name: str) -> Path:
    for candidate in _candidates(env_name, default, repo_name):
        try:
            if candidate.is_file() and candidate.stat().st_size > 0:
                return candidate
        except OSError:
            continue
    return Path(default)


def paths() -> tuple[Path, Path]:
    """Resolve both checkpoint locations: first existing candidate wins.

    Order per checkpoint: explicit ``LITTLENET_TRAINED_IMAGE_{V2,V3}_PATH``,
    the Modal cache-volume default, ``<repo>/models/<name>``, then
    ``./models/<name>``. When nothing is staged, the defaults are returned so
    ``available()`` stays fail-closed (False) and callers fall back.
    """
    return (
        _resolve("LITTLENET_TRAINED_IMAGE_V2_PATH", _DEFAULT_V2, "littlenet_core_safety_v2.pth"),
        _resolve("LITTLENET_TRAINED_IMAGE_V3_PATH", _DEFAULT_V3, "littlenet_weapons_violence_v3.pth"),
    )


def available() -> bool:
    if not _flag("LITTLENET_ENABLE_TRAINED_IMAGE_ENSEMBLE", True):
        return False
    v2, v3 = paths()
    return v2.is_file() and v3.is_file() and v2.stat().st_size > 0 and v3.stat().st_size > 0


def _load_one(path: Path):
    import torch
    import torch.nn as nn
    from torchvision.models import efficientnet_b0

    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    if not isinstance(checkpoint, dict) or not isinstance(checkpoint.get("state_dict"), dict):
        raise RuntimeError(f"invalid LittleNet image checkpoint: {path.name}")
    labels = list(checkpoint.get("labels") or [])
    if not labels:
        raise RuntimeError(f"missing labels in LittleNet image checkpoint: {path.name}")

    model = efficientnet_b0(weights=None)
    in_features = model.classifier[1].in_features
    model.classifier[1] = nn.Linear(in_features, len(labels))
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    model.eval()
    return model, checkpoint


def _models():
    global _MODELS
    if _MODELS is not None:
        return _MODELS
    if not available():
        raise RuntimeError("trained_image_ensemble_not_staged")
    with _LOCK:
        if _MODELS is None:
            v2_path, v3_path = paths()
            v2_model, v2_ckpt = _load_one(v2_path)
            v3_model, v3_ckpt = _load_one(v3_path)
            required_v2 = {"nudity", "sexy"}
            required_v3 = {"weapons", "violence"}
            if not required_v2.issubset(set(v2_ckpt.get("labels") or [])):
                raise RuntimeError("V2 checkpoint missing nudity/sexy labels")
            if not required_v3.issubset(set(v3_ckpt.get("labels") or [])):
                raise RuntimeError("V3 checkpoint missing weapons/violence labels")
            _MODELS = (v2_model, v2_ckpt, v3_model, v3_ckpt)
    return _MODELS


def _transform(image_path: str):
    from PIL import Image
    from torchvision import transforms

    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(
            [0.485, 0.456, 0.406],
            [0.229, 0.224, 0.225],
        ),
    ])
    return transform(Image.open(image_path).convert("RGB")).unsqueeze(0)


def _scores(model, checkpoint: dict[str, Any], tensor) -> dict[str, float]:
    import torch

    with torch.inference_mode():
        probs = torch.sigmoid(model(tensor))[0].cpu().tolist()
    labels = list(checkpoint["labels"])
    return {label: float(probs[i]) for i, label in enumerate(labels)}


def _threshold(checkpoint: dict[str, Any], label: str, fallback: float) -> float:
    raw = (checkpoint.get("thresholds") or {}).get(label, fallback)
    # Reject non-numeric or non-finite checkpoint values BEFORE clamping:
    # min(NaN, fallback) is NaN, and the outer min(0.99, NaN) then yields
    # 0.99 — silently loosening the policy threshold to its weakest value.
    if not isinstance(raw, (int, float)) or not math.isfinite(raw):
        value = fallback
    else:
        value = float(raw)
    # Tighten-only: a checkpoint may lower the policy default (stricter
    # blocking) but never raise it (looser blocking). ``fallback`` is the
    # policy default for the label.
    return max(0.01, min(0.99, min(value, fallback)))


def _below_threshold_score(probability: float, threshold: float, ceiling: float) -> float:
    # Preserve the tuned per-class threshold: a sub-threshold probability must
    # never be promoted into a policy hard-block solely because the global
    # LittleNet policy threshold uses a different numerical scale.
    ratio = max(0.0, min(1.0, probability / max(threshold, 1e-6)))
    return min(ceiling, ratio * ceiling)


def predict(image_path: str) -> dict[str, Any]:
    """Return raw probabilities plus policy-calibrated LittleNet safety signals."""
    v2_model, v2_ckpt, v3_model, v3_ckpt = _models()
    tensor = _transform(image_path)

    v2 = _scores(v2_model, v2_ckpt, tensor)
    v3 = _scores(v3_model, v3_ckpt, tensor)

    thresholds = {
        "nudity": _threshold(v2_ckpt, "nudity", 0.89),
        "sexy": _threshold(v2_ckpt, "sexy", 0.82),
        "weapons": _threshold(v3_ckpt, "weapons", 0.59),
        "violence": _threshold(v3_ckpt, "violence", 0.49),
    }
    raw = {
        "nudity": float(v2["nudity"]),
        "sexy": float(v2["sexy"]),
        "weapons": float(v3["weapons"]),
        "violence": float(v3["violence"]),
    }
    triggered = {name: raw[name] >= thresholds[name] for name in raw}

    sexual_triggered = triggered["nudity"] or triggered["sexy"]
    if sexual_triggered:
        adult_score = max(0.80, raw["nudity"], raw["sexy"])
    else:
        adult_score = max(
            _below_threshold_score(raw["nudity"], thresholds["nudity"], 0.39),
            _below_threshold_score(raw["sexy"], thresholds["sexy"], 0.39),
        )

    weapon_score = max(0.80, raw["weapons"]) if triggered["weapons"] else 0.0

    if triggered["violence"]:
        violence_score = max(0.80, raw["violence"])
    elif raw["violence"] >= 0.80 * thresholds["violence"]:
        # Near-threshold violence goes to parent review under STRICT policy,
        # while clearly sub-threshold frames stay out of the risk path.
        violence_score = 0.50
    else:
        violence_score = 0.0

    general = max(adult_score, weapon_score, violence_score)
    if sexual_triggered:
        category = "ADULT"
    elif triggered["weapons"]:
        category = "WEAPON"
    else:
        category = "IMAGE"

    return {
        "adult_score": adult_score,
        "sexual_score": adult_score,
        "violence_score": violence_score,
        "weapon_score": weapon_score,
        "toxicity_score": 0.0,
        "general_score": general,
        "category": category,
        "total_safety_failure": False,
        "partial_safety_failure": False,
        "errors": [],
        "model_signals": {
            "littlenet_trained_image": {
                "raw_probabilities": raw,
                "thresholds": thresholds,
                "triggered": triggered,
                "source": {
                    "v2": paths()[0].name,
                    "v3": paths()[1].name,
                },
            }
        },
        "trained_image_ensemble": True,
    }


def reset_for_tests() -> None:
    global _MODELS
    _MODELS = None
