"""Media processing worker for LittleNet Phase 2 asynchronous uploads.

Validates quarantine media, executes bounded frame sampling and safety checks,
generates posters / faststart video derivatives, and atomically transitions
posts from quarantine to published or review/blocked states.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

from config import Config
from database.connection import execute, execute_count, fetch_all, fetch_one
from safety.moderation_service import evaluate, record, safety_level
from safety.policy import decide
from services import object_storage
from services.media_sanitizer import strip_video_audio_in_place
from services.moderation_cache import cached_or_none_for_file, cached_or_none_for_text, store_cached_signals
from services.social import parent_notify

logger = logging.getLogger(__name__)
_worker_locks_guard = threading.Lock()
_worker_locks: dict[int, threading.Lock] = {}


def delete_orphaned_media_refs(refs: list[str | None], context: str) -> list[str]:
    """Delete orphaned R2 references or local files left behind by a failed publish.

    Uses the real ``object_storage.is_reference`` API (the historical
    ``is_r2_reference`` attribute never existed; the resulting AttributeError
    used to be swallowed by the inner except, leaking orphaned R2 objects).

    Every failure is logged with the object-key prefix as context (never
    secrets or credential-bearing URLs) and the ref is handed to the durable
    media-delete outbox so a transient R2 outage does not lose the cleanup.
    Returns the list of refs that could NOT be deleted so the caller can
    record or re-raise — failures are never silently swallowed.
    """
    failed: list[str] = []
    for ref in refs:
        if not ref:
            continue
        ref_str = str(ref)
        try:
            if object_storage.is_reference(ref_str):
                object_storage.delete_reference(ref_str)
            else:
                Path(ref_str).unlink(missing_ok=True)
        except (RuntimeError, OSError) as exc:
            logger.exception(
                "Orphan media cleanup failed (%s): ref_prefix=%s error=%s: %s",
                context,
                ref_str[:64],
                type(exc).__name__,
                exc,
            )
            failed.append(ref_str)
        except Exception as exc:
            logger.exception(
                "Orphan media cleanup failed unexpectedly (%s): ref_prefix=%s error=%s: %s",
                context,
                ref_str[:64],
                type(exc).__name__,
                exc,
            )
            failed.append(ref_str)
        if ref_str in failed:
            try:
                from services.media_outbox import enqueue_delete

                enqueue_delete(ref_str, source_table=f"orphan_cleanup:{context}")
            except Exception:
                logger.exception(
                    "Failed to enqueue orphan delete for %s (context=%s)",
                    ref_str[:64],
                    context,
                )
    return failed


def _notify_approved_followers(post_id: int, child_id: int, kind: str) -> None:
    """Idempotently notify eligible approved followers when content reaches ALLOWED."""
    try:
        user = fetch_one("SELECT full_name, username FROM users WHERE user_id=%s", (child_id,))
        author_name = (user.get("full_name") or user.get("username") or "A friend") if user else "A friend"

        k_lower = str(kind or "post").lower()
        if k_lower == "reel":
            msg = f"{author_name} posted a new Reel"
            notif_type = "NEW_REEL"
            target_url = f"/kids/reels?id={post_id}"
        elif k_lower == "story":
            msg = f"{author_name} added to their Story"
            notif_type = "NEW_STORY"
            target_url = f"/kids/story-viewer?id={post_id}"
        else:
            msg = f"{author_name} shared a new post"
            notif_type = "NEW_POST"
            target_url = f"/kids/home?post_id={post_id}"

        execute(
            """INSERT INTO notifications(user_id, actor_id, notification_type, message, target_url)
               SELECT f.child_id, %s, %s, %s, %s
               FROM followers f
               WHERE f.following_child_id = %s AND f.approved = TRUE AND f.approval_stage = 'ACTIVE'
               AND NOT EXISTS (
                   SELECT 1 FROM notifications n
                   WHERE n.user_id = f.child_id AND n.actor_id = %s
                     AND n.notification_type = %s AND n.target_url = %s
               )""",
            (child_id, notif_type, msg, target_url, child_id, child_id, notif_type, target_url),
        )
    except Exception:
        pass


def _make_video_derivatives(source_path: Path, temp_dir: Path) -> tuple[Path, Path | None]:
    """Generate +faststart video and poster thumbnail using ffmpeg if available.
    Fails closed if audio stripping or processing fails.
    """
    clean_video = temp_dir / f"clean_{source_path.name}"
    poster_image = temp_dir / f"poster_{source_path.stem}.jpg"

    # Always strip audio for child safety — fail closed on exception
    shutil.copy2(source_path, clean_video)
    try:
        strip_video_audio_in_place(str(clean_video))
    except Exception as exc:
        raise RuntimeError(f"video_sanitization_failed: {exc}") from exc

    if not shutil.which("ffmpeg"):
        return clean_video, None

    try:
        # Faststart MP4
        faststart_path = temp_dir / f"fast_{source_path.stem}.mp4"
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(clean_video),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-an", str(faststart_path),
        ]
        res = subprocess.run(cmd, capture_output=True, timeout=60)
        final_video = faststart_path if res.returncode == 0 and faststart_path.is_file() else clean_video

        # Poster thumbnail
        poster_cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", "0.2", "-i", str(final_video),
            "-frames:v", "1", "-vf", "scale=480:-2", str(poster_image),
        ]
        res_p = subprocess.run(poster_cmd, capture_output=True, timeout=30)
        final_poster = poster_image if res_p.returncode == 0 and poster_image.is_file() else None
        return final_video, final_poster
    except Exception as exc:
        raise RuntimeError(f"video_transcoding_failed: {exc}") from exc



def _make_image_moderation_proxy(source_path: Path, temp_dir: Path) -> Path:
    """Create a bounded JPEG used only for AI transfer/inference.

    The clean full-resolution image remains the publication source. Most visual
    safety models resize internally (224-640px), so sending multi-megapixel
    originals wastes web/GPU-container time without improving their input.
    """
    from PIL import Image

    try:
        max_px = int(os.getenv("LITTLENET_IMAGE_MODERATION_MAX_PX", "1600"))
    except (TypeError, ValueError):
        max_px = 1600
    max_px = max(640, min(max_px, 2048))

    proxy = temp_dir / "moderation_image.jpg"
    with Image.open(source_path) as img:
        work = img.convert("RGB")
        work.thumbnail((max_px, max_px))
        work.save(proxy, format="JPEG", quality=88, optimize=True)
    if not proxy.is_file() or proxy.stat().st_size <= 0:
        raise RuntimeError("moderation_image_proxy_empty")
    return proxy


def _merge_signals(text_signals: dict | None, media_signals: dict | None) -> dict:
    t = text_signals or {}
    m = media_signals or {}
    merged_models = {}
    if isinstance(t.get("model_signals"), dict):
        merged_models.update(t["model_signals"])
    if isinstance(m.get("model_signals"), dict):
        merged_models.update(m["model_signals"])

    return {
        "adult_score": max(float(t.get("adult_score") or 0.0), float(m.get("adult_score") or 0.0)),
        "violence_score": max(float(t.get("violence_score") or 0.0), float(m.get("violence_score") or 0.0)),
        "weapon_score": max(float(t.get("weapon_score") or 0.0), float(m.get("weapon_score") or 0.0)),
        "toxicity_score": max(float(t.get("toxicity_score") or 0.0), float(m.get("toxicity_score") or 0.0)),
        "risk_score": max(float(t.get("risk_score") or 0.0), float(m.get("risk_score") or 0.0)),
        "partial_safety_failure": bool(t.get("partial_safety_failure") or m.get("partial_safety_failure")),
        "total_safety_failure": bool(t.get("total_safety_failure") or m.get("total_safety_failure")),
        "model_signals": merged_models,
        "details": {
            "text": t,
            "media": m,
        },
    }


def _renew_worker_lease(post_id: int, worker_exec_token: str, extend_seconds: int = 300) -> bool:
    """Extend lease expiration for an active worker to prevent lease expiration during long operations."""
    try:
        updated = execute(
            """UPDATE posts
               SET processing_lease_expires_at = NOW() + (%s || ' seconds')::INTERVAL
               WHERE post_id = %s AND processing_lease_token = %s AND processing_status = 'PROCESSING'
               RETURNING post_id""",
            (str(extend_seconds), post_id, worker_exec_token),
            returning=True,
        )
        return bool(updated)
    except Exception as exc:
        logger.warning("Failed to renew lease for post %s: %s", post_id, exc)
        return False


def process_media_job(
    post_id: int,
    child_id: int,
    object_key: str,
    kind: str,
    lease_token: str | None = None,
) -> dict[str, Any]:
    """Prevent duplicate work in-process; the database lease covers other workers."""
    with _worker_locks_guard:
        worker_lock = _worker_locks.setdefault(int(post_id), threading.Lock())
    if not worker_lock.acquire(blocking=False):
        return {"ok": True, "status": "PROCESSING", "already_claimed": True, "idempotent": True}
    try:
        return _process_media_job_impl(post_id, child_id, object_key, kind, lease_token)
    finally:
        worker_lock.release()
        with _worker_locks_guard:
            if _worker_locks.get(int(post_id)) is worker_lock and not worker_lock.locked():
                _worker_locks.pop(int(post_id), None)


def _process_media_job_impl(
    post_id: int,
    child_id: int,
    object_key: str,
    kind: str,
    lease_token: str | None = None,
) -> dict[str, Any]:
    """Worker task entry point. Idempotent: safe to run multiple times."""
    post = fetch_one(
        """SELECT post_id, child_id, media_type, caption, content_category,
                  audience_age_group, is_story, is_reel, processing_status, moderation_status,
                  processing_lease_token, processing_lease_expires_at
           FROM posts WHERE post_id=%s""",
        (post_id,),
    )
    if not post:
        return {"ok": False, "error": "post_not_found"}

    # Idempotent skip if already terminal
    if post["processing_status"] in ("ALLOWED", "BLOCKED", "REVIEW"):
        return {"ok": True, "status": post["processing_status"], "idempotent": True}
    if post["processing_status"] == "FAILED":
        return {"ok": False, "status": "FAILED", "error": "terminal_failure", "idempotent": True}

    # Atomic per-post worker claim/lease: exactly one worker owns a processing attempt
    worker_exec_token = uuid.uuid4().hex
    claimed = execute(
        """UPDATE posts
           SET processing_status='PROCESSING',
               processing_lease_token=%s,
               processing_lease_expires_at=NOW() + INTERVAL '300 seconds',
               processing_started_at=COALESCE(processing_started_at, NOW()),
               last_attempt_at=NOW()
           WHERE post_id=%s
             AND processing_status NOT IN ('ALLOWED', 'BLOCKED', 'FAILED')
             AND (
               (%s::text IS NOT NULL AND processing_lease_token=%s::text)
               OR
               (%s::text IS NULL AND (processing_lease_token IS NULL OR processing_lease_expires_at < NOW()))
             )
           RETURNING post_id, child_id, media_type, caption, content_category,
                     audience_age_group, is_story, is_reel, processing_status, moderation_status,
                     processing_lease_token""",
        (worker_exec_token, post_id, lease_token, lease_token, lease_token),
        returning=True,
    )
    if not claimed:
        latest = fetch_one("SELECT processing_status FROM posts WHERE post_id=%s", (post_id,))
        cur_status = latest["processing_status"] if latest else "UNKNOWN"
        return {"ok": True, "status": cur_status, "already_claimed": True, "idempotent": True}

    post = claimed

    # R2 references must never fall back to a container-local path. That makes a
    # missing worker secret look like missing user media and wastes every retry.
    local_quarantine_file = Path(object_key).is_file()
    if object_storage.is_reference(object_key) and not object_storage.enabled() and not local_quarantine_file:
        execute(
            """UPDATE posts
               SET processing_status='UPLOADED', processing_error='r2_storage_unavailable',
                   processing_lease_token=NULL, processing_lease_expires_at=NULL
               WHERE post_id=%s AND processing_lease_token=%s""",
            (post_id, worker_exec_token),
        )
        return {"ok": False, "error": "r2_storage_unavailable", "retryable": True}

    # Check quarantine object size via head_object if storage enabled.
    if object_storage.enabled() and not local_quarantine_file:
        try:
            head = object_storage.head_object(object_key)
            if head is None:
                execute(
                    """UPDATE posts
                       SET processing_status='UPLOADED', processing_error='quarantine_object_unavailable',
                           processing_lease_token=NULL, processing_lease_expires_at=NULL
                       WHERE post_id=%s AND processing_lease_token=%s""",
                    (post_id, worker_exec_token),
                )
                return {"ok": False, "error": "quarantine_object_unavailable", "retryable": True}
            if int(head.get("content_length", 0) or 0) > Config.MAX_CONTENT_LENGTH:
                try:
                    object_storage.delete_reference(object_key)
                except Exception:
                    pass
                execute(
                    """UPDATE posts
                       SET processing_status='FAILED', processing_error='upload_size_exceeded',
                           processing_completed_at=NOW(), processing_lease_token=NULL,
                           processing_lease_expires_at=NULL
                       WHERE post_id=%s AND processing_lease_token=%s""",
                    (post_id, worker_exec_token),
                )
                return {"ok": False, "error": "upload_size_exceeded"}
        except Exception as exc:
            execute(
                """UPDATE posts
                   SET processing_status='UPLOADED', processing_error=%s,
                       processing_lease_token=NULL, processing_lease_expires_at=NULL
                   WHERE post_id=%s AND processing_lease_token=%s""",
                (f"r2_preflight_failed: {type(exc).__name__}", post_id, worker_exec_token),
            )
            return {"ok": False, "error": "r2_preflight_failed", "retryable": True}

    tags_rows = fetch_all("SELECT tag FROM post_tags WHERE post_id=%s", (post_id,))
    tags_text = " ".join(f"#{r['tag']}" for r in tags_rows)
    combined_text = f"{post.get('caption') or ''} {tags_text}".strip()

    media_type = post.get("media_type") or "VIDEO"
    temp_dir = Path(tempfile.mkdtemp(prefix=f"littlenet_proc_{post_id}_"))
    lease_stop = threading.Event()
    lease_lost = threading.Event()

    def keep_lease_alive() -> None:
        while not lease_stop.wait(60):
            if not _renew_worker_lease(post_id, worker_exec_token, 300):
                lease_lost.set()
                return

    lease_thread = threading.Thread(target=keep_lease_alive, name=f"media-lease-{post_id}", daemon=True)
    lease_thread.start()

    def require_active_lease() -> None:
        if lease_lost.is_set() or not _renew_worker_lease(post_id, worker_exec_token, 300):
            lease_lost.set()
            raise RuntimeError("processing_lease_lost")

    try:
        source_suffix = Path(str(object_key)).suffix.lower()
        source_local = temp_dir / f"quarantine_source{source_suffix if source_suffix in {'.jpg', '.jpeg', '.png', '.webp', '.mp4', '.mov'} else '.bin'}"
        if object_storage.enabled():
            object_storage.download_file(object_key, source_local)
        else:
            candidate = Path(object_key)
            if not candidate.is_file():
                for mock_candidate in Path("uploads/mock_quarantine").rglob("*"):
                    if mock_candidate.is_file() and object_key in str(mock_candidate):
                        candidate = mock_candidate
                        break
            if candidate.is_file() and candidate.stat().st_size > 0:
                shutil.copy2(candidate, source_local)

        if not source_local.is_file() or source_local.stat().st_size <= 0:
            execute(
                """UPDATE posts
                   SET processing_status='FAILED', processing_error='quarantine_media_missing_or_empty',
                       processing_completed_at=NOW(), processing_lease_token=NULL,
                       processing_lease_expires_at=NULL
                   WHERE post_id=%s AND processing_lease_token=%s""",
                (post_id, worker_exec_token),
            )
            return {"ok": False, "error": "quarantine_media_missing_or_empty"}

        if source_local.is_file() and source_local.stat().st_size > Config.MAX_CONTENT_LENGTH:
            execute(
                """UPDATE posts
                   SET processing_status='FAILED', processing_error='upload_size_exceeded',
                       processing_completed_at=NOW(), processing_lease_token=NULL,
                       processing_lease_expires_at=NULL
                   WHERE post_id=%s AND processing_lease_token=%s""",
                (post_id, worker_exec_token),
            )
            return {"ok": False, "error": "upload_size_exceeded"}

        final_media_local = source_local
        final_poster_local = None

        if media_type == "VIDEO":
            from safety.visual_service import video_duration_seconds

            duration = video_duration_seconds(str(source_local))
            limit = (
                Config.REEL_MAX_SECONDS
                if kind.lower() == "reel"
                else Config.STORY_MAX_SECONDS
                if kind.lower() == "story"
                else Config.VIDEO_MAX_SECONDS
            )
            if duration > limit:
                execute(
                    """UPDATE posts
                       SET processing_status='FAILED', processing_error='video_duration_exceeded',
                           processing_completed_at=NOW(), processing_lease_token=NULL,
                           processing_lease_expires_at=NULL
                       WHERE post_id=%s AND processing_lease_token=%s""",
                    (post_id, worker_exec_token),
                )
                return {"ok": False, "error": "video_duration_exceeded"}

            final_media_local, final_poster_local = _make_video_derivatives(source_local, temp_dir)
            _renew_worker_lease(post_id, worker_exec_token, 300)
        elif media_type == "IMAGE":
            try:
                from PIL import Image, ImageOps
                with Image.open(source_local) as img:
                    img = ImageOps.exif_transpose(img)
                    clean_img_path = temp_dir / "clean_image.jpg"
                    # Strip EXIF/GPS by saving a fresh clean JPEG RGB image
                    img.convert("RGB").save(clean_img_path, format="JPEG", quality=92, optimize=True)
                    if not clean_img_path.is_file() or clean_img_path.stat().st_size == 0:
                        raise RuntimeError("clean_image_empty")
                    final_media_local = clean_img_path
            except Exception as exc:
                execute(
                    """UPDATE posts
                       SET processing_status='FAILED', processing_error=%s,
                           processing_completed_at=NOW(), processing_lease_token=NULL,
                           processing_lease_expires_at=NULL
                       WHERE post_id=%s AND processing_lease_token=%s""",
                    (f"image_sanitization_failed: {exc}", post_id, worker_exec_token),
                )
                raise RuntimeError(f"image_sanitization_failed: {exc}") from exc

        # AI Moderation
        #
        # Cost controls:
        # 1) reuse exact, versioned model signals when safe to do so;
        # 2) send caption + media in one protected AI request when both miss;
        # 3) for images, send a bounded proxy to AI while publishing the clean
        #    full-resolution source.
        moderation_media_local = final_media_local
        if media_type == "IMAGE":
            moderation_media_local = _make_image_moderation_proxy(Path(final_media_local), temp_dir)

        text_fingerprint = None
        text_signals = {}
        if combined_text:
            try:
                text_fingerprint, text_signals = cached_or_none_for_text(combined_text)
            except Exception:
                logger.info("Text moderation cache unavailable for post %s", post_id, exc_info=True)
                text_signals = {}

        media_fingerprint = None
        media_signals = {}
        try:
            media_fingerprint, media_signals = cached_or_none_for_file(media_type, moderation_media_local)
        except Exception:
            logger.info("Media moderation cache unavailable for post %s", post_id, exc_info=True)
            media_signals = {}

        text_needed = bool(combined_text) and not text_signals
        media_needed = not media_signals

        # Preserve the original cache-miss state before inference recalculates
        # text_needed/media_needed. Fresh inference results should be cached once,
        # while cache hits should not overwrite/reset existing cache entries.
        text_cache_miss = text_needed
        media_cache_miss = media_needed

        # Production IMAGE uploads are handled by a direct Modal CPU function.
        # This is the main first-upload cost guard: an ordinary photo does not
        # wake the T4 at all. The same visual models run with LITTLENET_DEVICE=cpu.
        if media_type == "IMAGE" and (text_needed or media_needed):
            from services.modal_image_moderation import (
                allow_gpu_fallback as image_gpu_fallback_allowed,
                enabled as modal_image_cpu_enabled,
                moderate_image_upload as moderate_image_upload_cpu,
            )

            if modal_image_cpu_enabled():
                try:
                    cpu_result = moderate_image_upload_cpu(
                        str(moderation_media_local),
                        combined_text if text_needed else "",
                        run_text=text_needed,
                        run_media=media_needed,
                    )
                    if text_needed:
                        text_signals = cpu_result.get("text_signals") or {}
                    if media_needed:
                        media_signals = cpu_result.get("media_signals") or {}
                except Exception:
                    logger.warning("CPU image moderation failed for post %s", post_id, exc_info=True)
                    if not image_gpu_fallback_allowed():
                        # Budget guarantee: never silently turn a CPU problem into
                        # GPU spend. Fail closed; a later redrive can retry CPU.
                        if text_needed:
                            text_signals = {
                                "category": "TEXT",
                                "total_safety_failure": True,
                                "errors": ["modal_cpu_image_moderation_unavailable"],
                            }
                        if media_needed:
                            media_signals = {
                                "category": "IMAGE",
                                "total_safety_failure": True,
                                "errors": ["modal_cpu_image_moderation_unavailable"],
                            }

            text_needed = bool(combined_text) and not text_signals
            media_needed = not media_signals

        # VIDEO (and explicit image GPU fallback, if an operator enables it)
        # uses one bundled request when both text and media need model evidence.
        if text_needed and media_needed:
            from safety.remote_client import enabled as remote_ai_enabled, moderate_upload

            if remote_ai_enabled():
                try:
                    bundled = moderate_upload(media_type, str(moderation_media_local), combined_text)
                    text_signals = bundled.get("text_signals") or {}
                    media_signals = bundled.get("media_signals") or {}
                except Exception:
                    # Do not fan one failed upload into two more GPU retries.
                    logger.warning("Bundled AI moderation failed for post %s", post_id, exc_info=True)
                    text_signals = {
                        "category": "TEXT",
                        "total_safety_failure": True,
                        "errors": ["remote_ai_upload_bundle_unavailable"],
                    }
                    media_signals = {
                        "category": media_type,
                        "total_safety_failure": True,
                        "errors": ["remote_ai_upload_bundle_unavailable"],
                    }
            else:
                text_signals, _ = evaluate(child_id, "TEXT", combined_text)
                media_signals, _ = evaluate(child_id, media_type, str(moderation_media_local))
        else:
            if text_needed:
                text_signals, _ = evaluate(child_id, "TEXT", combined_text)
            if media_needed:
                media_signals, _ = evaluate(child_id, media_type, str(moderation_media_local))

        if combined_text and text_fingerprint and text_signals and text_cache_miss:
            try:
                store_cached_signals("TEXT", text_fingerprint, text_signals)
            except Exception:
                logger.info("Unable to persist text moderation cache for post %s", post_id, exc_info=True)
        if media_fingerprint and media_signals and media_cache_miss:
            try:
                store_cached_signals(media_type, media_fingerprint, media_signals)
            except Exception:
                logger.info("Unable to persist media moderation cache for post %s", post_id, exc_info=True)

        _renew_worker_lease(post_id, worker_exec_token, 300)
        merged = _merge_signals(text_signals, media_signals)
        decision = decide(merged, safety_level(child_id), Config.ADULT_HARD_BLOCK_THRESHOLD)
        event_id = record(child_id, media_type, post_id, merged, decision)

        if decision.action == "BLOCK":
            blocked_row = execute(
                """UPDATE posts
                   SET is_safe=FALSE, moderation_status='BLOCKED', processing_status='BLOCKED',
                       media_path=NULL,
                       safety_score=%s, adult_score=%s, violence_score=%s, weapon_score=%s,
                       toxicity_score=%s, moderation_reason=%s, processing_completed_at=NOW(),
                       processing_lease_token=NULL, processing_lease_expires_at=NULL
                   WHERE post_id=%s AND processing_lease_token=%s
                   RETURNING post_id""",
                (
                    decision.risk,
                    merged["adult_score"] * 100,
                    merged["violence_score"] * 100,
                    merged["weapon_score"] * 100,
                    merged["toxicity_score"] * 100,
                    decision.reason,
                    post_id,
                    worker_exec_token,
                ),
                returning=True,
            )
            if not blocked_row:
                logger.warning("Worker lease expired or stolen during BLOCK for post %s; aborting cleanup", post_id)
                return {"ok": False, "status": "EXPIRED", "error": "lease_lost"}
            parent_notify(child_id, "CONTENT_BLOCKED", decision.reason, "/parent/safety/")
            try:
                from services.push_notifications import notify_child_content_status
                notify_child_content_status(child_id, post_id, "BLOCKED", kind)
            except Exception:
                pass
            if not block_and_cleanup_quarantine(post_id, object_key):
                logger.warning(
                    "Quarantine cleanup incomplete after BLOCK for post %s; durable outbox retry queued",
                    post_id,
                )
            return {"ok": True, "status": "BLOCKED", "reason": decision.reason}

        elif decision.action == "REVIEW":
            review_row = execute(
                """UPDATE posts
                   SET is_safe=FALSE, moderation_status='REVIEW', processing_status='REVIEW',
                       safety_score=%s, adult_score=%s, violence_score=%s, weapon_score=%s,
                       toxicity_score=%s, moderation_reason=%s, processing_completed_at=NOW(),
                       processing_lease_token=NULL, processing_lease_expires_at=NULL
                   WHERE post_id=%s AND processing_lease_token=%s
                   RETURNING post_id""",
                (
                    decision.risk,
                    merged["adult_score"] * 100,
                    merged["violence_score"] * 100,
                    merged["weapon_score"] * 100,
                    merged["toxicity_score"] * 100,
                    decision.reason,
                    post_id,
                    worker_exec_token,
                ),
                returning=True,
            )
            if not review_row:
                logger.warning("Worker lease expired or stolen during REVIEW for post %s; aborting notify", post_id)
                return {"ok": False, "status": "EXPIRED", "error": "lease_lost"}
            parent_notify(
                child_id,
                "REVIEW_REQUIRED",
                "Content is waiting for your review",
                f"/parent/safety/?event={event_id}",
            )
            try:
                from services.push_notifications import notify_parent_safety_event, notify_child_content_status
                pcm = fetch_one("""SELECT p.parent_id, u.full_name
                                   FROM parent_child_map p
                                   JOIN users u ON u.user_id=p.child_id
                                   JOIN users guardian ON guardian.user_id=p.parent_id
                                   WHERE p.child_id=%s
                                     AND p.approved=TRUE
                                     AND p.approval_status='APPROVED'
                                     AND guardian.role='PARENT'
                                     AND guardian.account_status='ACTIVE'
                                   LIMIT 1""", (child_id,))
                if pcm and pcm.get("parent_id"):
                    notify_parent_safety_event(int(pcm["parent_id"]), str(pcm.get("full_name") or "Child"), event_id, "REVIEW")
                notify_child_content_status(child_id, post_id, "REVIEW", kind)
            except Exception:
                pass
            return {"ok": True, "status": "REVIEW", "event_id": event_id}

        else:  # ALLOW
            require_active_lease()
            ext = "mp4" if media_type == "VIDEO" else "jpg"
            media_mime = "video/mp4" if ext == "mp4" else "image/jpeg"
            namespace = "stories" if kind.lower() == "story" else "reels" if kind.lower() == "reel" else "posts"
            published_media_ref = f"uploads/r2/{namespace}/{child_id}/{post_id}_media.{ext}"
            published_poster_ref = None

            if object_storage.enabled():
                # VIDEO bytes were already audio-stripped by _make_video_derivatives
                # (fail-closed); skip upload_file's redundant second strip. All
                # other video callers must leave upload_file's default strip on.
                object_storage.upload_file(
                    str(final_media_local),
                    f"{namespace}/{child_id}/{post_id}_media.{ext}",
                    content_type=media_mime,
                    skip_audio_strip=(media_type == "VIDEO"),
                )
                if final_poster_local and final_poster_local.is_file():
                    published_poster_ref = f"uploads/r2/{namespace}/{child_id}/{post_id}_poster.jpg"
                    object_storage.upload_file(
                        str(final_poster_local), f"{namespace}/{child_id}/{post_id}_poster.jpg", content_type="image/jpeg"
                    )
            else:
                local_pub_dir = Path("uploads") / namespace / str(child_id)
                local_pub_dir.mkdir(parents=True, exist_ok=True)
                perm_media = local_pub_dir / f"{post_id}_media.{ext}"
                shutil.copy2(final_media_local, perm_media)
                published_media_ref = str(perm_media).replace("\\", "/")

                published_poster_ref = None
                if final_poster_local and final_poster_local.is_file():
                    perm_poster = local_pub_dir / f"{post_id}_poster.jpg"
                    shutil.copy2(final_poster_local, perm_poster)
                    published_poster_ref = str(perm_poster).replace("\\", "/")

            try:
                require_active_lease()
            except RuntimeError:
                failed_orphans = delete_orphaned_media_refs(
                    (published_media_ref, published_poster_ref), context="lease_lost_before_commit"
                )
                if failed_orphans:
                    logger.warning(
                        "Lease lost for post %s; %d orphaned publication object(s) queued for retry: %s",
                        post_id,
                        len(failed_orphans),
                        [r[:64] for r in failed_orphans],
                    )
                raise

            allowed_row = execute(
                """UPDATE posts
                   SET media_path=%s, poster_path=%s, is_safe=TRUE,
                       moderation_status='ALLOWED', processing_status='ALLOWED',
                       safety_score=%s, adult_score=%s, violence_score=%s, weapon_score=%s,
                       toxicity_score=%s, moderation_reason=%s, processing_completed_at=NOW(),
                       processing_lease_token=NULL, processing_lease_expires_at=NULL
                   WHERE post_id=%s AND processing_lease_token=%s
                   RETURNING post_id""",
                (
                    published_media_ref,
                    published_poster_ref,
                    decision.risk,
                    merged["adult_score"] * 100,
                    merged["violence_score"] * 100,
                    merged["weapon_score"] * 100,
                    merged["toxicity_score"] * 100,
                    decision.reason,
                    post_id,
                    worker_exec_token,
                ),
                returning=True,
            )
            if not allowed_row:
                logger.warning("Worker lease expired or stolen during ALLOW for post %s; aborting publication", post_id)
                failed_orphans = delete_orphaned_media_refs(
                    (published_media_ref, published_poster_ref), context="lease_lost_after_publish"
                )
                if failed_orphans:
                    logger.warning(
                        "Lease stolen for post %s; %d orphaned publication object(s) queued for retry: %s",
                        post_id,
                        len(failed_orphans),
                        [r[:64] for r in failed_orphans],
                    )
                return {"ok": False, "status": "EXPIRED", "error": "lease_lost"}
            if media_type == "VIDEO":
                try:
                    from services.video_delivery import ingest_post_video
                    ingest_post_video(
                        post_id=post_id,
                        child_id=child_id,
                        source_r2_key=object_key,
                        published_ref=published_media_ref,
                        poster_ref=published_poster_ref,
                        local_file=final_media_local,
                    )
                except Exception:
                    pass

            from services.publication_lifecycle import refresh_publication_visibility
            refresh_publication_visibility(post_id, child_id, is_reel=bool(post.get("is_reel")))
            _notify_approved_followers(post_id, child_id, kind)
            try:
                from services.push_notifications import notify_child_content_status
                notify_child_content_status(child_id, post_id, "ALLOWED", kind)
            except Exception:
                pass
            if not block_and_cleanup_quarantine(post_id, object_key):
                logger.warning(
                    "Quarantine cleanup incomplete after ALLOW for post %s; durable outbox retry queued",
                    post_id,
                )
            return {
                "ok": True,
                "status": "ALLOWED",
                "media_path": published_media_ref,
                "poster_path": published_poster_ref,
            }

    except Exception as exc:
        execute(
            """UPDATE posts
               SET processing_status='FAILED', processing_error=%s, processing_completed_at=NOW(),
                   processing_lease_token=NULL, processing_lease_expires_at=NULL
               WHERE post_id=%s AND processing_lease_token=%s""",
            (str(exc), post_id, worker_exec_token),
        )
        return {"ok": False, "error": str(exc)}

    finally:
        lease_stop.set()
        lease_thread.join(timeout=2)
        shutil.rmtree(temp_dir, ignore_errors=True)


def sanitize_and_promote_media(
    post_id: int, child_id: int, object_key: str, kind: str, media_type: str
) -> tuple[str, str | None]:
    """Sanitize quarantine media and promote bytes to the published namespace.

    Fails closed: raises RuntimeError on any sanitization or storage failure so
    unmoderated or unsanitized bytes are never published.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix=f"littlenet_promote_{post_id}_"))
    try:
        source_local = temp_dir / "quarantine_source"
        if object_storage.enabled():
            object_storage.download_file(object_key, source_local)
        else:
            candidate = Path(object_key)
            if not candidate.is_file():
                for mock_candidate in Path("uploads/mock_quarantine").rglob("*"):
                    if mock_candidate.is_file() and object_key in str(mock_candidate):
                        candidate = mock_candidate
                        break
            if candidate.is_file():
                shutil.copy2(candidate, source_local)

        if not source_local.is_file() or source_local.stat().st_size <= 0:
            raise RuntimeError("quarantine_media_missing_or_empty")

        final_media_local = source_local
        final_poster_local = None

        ext = "mp4" if media_type.upper() == "VIDEO" else "jpg"
        media_mime = "video/mp4" if ext == "mp4" else "image/jpeg"

        if media_type.upper() == "VIDEO":
            final_media_local, final_poster_local = _make_video_derivatives(source_local, temp_dir)
        elif media_type.upper() == "IMAGE":
            try:
                from PIL import Image, ImageOps

                with Image.open(source_local) as img:
                    img = ImageOps.exif_transpose(img)
                    clean_img_path = temp_dir / "clean_image.jpg"
                    img.convert("RGB").save(clean_img_path, format="JPEG", quality=92, optimize=True)
                    if not clean_img_path.is_file() or clean_img_path.stat().st_size == 0:
                        raise RuntimeError("clean_image_empty")
                    final_media_local = clean_img_path
            except Exception as exc:
                raise RuntimeError(f"image_sanitization_failed: {exc}") from exc

        namespace = "stories" if kind.lower() == "story" else "reels" if kind.lower() == "reel" else "posts"

        if object_storage.enabled():
            published_media_ref = f"uploads/r2/{namespace}/{child_id}/{post_id}_media.{ext}"
            published_poster_ref = None
            # VIDEO bytes were already audio-stripped by _make_video_derivatives
            # (fail-closed); skip upload_file's redundant second strip. All
            # other video callers must leave upload_file's default strip on.
            object_storage.upload_file(
                str(final_media_local),
                f"{namespace}/{child_id}/{post_id}_media.{ext}",
                content_type=media_mime,
                skip_audio_strip=(ext == "mp4"),
            )
            if final_poster_local and final_poster_local.is_file():
                published_poster_ref = f"uploads/r2/{namespace}/{child_id}/{post_id}_poster.jpg"
                object_storage.upload_file(
                    str(final_poster_local), f"{namespace}/{child_id}/{post_id}_poster.jpg", content_type="image/jpeg"
                )
            # Caller deletes quarantine object_key AFTER database state commits!
        else:
            # Local persistent storage: copy into permanent local directory
            local_pub_dir = Path("uploads") / namespace / str(child_id)
            local_pub_dir.mkdir(parents=True, exist_ok=True)
            perm_media = local_pub_dir / f"{post_id}_media.{ext}"
            shutil.copy2(final_media_local, perm_media)
            published_media_ref = str(perm_media).replace("\\", "/")

            published_poster_ref = None
            if final_poster_local and final_poster_local.is_file():
                perm_poster = local_pub_dir / f"{post_id}_poster.jpg"
                shutil.copy2(final_poster_local, perm_poster)
                published_poster_ref = str(perm_poster).replace("\\", "/")

        return published_media_ref, published_poster_ref
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def block_and_cleanup_quarantine(post_id: int, object_key: str | None) -> bool:
    """Delete and invalidate quarantine media after moderation BLOCK or ALLOW.

    Called only after the database state commits. Returns True when the
    quarantine object was fully cleaned, False when any part failed. Failures
    are logged with the object-key prefix as context (never secrets or
    credential-bearing URLs) and the R2 reference is handed to the durable
    media-delete outbox for retry — nothing is silently swallowed.
    """
    if not object_key:
        return True
    cleaned = True
    key_prefix = str(object_key)[:64]
    if object_storage.enabled():
        try:
            object_storage.delete_reference(object_key)
        except (RuntimeError, OSError) as exc:
            logger.warning(
                "Quarantine R2 delete failed for post %s ref_prefix=%s: %s: %s",
                post_id,
                key_prefix,
                type(exc).__name__,
                exc,
            )
            cleaned = False
        except Exception as exc:
            logger.warning(
                "Quarantine R2 delete failed unexpectedly for post %s ref_prefix=%s: %s: %s",
                post_id,
                key_prefix,
                type(exc).__name__,
                exc,
            )
            cleaned = False
    try:
        for p in Path("uploads/mock_quarantine").rglob("*"):
            if p.is_file() and object_key in str(p):
                p.unlink(missing_ok=True)
    except (OSError, RuntimeError) as exc:
        logger.warning(
            "Mock quarantine sweep failed for post %s ref_prefix=%s: %s: %s",
            post_id,
            key_prefix,
            type(exc).__name__,
            exc,
        )
        cleaned = False
    except Exception as exc:
        logger.warning(
            "Mock quarantine sweep failed unexpectedly for post %s ref_prefix=%s: %s: %s",
            post_id,
            key_prefix,
            type(exc).__name__,
            exc,
        )
        cleaned = False

    if not cleaned:
        try:
            from services.media_outbox import enqueue_delete

            enqueue_delete(object_key, "posts", post_id)
        except Exception as exc:
            logger.exception(
                "Failed to enqueue quarantine delete for post %s ref_prefix=%s: %s: %s",
                post_id,
                key_prefix,
                type(exc).__name__,
                exc,
            )

    return cleaned


