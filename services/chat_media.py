"""Safe direct-upload completion for child-to-child chat images.

Bytes are uploaded directly to private quarantine. This service strips EXIF/GPS,
runs the same image moderation evidence/policy used by posts, and only then
publishes a private message-media reference.
"""
from __future__ import annotations

import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import Config
from database.connection import execute, fetch_one
from safety.moderation_service import evaluate, record, safety_level
from safety.policy import decide
from services import object_storage
from services.controls import feature_allowed
from services.media_processor import _make_image_moderation_proxy, _merge_signals
from services.moderation_cache import cached_or_none_for_file, store_cached_signals
from services.social import can_interact, notify, parent_notify


def _mock_source(session_row: dict[str, Any]) -> Path:
    return (
        Path("uploads/mock_quarantine")
        / str(session_row["child_id"])
        / str(session_row["upload_id"])
        / f"source.{session_row['extension']}"
    )


def _verify_upload_object(session_row: dict[str, Any]) -> tuple[bool, str | None]:
    if object_storage.enabled():
        meta = object_storage.head_object(session_row["object_key"])
        if not meta or int(meta.get("content_length", 0) or 0) <= 0:
            return False, "media_object_missing_in_quarantine"
        actual = int(meta["content_length"])
        expected = int(session_row["expected_size_bytes"])
        if actual != expected:
            return False, "media_size_mismatch"
        actual_mime = str(meta.get("content_type") or "").strip().lower()
        expected_mime = str(session_row.get("mime_type") or "").strip().lower()
        if actual_mime and expected_mime and actual_mime != expected_mime:
            return False, "media_mime_mismatch"
        return True, None

    source = _mock_source(session_row)
    if not source.is_file() or source.stat().st_size <= 0:
        return False, "media_object_missing_in_quarantine"
    if source.stat().st_size != int(session_row["expected_size_bytes"]):
        return False, "media_size_mismatch"
    return True, None


def _materialize_source(session_row: dict[str, Any], target: Path) -> None:
    if object_storage.enabled():
        object_storage.download_file(session_row["object_key"], target)
        return
    source = _mock_source(session_row)
    shutil.copy2(source, target)


def _sanitize_image(source: Path, target: Path) -> None:
    from PIL import Image, ImageOps

    with Image.open(source) as img:
        clean = ImageOps.exif_transpose(img).convert("RGB")
        clean.save(target, format="JPEG", quality=92, optimize=True)
    if not target.is_file() or target.stat().st_size <= 0:
        raise RuntimeError("clean_image_empty")


def _moderate_image(child_id: int, clean_path: Path, temp_dir: Path):
    moderation_path = _make_image_moderation_proxy(clean_path, temp_dir)
    fingerprint = None
    signals: dict[str, Any] = {}
    cache_miss = False
    try:
        fingerprint, signals = cached_or_none_for_file("IMAGE", moderation_path)
    except Exception:
        signals = {}

    if not signals:
        cache_miss = True
        try:
            from services.modal_image_moderation import (
                allow_gpu_fallback,
                enabled as modal_image_cpu_enabled,
                moderate_image_upload,
            )

            if modal_image_cpu_enabled():
                try:
                    result = moderate_image_upload(
                        str(moderation_path),
                        "",
                        run_text=False,
                        run_media=True,
                    )
                    signals = result.get("media_signals") or {}
                except Exception:
                    if not allow_gpu_fallback():
                        signals = {
                            "category": "IMAGE",
                            "total_safety_failure": True,
                            "errors": ["modal_cpu_image_moderation_unavailable"],
                        }
        except Exception:
            signals = {}

    if not signals:
        signals, _ = evaluate(child_id, "IMAGE", str(moderation_path))

    if fingerprint and signals and cache_miss:
        try:
            store_cached_signals("IMAGE", fingerprint, signals)
        except Exception:
            pass

    merged = _merge_signals({}, signals)
    decision = decide(merged, safety_level(child_id), Config.ADULT_HARD_BLOCK_THRESHOLD)
    return merged, decision


def _publish_image(clean_path: Path, conversation_id: int, message_id: int) -> str:
    if object_storage.enabled():
        return object_storage.upload_file(
            str(clean_path),
            f"messages/{conversation_id}/{message_id}.jpg",
            content_type="image/jpeg",
        )
    dest = Path("uploads/messages") / str(conversation_id) / f"{message_id}.jpg"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(clean_path, dest)
    return str(dest).replace("\\", "/")


def _cleanup_quarantine(session_row: dict[str, Any]) -> None:
    try:
        if object_storage.is_reference(session_row["object_key"]) and object_storage.enabled():
            object_storage.delete_reference(session_row["object_key"])
        else:
            source = _mock_source(session_row)
            source.unlink(missing_ok=True)
            try:
                source.parent.rmdir()
            except OSError:
                pass
    except Exception:
        try:
            from services.media_outbox import enqueue_delete

            enqueue_delete(
                str(session_row["object_key"]),
                source_table="chat_image_quarantine",
            )
        except Exception:
            pass


