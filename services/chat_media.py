"""Fail-closed moderation and promotion for child-to-child chat media."""
from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from config import Config
from database.connection import execute, fetch_all
from safety.moderation_service import evaluate, record
from services import object_storage
from services.media_processor import sanitize_and_promote_media

logger = logging.getLogger(__name__)


def _cleanup_quarantine(reference: str | None, local_path: str | None = None, *, message_id: int | None = None) -> None:
    if reference:
        try:
            if object_storage.is_reference(reference):
                object_storage.delete_reference(reference)
            else:
                Path(reference).unlink(missing_ok=True)
        except Exception:
            logger.exception("chat quarantine cleanup failed ref_prefix=%s", str(reference)[:64])
            try:
                from services.media_outbox import enqueue_delete
                enqueue_delete(reference, "child_messages", message_id)
            except Exception:
                logger.exception("failed to enqueue chat quarantine cleanup ref_prefix=%s", str(reference)[:64])
    if local_path:
        try:
            Path(local_path).unlink(missing_ok=True)
        except Exception:
            logger.exception("local chat quarantine cleanup failed path=%s", str(local_path)[:120])


def _download_for_moderation(reference: str, local_source_path: str | None = None) -> tuple[Path, Path]:
    temp_dir = Path(tempfile.mkdtemp(prefix="littlemuse_chat_media_"))
    source = temp_dir / "source"
    try:
        if object_storage.enabled() and object_storage.is_reference(reference):
            object_storage.download_file(reference, source)
        elif local_source_path and Path(local_source_path).is_file():
            shutil.copy2(local_source_path, source)
        else:
            candidate = Path(reference)
            if candidate.is_file():
                shutil.copy2(candidate, source)
        if not source.is_file() or source.stat().st_size <= 0:
            raise RuntimeError("chat_media_missing_or_empty")
        return temp_dir, source
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def moderate_chat_media(
    *,
    message_id: int,
    child_id: int,
    media_type: str,
    quarantine_ref: str,
    local_source_path: str | None = None,
) -> dict:
    """Moderate one chat image/video and promote only ALLOW media.

    REVIEW deliberately keeps the quarantine object private for the sender and
    guardian review. BLOCK deletes it. ALLOW sanitizes/promotes into chat/.
    """
    media_type = str(media_type or "").upper()
    if media_type not in {"IMAGE", "VIDEO"}:
        return {"action": "BLOCK", "reason": "unsupported_chat_media_type", "media_path": None, "poster_path": None}

    temp_dir, source = _download_for_moderation(quarantine_ref, local_source_path)
    try:
        signals, decision = evaluate(child_id, media_type, str(source))
        event_id = record(child_id, "MESSAGE", message_id, signals, decision)

        if decision.action == "ALLOW":
            source_for_promotion = quarantine_ref if object_storage.is_reference(quarantine_ref) else str(source)
            media_ref, poster_ref = sanitize_and_promote_media(
                message_id,
                child_id,
                source_for_promotion,
                "chat",
                media_type,
            )
            _cleanup_quarantine(quarantine_ref, local_source_path, message_id=message_id)
            return {
                "action": "ALLOW",
                "reason": decision.reason,
                "media_path": media_ref,
                "poster_path": poster_ref,
                "event_id": event_id,
            }

        if decision.action == "BLOCK":
            _cleanup_quarantine(quarantine_ref, local_source_path, message_id=message_id)
            return {
                "action": "BLOCK",
                "reason": decision.reason,
                "media_path": None,
                "poster_path": None,
                "event_id": event_id,
            }

        # REVIEW: leave the quarantine object in place. It is protected by
        # mobile media authorization and is never visible to the receiver.
        return {
            "action": "REVIEW",
            "reason": decision.reason,
            "media_path": quarantine_ref,
            "poster_path": None,
            "event_id": event_id,
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def promote_reviewed_chat_media(
    *,
    message_id: int,
    child_id: int,
    media_type: str,
    quarantine_ref: str,
) -> tuple[str, str | None]:
    if media_type not in {"IMAGE", "VIDEO"}:
        raise RuntimeError("unsupported_chat_media_type")
    media_ref, poster_ref = sanitize_and_promote_media(
        message_id,
        child_id,
        quarantine_ref,
        "chat",
        media_type,
    )
    _cleanup_quarantine(quarantine_ref, message_id=message_id)
    return media_ref, poster_ref


def block_reviewed_chat_media(*, message_id: int, quarantine_ref: str | None) -> None:
    _cleanup_quarantine(quarantine_ref, message_id=message_id)



def reconcile_abandoned_chat_upload_sessions(limit: int = 50) -> dict:
    """Delete expired chat quarantine uploads that never reached completion.

    REVIEW sessions are intentionally excluded: their bytes are still needed
    for guardian moderation. Only expired PENDING/EXPIRED sessions are swept.
    """
    try:
        safe_limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        safe_limit = 50

    rows = fetch_all(
        """SELECT upload_id,child_id,object_key,status
           FROM chat_upload_sessions
           WHERE status IN ('PENDING','EXPIRED')
             AND expires_at < NOW()
           ORDER BY expires_at ASC
           LIMIT %s""",
        (safe_limit,),
    ) or []

    cleaned = 0
    failed = 0
    for row in rows:
        upload_id = str(row["upload_id"])
        ref = row.get("object_key")
        local_dir = Path("uploads/mock_chat_quarantine") / str(row["child_id"]) / upload_id
        try:
            _cleanup_quarantine(ref, message_id=None)
            shutil.rmtree(local_dir, ignore_errors=True)
            execute(
                """UPDATE chat_upload_sessions
                   SET status='EXPIRED',consumed_at=COALESCE(consumed_at,NOW())
                   WHERE upload_id=%s AND status IN ('PENDING','EXPIRED')""",
                (upload_id,),
            )
            cleaned += 1
        except Exception:
            logger.exception("failed to reconcile abandoned chat upload=%s", upload_id)
            failed += 1

    return {"ok": failed == 0, "scanned": len(rows), "cleaned": cleaned, "failed": failed}
