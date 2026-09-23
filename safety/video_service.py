"""Scene-aware LittleNet video moderation.

Combines PySceneDetect scene evidence with the existing evenly-distributed frame
budget. This module is the runtime video entry point; visual_service.check_video
is retained temporarily for compatibility with older imports/tests.
"""
from __future__ import annotations

import os
import tempfile

from .common import env_flag, normalize_signals, timed_call, timeout_seconds
from .scene_sampler import combined_frame_indices
from .visual_service import check_image, _video_sample_count, video_sampling_coverage


def _frame_count(path: str):
    import cv2
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()
    return total


def _sample_frames(path: str, requested: int):
    import cv2
    from .policy import decide

    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total <= 0:
        cap.release()
        return [], [], []
    indices = combined_frame_indices(path, total, requested)
    outs = []
    inspected = []
    failed = []
    try:
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            good, frame = cap.read()
            if not good:
                failed.append(int(idx))
                outs.append(normalize_signals({
                    "category":"IMAGE",
                    "total_safety_failure":True,
                    "errors":["video_frame_decode_failed"],
                    "frame_index":int(idx),
                },category="IMAGE"))
                continue
            fd, tmp = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)
            cv2.imwrite(tmp, frame)
            try:
                # Frame OCR stays off unless explicitly enabled: OCR across the
                # bounded frame set can otherwise dominate moderation time.
                signals = check_image(tmp, ocr=env_flag('LITTLENET_ENABLE_OCR_VIDEO_FRAMES'))
                outs.append(signals)
                inspected.append(int(idx))
                if decide(signals).action == "BLOCK":
                    break
            finally:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
    finally:
        cap.release()
    return outs, inspected, failed


def check_video(path: str, max_frames=None):
    """Moderate a video with bounded scene-aware + uniform frame evidence."""
    from .remote_client import enabled, moderate_file

    if enabled():
        try:
            return normalize_signals(moderate_file("VIDEO", path), category="VIDEO")
        except Exception:
            return normalize_signals(
                {"total_safety_failure": True, "category": "VIDEO", "errors": ["remote_ai_unavailable"]},
                category="VIDEO",
            )

    try:
        requested = _video_sample_count(path, max_frames)
        coverage = video_sampling_coverage(path, requested)
        outs, indices, failed_indices = timed_call(
            "video_frames",
            lambda: _sample_frames(path, requested),
            timeout_seconds("video_frames", 240),
        )
        if not outs:
            return normalize_signals(
                {"total_safety_failure": True, "category": "VIDEO", "errors": ["no_video_frames"]},
                category="VIDEO",
            )
        keys = ["adult_score", "sexual_score", "weapon_score", "violence_score", "general_score"]
        out = {k: max(float(x.get(k, 0)) for x in outs) for k in keys}
        out["toxicity_score"] = 0
        any_total_failure=any(x.get("total_safety_failure") is True for x in outs)
        out["partial_safety_failure"] = (not coverage["coverage_complete"]) or bool(failed_indices) or any_total_failure or any(x.get("partial_safety_failure") is True for x in outs)
        out["total_safety_failure"] = bool(outs) and all(x.get("total_safety_failure") is True for x in outs)
        out["errors"] = [err for x in outs for err in x.get("errors", [])]
        if not coverage["coverage_complete"]:
            out["errors"].append("video_temporal_coverage_incomplete")
        out["model_signals"] = {
            "sampling_strategy": "pyscenedetect_plus_uniform",
            "sampled_frames": len(outs),
            "inspected_frames": len(indices),
            "requested_frames": requested,
            "frame_indices": indices,
            "failed_frame_indices": failed_indices,
            **coverage,
            "frames": [x.get("model_signals", {}) for x in outs],
        }
        out["category"] = (
            "ADULT" if max(out["adult_score"], out["sexual_score"]) >= .4
            else ("WEAPON" if out["weapon_score"] >= .45 else "VIDEO")
        )
        return normalize_signals(out, category="VIDEO")
    except Exception as exc:
        return normalize_signals(
            {
                "total_safety_failure": True,
                "category": "VIDEO",
                "errors": ["video_timeout" if "timeout" in str(exc).lower() else "video_processing"],
            },
            category="VIDEO",
        )