def claim_media_job_lease(
    post_id: int,
    lease_seconds: int = 300,
    force: bool = False,
    is_reap: bool = False,
) -> tuple[bool, str | None, dict[str, Any] | None]:
    """Atomically acquire or renew a DB-backed lease for a media processing attempt.

    Returns (acquired: bool, lease_token: str | None, post_data: dict | None).
    Guarantees:
    - Never claims terminal states ('ALLOWED', 'BLOCKED', 'FAILED').
    - Exactly one caller wins via atomic conditional UPDATE ... RETURNING.
    - If another active lease exists and is not expired, returns (False, None, post).
    """
    post = fetch_one(
        """SELECT post_id, child_id, source_media_path, is_reel, is_story,
                  processing_status, moderation_status, processing_attempts,
                  max_processing_attempts, last_attempt_at, processing_lease_token,
                  processing_lease_expires_at
           FROM posts WHERE post_id=%s""",
        (post_id,),
    )
    if not post:
        return False, None, None

    if post.get("processing_status") in ("ALLOWED", "BLOCKED"):
        return False, None, dict(post)

    attempts = int(post.get("processing_attempts") or 0)
    max_attempts = int(post.get("max_processing_attempts") or 3)

    if attempts >= max_attempts and not force:
        execute(
            """UPDATE posts
               SET processing_status='FAILED', processing_error='max_attempts_exceeded',
                   processing_completed_at=NOW(), processing_lease_token=NULL,
                   processing_lease_expires_at=NULL
               WHERE post_id=%s AND processing_status NOT IN ('ALLOWED', 'BLOCKED', 'FAILED')""",
            (post_id,),
        )
        post_dict = dict(post)
        post_dict["processing_status"] = "FAILED"
        return False, None, post_dict

    last_att = post.get("last_attempt_at")
    if last_att and not force and not is_reap:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        if hasattr(last_att, "tzinfo") and last_att.tzinfo is None:
            last_att = last_att.replace(tzinfo=timezone.utc)
        backoff_sec = min(300, (2 ** max(0, attempts - 1)) * 5)
        elapsed = (now - last_att).total_seconds()
        if elapsed < backoff_sec:
            rem = int(backoff_sec - elapsed)
            post_dict = dict(post)
            post_dict["retry_after_seconds"] = rem
            return False, None, post_dict

    new_token = uuid.uuid4().hex
    claimed_row = execute(
        """UPDATE posts
           SET processing_status='PROCESSING',
               processing_lease_token=%s,
               processing_lease_expires_at=NOW() + INTERVAL '300 seconds',
               processing_started_at=COALESCE(processing_started_at, NOW()),
               processing_attempts=processing_attempts + 1,
               last_attempt_at=NOW(),
               processing_error=NULL
           WHERE post_id=%s
             AND processing_status NOT IN ('ALLOWED', 'BLOCKED', 'FAILED')
             AND (processing_attempts < max_processing_attempts OR %s=TRUE)
             AND (processing_lease_token IS NULL OR processing_lease_expires_at < NOW() OR %s=TRUE)
           RETURNING post_id, child_id, source_media_path, is_reel, is_story,
                     processing_status, moderation_status, processing_attempts,
                     max_processing_attempts, processing_lease_token""",
        (new_token, post_id, force, force),
        returning=True,
    )
    if claimed_row:
        return True, new_token, dict(claimed_row)
    latest = fetch_one("SELECT * FROM posts WHERE post_id=%s", (post_id,))
    return False, None, dict(latest) if latest else None