def complete_chat_image_upload(child_id: int, upload_id: str) -> tuple[dict[str, Any], int]:
    session_row = fetch_one(
        "SELECT * FROM upload_sessions WHERE upload_id=%s",
        (upload_id,),
    )
    if not session_row:
        return {"error": "upload_session_not_found"}, 404
    if int(session_row["child_id"]) != int(child_id):
        return {"error": "forbidden_upload_owner_mismatch"}, 403
    if str(session_row.get("kind") or "").upper() != "MESSAGE":
        return {"error": "invalid_upload_kind"}, 400
    if str(session_row.get("media_type") or "").upper() != "IMAGE":
        return {"error": "invalid_message_media_type"}, 400

    peer_id = int(session_row.get("target_id") or 0)
    if not peer_id or not feature_allowed(child_id, "messaging") or not feature_allowed(peer_id, "messaging"):
        return {"error": "disabled_by_parent", "feature": "messaging"}, 403
    if not can_interact(child_id, peer_id):
        return {"error": "approved_connection_required"}, 403

    existing = fetch_one(
        """SELECT child_message_id,conversation_id,moderation_status,media_path
           FROM child_messages WHERE upload_id=%s""",
        (upload_id,),
    )
    if session_row.get("status") == "CONSUMED" and existing:
        return {
            "ok": True,
            "message_id": int(existing["child_message_id"]),
            "status": existing["moderation_status"],
            "idempotent": True,
        }, 200

    exp = session_row.get("expires_at")
    if exp:
        now = datetime.now(timezone.utc)
        if getattr(exp, "tzinfo", None) is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < now:
            execute("UPDATE upload_sessions SET status='EXPIRED' WHERE upload_id=%s", (upload_id,))
            return {"error": "upload_session_expired"}, 400

    ok, upload_error = _verify_upload_object(session_row)
    if not ok:
        return {"error": upload_error}, 400

    from childMessage.service import conversation

    conversation_id = conversation(child_id, peer_id)
    if not conversation_id:
        return {"error": "approved_connection_required"}, 403

    created = execute(
        """INSERT INTO child_messages(
               conversation_id,sender_child_id,receiver_child_id,message_type,
               message_text,media_path,upload_id,moderation_status
           ) VALUES(%s,%s,%s,'IMAGE','Photo',NULL,%s,'REVIEW')
           ON CONFLICT(upload_id) DO NOTHING
           RETURNING child_message_id""",
        (conversation_id, child_id, peer_id, upload_id),
        returning=True,
    )
    if created:
        message_id = int(created["child_message_id"])
    else:
        row = fetch_one("SELECT child_message_id FROM child_messages WHERE upload_id=%s", (upload_id,))
        if not row:
            return {"error": "message_creation_failed"}, 500
        message_id = int(row["child_message_id"])

    temp_dir = Path(tempfile.mkdtemp(prefix=f"littlenet_chat_{message_id}_"))
    source = temp_dir / f"source.{session_row['extension']}"
    clean = temp_dir / "clean.jpg"
    published_ref: str | None = None
    try:
        _materialize_source(session_row, source)
        _sanitize_image(source, clean)
        merged, decision = _moderate_image(child_id, clean, temp_dir)
        event_id = record(child_id, "IMAGE", message_id, merged, decision)

        if decision.action == "BLOCK":
            execute(
                """UPDATE child_messages
                   SET moderation_status='BLOCKED',media_path=NULL
                   WHERE child_message_id=%s""",
                (message_id,),
            )
            execute(
                "UPDATE upload_sessions SET status='CONSUMED',consumed_at=NOW() WHERE upload_id=%s",
                (upload_id,),
            )
            parent_notify(child_id, "MESSAGE_BLOCKED", decision.reason, "/parent/safety/")
            _cleanup_quarantine(session_row)
            return {
                "blocked": True,
                "error": "message_image_blocked",
                "reason": decision.reason,
                "message_id": message_id,
            }, 400

        published_ref = _publish_image(clean, int(conversation_id), message_id)
        status = "REVIEW" if decision.action == "REVIEW" else "ALLOWED"
        execute(
            """UPDATE child_messages
               SET moderation_status=%s,media_path=%s
               WHERE child_message_id=%s""",
            (status, published_ref, message_id),
        )
        execute(
            "UPDATE upload_sessions SET status='CONSUMED',consumed_at=NOW() WHERE upload_id=%s",
            (upload_id,),
        )

        if status == "REVIEW":
            parent_notify(
                child_id,
                "REVIEW_REQUIRED",
                "A photo message needs safety review",
                f"/parent/safety/?event={event_id}",
            )
        else:
            sender = fetch_one("SELECT full_name,username FROM users WHERE user_id=%s", (child_id,)) or {}
            sender_name = sender.get("full_name") or sender.get("username") or "A friend"
            notify(peer_id, "MESSAGE", f"{sender_name} sent you a photo", f"/chat/{child_id}/", child_id)
            try:
                from services.push_notifications import notify_new_chat_message

                notify_new_chat_message(peer_id, sender_name, int(conversation_id))
            except Exception:
                pass

        _cleanup_quarantine(session_row)
        return {
            "ok": True,
            "message_id": message_id,
            "status": status,
        }, 200
    except Exception:
        if published_ref:
            try:
                if object_storage.is_reference(published_ref):
                    object_storage.delete_reference(published_ref)
                else:
                    Path(published_ref).unlink(missing_ok=True)
            except Exception:
                pass
        # Leave REVIEW and the upload unconsumed so the same upload can be retried.
        raise
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
