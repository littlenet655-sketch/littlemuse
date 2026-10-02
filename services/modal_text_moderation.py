"""Cost-guarded Modal CPU client for text moderation.

Normal LittleNet text/chat/comment moderation uses the same scale-to-zero CPU
AI function as image-upload captions. This prevents routine text from waking the
T4. GPU fallback must be explicitly enabled by an operator.

The function name is configurable via LITTLENET_AI_TEXT_CPU_FUNCTION. The legacy
LITTLENET_AI_IMAGE_CPU_FUNCTION name is still honored as a fallback so existing
deployments that overrode it keep working; new deployments should use the
text-specific name.
"""
from __future__ import annotations

import os
from typing import Any


def _cpu_function_name() -> str:
    return (
        os.getenv("LITTLENET_AI_TEXT_CPU_FUNCTION", "").strip()
        or os.getenv("LITTLENET_AI_IMAGE_CPU_FUNCTION", "").strip()
        or "moderate_image_upload_cpu"
    )


def enabled() -> bool:
    if os.getenv("LITTLENET_AI_SERVER") == "1":
        return False
    raw = os.getenv("LITTLENET_USE_MODAL_TEXT_CPU", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def allow_gpu_fallback() -> bool:
    raw = os.getenv("LITTLENET_ALLOW_TEXT_GPU_FALLBACK", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def moderate_text(text: str) -> dict[str, Any]:
    if not enabled():
        raise RuntimeError("modal_text_cpu_disabled")

    import modal

    app_name = os.getenv("LITTLENET_AI_MODAL_APP", "littlemuse-ai").strip() or "littlemuse-ai"
    function_name = _cpu_function_name()

    fn = modal.Function.from_name(app_name, function_name)
    result = fn.remote(
        b"",
        "text-only.txt",
        (text or "")[:4000],
        True,
        False,
    )
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise RuntimeError("modal_text_cpu_invalid_result")
    signals = result.get("text_signals")
    if not isinstance(signals, dict) or not signals:
        raise RuntimeError("modal_text_cpu_signals_missing")
    return signals