def redrive_media_job(post_id: int, force: bool = False) -> dict[str, Any]:
    """Redrive an individual stalled or failed media processing job with bounded attempts and backoff."""
    acquired, lease_token, post = claim_media_job_lease(post_id, lease_seconds=300, force=force)
    if not acquired:
        if not post:
            return {"ok": False, "error": "post_not_found"}
        if post.get("processing_status") in ("ALLOWED", "BLOCKED"):
            return {"ok": True, "status": post["processing_status"], "idempotent": True}
        if post.get("processing_status") == "FAILED":
            return {
                "ok": False,
                "error": "max_attempts_exceeded",
                "status": "FAILED",
                "attempts": post.get("processing_attempts", 0),
                "max_attempts": post.get("max_processing_attempts", 3),
            }
        if "retry_after_seconds" in post:
            return {
                "ok": False,
                "error": "backoff_in_progress",
                "retry_after_seconds": post["retry_after_seconds"],
                "attempts": post.get("processing_attempts", 0),
            }
        return {
            "ok": False,
            "error": "already_claimed_or_in_progress",
            "status": post.get("processing_status", "PROCESSING"),
        }

    kind = "reel" if post.get("is_reel") else ("story" if post.get("is_story") else "post")
    object_key = post.get("source_media_path")
    if not object_key:
        return {"ok": False, "error": "missing_source_media_path"}

    from services.job_queue import enqueue_media_job

    try:
        job_id = enqueue_media_job(
            post_id, int(post["child_id"]), object_key, kind, lease_token=lease_token
        )
        execute("UPDATE posts SET job_id=%s WHERE post_id=%s", (job_id, post_id))
        return {
            "ok": True,
            "post_id": post_id,
            "job_id": job_id,
            "status": "PROCESSING",
            "attempts": post.get("processing_attempts", 1),
        }
    except Exception as exc:
        execute(
            """UPDATE posts
               SET processing_status='UPLOADED',
                   processing_lease_token=NULL,
                   processing_lease_expires_at=NULL,
                   processing_error=%s
               WHERE post_id=%s""",
            (f"redrive_dispatch_failed: {exc}", post_id),
        )
        return {"ok": False, "error": "job_dispatch_failed", "detail": str(exc)}


