"""Adaptive LittleNet video moderation.

Short videos use a first-frame + later-frame fast pass. Only uncertain evidence
expands into the existing scene-aware/uniform frame budget; long videos keep the
full bounded coverage path.
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


def _initial_frame_indices(total: int, budget: int) -> list[int]:
    """Cheap first pass: frame zero plus one later frame around 70%."""
    total=max(0,int(total));budget=max(1,int(budget))
    if total<=1 or budget==1:return [0]
    later=max(1,min(total-1,int(round((total-1)*0.70))))
    return [0,later] if later else [0]


def _signals_uncertain(signals: dict) -> bool:
    """Whether a clearly non-blocking frame deserves the expanded sampler."""
    from .policy import decide

    decision=decide(signals)
    if decision.action!="ALLOW":
        return True
    if signals.get("partial_safety_failure") or signals.get("total_safety_failure"):
        return True
    try:threshold=max(0.0,min(1.0,float(os.getenv("LITTLENET_VIDEO_EXPAND_SCORE","0.15"))))
    except (TypeError,ValueError):threshold=0.15
    score=max(
        float(signals.get("adult_score",0) or 0),
        float(signals.get("sexual_score",0) or 0),
        float(signals.get("weapon_score",0) or 0),
        float(signals.get("violence_score",0) or 0),
        float(signals.get("general_score",0) or 0),
    )
    return score>=threshold


def _sample_indices(path: str, indices: list[int]):
    import cv2
    from .policy import decide

    cap=cv2.VideoCapture(path)
    outs=[];inspected=[];failed=[]
    try:
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES,int(idx))
            good,frame=cap.read()
            if not good:
                failed.append(int(idx))
                outs.append(normalize_signals({
                    "category":"IMAGE",
                    "total_safety_failure":True,
                    "errors":["video_frame_decode_failed"],
                    "frame_index":int(idx),
                },category="IMAGE"))
                continue
            fd,tmp=tempfile.mkstemp(suffix=".jpg");os.close(fd)
            cv2.imwrite(tmp,frame)
            try:
                signals=check_image(tmp,ocr=env_flag("LITTLENET_ENABLE_OCR_VIDEO_FRAMES"))
                outs.append(signals);inspected.append(int(idx))
                if decide(signals).action=="BLOCK":
                    break
            finally:
                try:os.unlink(tmp)
                except OSError:pass
    finally:
        cap.release()
    return outs,inspected,failed


def _adaptive_sample_frames(path: str, requested: int, force_expand: bool=False):
    """Two-frame first pass; expand to scene+uniform evidence only when needed."""
    total=_frame_count(path)
    if total<=0:return [],[],[],False,[]

    budget=max(1,int(requested))
    first_indices=_initial_frame_indices(total,budget)
    outs,inspected,failed=_sample_indices(path,first_indices)

    from .policy import decide
    blocked=any(decide(signals).action=="BLOCK" for signals in outs)
    uncertain=force_expand or bool(failed) or any(_signals_uncertain(signals) for signals in outs)
    if blocked or not uncertain or len(inspected)+len(failed)>=budget:
        return outs,inspected,failed,False,first_indices

    planned=combined_frame_indices(path,total,budget)
    # Add a midpoint candidate because the first pass intentionally samples
    # near 70%; this catches a changed middle scene without exceeding budget.
    midpoint=max(0,min(total-1,(total-1)//2))
    candidates=[]
    for idx in [midpoint,*planned]:
        idx=int(idx)
        if idx not in first_indices and idx not in candidates:
            candidates.append(idx)
    remaining=max(0,budget-(len(inspected)+len(failed)))
    extra_indices=candidates[:remaining]
    if not extra_indices:
        return outs,inspected,failed,True,first_indices

    extra_outs,extra_inspected,extra_failed=_sample_indices(path,extra_indices)
    return (
        outs+extra_outs,
        inspected+extra_inspected,
        failed+extra_failed,
        True,
        first_indices,
    )

def check_video(path: str, max_frames=None):
    """Moderate video with a cheap first pass and uncertainty-driven expansion."""
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
        requested=_video_sample_count(path,max_frames)
        coverage=video_sampling_coverage(path,requested)
        try:adaptive_max=max(1.0,float(os.getenv("LITTLENET_VIDEO_ADAPTIVE_MAX_SECONDS","60")))
        except (TypeError,ValueError):adaptive_max=60.0
        force_expand=float(coverage.get("duration_seconds") or 0)>adaptive_max

        outs,indices,failed_indices,expanded,first_pass_indices=timed_call(
            "video_frames",
            lambda:_adaptive_sample_frames(path,requested,force_expand=force_expand),
            timeout_seconds("video_frames",240),
        )
        if not outs:
            return normalize_signals(
                {"total_safety_failure":True,"category":"VIDEO","errors":["no_video_frames"]},
                category="VIDEO",
            )

        keys=["adult_score","sexual_score","weapon_score","violence_score","general_score"]
        out={k:max(float(x.get(k,0) or 0) for x in outs) for k in keys}
        out["toxicity_score"]=0
        any_total_failure=any(x.get("total_safety_failure") is True for x in outs)
        # Incomplete temporal coverage is only a failure after we deliberately
        # expanded (or for >60s videos). A clear short Reel may short-circuit
        # after its first + later frame by design.
        coverage_failure=bool(expanded and not coverage["coverage_complete"])
        out["partial_safety_failure"]=(
            coverage_failure
            or bool(failed_indices)
            or any_total_failure
            or any(x.get("partial_safety_failure") is True for x in outs)
        )
        out["total_safety_failure"]=bool(outs) and all(x.get("total_safety_failure") is True for x in outs)
        out["errors"]=[err for x in outs for err in x.get("errors",[])]
        if coverage_failure:
            out["errors"].append("video_temporal_coverage_incomplete")
        out["model_signals"]={
            "sampling_strategy":"adaptive_first_later_then_scene_uniform_if_uncertain",
            "adaptive_first_pass":True,
            "expanded_sampling":bool(expanded),
            "first_pass_frame_indices":first_pass_indices,
            "sampled_frames":len(outs),
            "inspected_frames":len(indices),
            "requested_frames":requested,
            "frame_indices":indices,
            "failed_frame_indices":failed_indices,
            **coverage,
            "frames":[x.get("model_signals",{}) for x in outs],
        }
        out["category"]=(
            "ADULT" if max(out["adult_score"],out["sexual_score"])>=.4
            else ("WEAPON" if out["weapon_score"]>=.45 else "VIDEO")
        )
        return normalize_signals(out,category="VIDEO")
    except Exception as exc:
        return normalize_signals(
            {
                "total_safety_failure":True,
                "category":"VIDEO",
                "errors":["video_timeout" if "timeout" in str(exc).lower() else "video_processing"],
            },
            category="VIDEO",
        )

