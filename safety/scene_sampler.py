"""Scene-aware frame selection for LittleNet video moderation.

PySceneDetect augments (never replaces) the existing time-distributed sampling.
If the optional dependency cannot inspect a video, callers simply keep the
uniform samples so moderation never loses its current coverage.
"""
from __future__ import annotations

import os
from typing import List


def enabled() -> bool:
    return os.getenv("LITTLENET_ENABLE_SCENEDETECT", "1").strip().lower() not in {
        "0", "false", "no", "off"
    }


def scene_sample_indices(path: str, total_frames: int, max_indices: int = 30) -> List[int]:
    """Return representative frame indices from detected scene boundaries."""
    if not enabled() or total_frames <= 1 or max_indices <= 0:
        return []
    try:
        from scenedetect import open_video, SceneManager
        from scenedetect.detectors import ContentDetector

        threshold = float(os.getenv("LITTLENET_SCENEDETECT_THRESHOLD", "27"))
        min_scene_len = max(5, int(os.getenv("LITTLENET_SCENEDETECT_MIN_FRAMES", "12")))
        video = open_video(path)
        manager = SceneManager()
        manager.add_detector(ContentDetector(threshold=threshold, min_scene_len=min_scene_len))
        manager.detect_scenes(video=video, show_progress=False)
        scenes = manager.get_scene_list(start_in_scene=True)
    except Exception:
        return []

    indices: List[int] = []
    for start, end in scenes:
        try:
            first = max(0, min(total_frames - 1, int(start.get_frames())))
            last = max(first, min(total_frames - 1, int(end.get_frames()) - 1))
            middle = first + ((last - first) // 2)
        except Exception:
            continue
        # A cut frame and a scene midpoint complement uniform sampling well.
        for idx in (first, middle):
            if idx not in indices:
                indices.append(idx)
                if len(indices) >= max_indices:
                    return sorted(indices)
    return sorted(indices)


def combined_frame_indices(path: str, total_frames: int, requested: int) -> List[int]:
    """Blend scene-aware and evenly distributed frame indices within a hard cap."""
    requested = max(1, int(requested))
    total_frames = max(1, int(total_frames))
    uniform = [
        int(i * max(total_frames - 1, 0) / max(requested - 1, 1))
        for i in range(min(requested, total_frames))
    ]
    # Reserve up to half the budget for scene-derived evidence, then fill with
    # the original evenly distributed indices. Always remain <= requested.
    scene_budget = max(1, requested // 2)
    scene = scene_sample_indices(path, total_frames, scene_budget)
    merged: List[int] = []
    for idx in scene + uniform:
        if idx not in merged:
            merged.append(idx)
        if len(merged) >= requested:
            break
    return sorted(merged)