def reap_stale_media_jobs(stale_seconds: int = 300) -> dict[str, Any]:
    """Find posts stuck in UPLOADED or PROCESSING longer than stale_seconds, respect max attempts, and redrive them."""
    from datetime import datetime, timedelta, timezone

    stale_seconds = max(30, min(int(stale_seconds), 86400))
    threshold = datetime.now(timezone.utc) - timedelta(seconds=stale_seconds)

    stale_posts = fetch_all(
        """SELECT post_id, child_id, source_media_path, is_reel, is_story,
                  processing_status, processing_started_at, created_at,
                  processing_attempts, max_processing_attempts
           FROM posts
           WHERE processing_status IN ('UPLOADED', 'PROCESSING')
             AND (processing_lease_token IS NULL OR processing_lease_expires_at < NOW())
             AND (processing_started_at < %s OR (processing_started_at IS NULL AND created_at < %s))
           ORDER BY post_id ASC LIMIT 50""",
        (threshold, threshold),
    )

    redriven = []
    failed = []
    from services.job_queue import enqueue_media_job

    for p in (stale_posts or []):
        post_id = int(p["post_id"])
        child_id = int(p["child_id"])
        object_key = p["source_media_path"]
        attempts = int(p.get("processing_attempts") or 0)
        max_attempts = int(p.get("max_processing_attempts") or 3)

        if attempts >= max_attempts:
            transitioned = execute_count(
                """UPDATE posts
                   SET processing_status='FAILED', processing_error='max_attempts_exceeded_stale_reap',
                       processing_completed_at=NOW(), processing_lease_token=NULL,
                       processing_lease_expires_at=NULL
                   WHERE post_id=%s AND processing_status NOT IN ('ALLOWED', 'BLOCKED', 'FAILED')""",
                (post_id,),
            )
            entry = {"post_id": post_id, "error": "max_attempts_exceeded"}
            if transitioned:
                # Terminal FAILED: the quarantine object can never be consumed
                # now, so delete it (outbox-backed on R2 failure). Skipped when
                # another worker already transitioned the row.
                entry["quarantine_cleaned"] = block_and_cleanup_quarantine(post_id, object_key)
            failed.append(entry)
            continue

        if not object_key:
            continue

        acquired, lease_token, post_data = claim_media_job_lease(post_id, lease_seconds=300, is_reap=True)
        if not acquired or not post_data:
            continue

        kind = "reel" if p.get("is_reel") else ("story" if p.get("is_story") else "post")
        try:
            job_id = enqueue_media_job(post_id, child_id, object_key, kind, lease_token=lease_token)
            execute("UPDATE posts SET job_id=%s WHERE post_id=%s", (job_id, post_id))
            redriven.append({"post_id": post_id, "job_id": job_id, "attempts": post_data.get("processing_attempts", attempts + 1)})
        except Exception as exc:
            execute(
                """UPDATE posts
                   SET processing_status='UPLOADED',
                       processing_lease_token=NULL,
                       processing_lease_expires_at=NULL,
                       processing_error=%s
                   WHERE post_id=%s""",
                (f"reap_dispatch_failed: {exc}", post_id),
            )
            failed.append({"post_id": post_id, "error": str(exc)})

    return {"ok": True, "count": len(redriven), "redriven": redriven, "failed": failed}


def reconcile_abandoned_upload_sessions(stale_seconds: int = 86400) -> dict[str, Any]:
    """Bounded reconciliation of abandoned direct-upload sessions.

    A client may PUT bytes to a quarantine R2 object via the presigned upload
    URL and never call ``/complete`` — or the session expires first. Those
    objects have no post row, so the media-job reaper can never see them.
    This sweeps the bounded ``upload_sessions`` table (LIMIT 50, TTL-gated)
    for sessions still PENDING/EXPIRED long after ``expires_at``, deletes the
    quarantine object (durable outbox on R2 failure), removes local
    mock-quarantine files, and marks the session CANCELLED so it is never
    swept twice. The DB is the source of truth: no R2 prefix listings, no
    unbounded scans.
    """
    from datetime import datetime, timedelta, timezone

    stale_seconds = max(3600, min(int(stale_seconds), 7 * 86400))
    threshold = datetime.now(timezone.utc) - timedelta(seconds=stale_seconds)

    rows = fetch_all(
        """SELECT upload_id, child_id, object_key, extension
           FROM upload_sessions
           WHERE status IN ('PENDING', 'EXPIRED')
             AND expires_at < %s
           ORDER BY expires_at ASC LIMIT 50""",
        (threshold,),
    )

    cleaned: list[str] = []
    failed: list[dict[str, Any]] = []
    r2_enabled = object_storage.enabled()

    for row in rows or []:
        upload_id = str(row["upload_id"])
        child_id = row["child_id"]
        object_key = str(row["object_key"] or "")
        row_failed: str | None = None

        if object_key and r2_enabled and object_storage.is_reference(object_key):
            try:
                object_storage.delete_reference(object_key)
            except (RuntimeError, OSError) as exc:
                logger.warning(
                    "Abandoned upload cleanup: R2 delete failed upload_id=%s ref_prefix=%s: %s: %s",
                    upload_id,
                    object_key[:64],
                    type(exc).__name__,
                    exc,
                )
                row_failed = f"r2_delete_failed:{type(exc).__name__}"
                try:
                    from services.media_outbox import enqueue_delete

                    enqueue_delete(object_key, source_table="abandoned_upload_session", source_id=upload_id)
                except Exception:
                    logger.exception(
                        "Abandoned upload cleanup: outbox enqueue failed upload_id=%s ref_prefix=%s",
                        upload_id,
                        object_key[:64],
                    )
            except Exception as exc:
                logger.warning(
                    "Abandoned upload cleanup: R2 delete failed unexpectedly upload_id=%s ref_prefix=%s: %s: %s",
                    upload_id,
                    object_key[:64],
                    type(exc).__name__,
                    exc,
                )
                row_failed = f"r2_delete_failed:{type(exc).__name__}"

        try:
            mock_dir = Path("uploads/mock_quarantine") / str(child_id) / upload_id
            if mock_dir.is_dir():
                shutil.rmtree(mock_dir, ignore_errors=True)
        except (OSError, RuntimeError) as exc:
            logger.warning(
                "Abandoned upload cleanup: mock quarantine sweep failed upload_id=%s: %s: %s",
                upload_id,
                type(exc).__name__,
                exc,
            )
            row_failed = row_failed or f"mock_sweep_failed:{type(exc).__name__}"

        try:
            execute_count(
                """UPDATE upload_sessions SET status='CANCELLED'
                   WHERE upload_id=%s AND status IN ('PENDING', 'EXPIRED')""",
                (upload_id,),
            )
        except Exception as exc:
            logger.exception(
                "Abandoned upload cleanup: failed to mark session CANCELLED upload_id=%s: %s: %s",
                upload_id,
                type(exc).__name__,
                exc,
            )
            row_failed = row_failed or f"mark_cancelled_failed:{type(exc).__name__}"

        if row_failed:
            failed.append({"upload_id": upload_id, "error": row_failed})
        else:
            cleaned.append(upload_id)

    return {"ok": True, "checked": len(rows or []), "cleaned": cleaned, "failed": failed}
