"""Cloudflare R2 storage adapter for LittleNet media.

The application keeps moderation files on local ephemeral disk only long enough
for safety analysis. Once content is accepted, callers persist it here before the
corresponding PostgreSQL row is published.
"""
from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from botocore.exceptions import ClientError

R2_REFERENCE_PREFIX = "uploads/r2/"


def _write_key(key: str) -> str:
    prefix = (os.getenv("LITTLENET_R2_WRITE_PREFIX") or "").strip("/")
    return f"{prefix}/{key.lstrip('/')}" if prefix else key.lstrip("/")


def deployment_object_key(key: str) -> str:
    """Return an object key inside the configured deployment write namespace."""
    return _write_key(key)


def new_reference(key: str) -> str:
    """Return a reference inside this deployment's R2 write namespace."""
    return R2_REFERENCE_PREFIX + _write_key(key)


def _enabled() -> bool:
    return all(
        os.getenv(name)
        for name in (
            "R2_ACCOUNT_ID",
            "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
            "R2_BUCKET",
        )
    )


def enabled() -> bool:
    return _enabled()


_UNSET = object()


def _account_id(raw: Any = _UNSET) -> str:
    """Accept either Cloudflare's bare account ID or the copied R2 endpoint URL."""
    if raw is _UNSET:
        raw = os.getenv("R2_ACCOUNT_ID") or ""
    elif raw is None:
        return ""
    raw = str(raw).strip()
    if not raw:
        return ""
    raw = raw.rstrip("/")
    suffix = ".r2.cloudflarestorage.com"
    while "://" in raw:
        _, _, raw = raw.partition("://")
    host = raw.split("/")[0].split("?")[0].split("#")[0].split(":")[0].strip()
    while host.lower().endswith(suffix):
        host = host[: -len(suffix)].rstrip("/")
    return host.strip("/")


def normalize_r2_origin(raw: Any = _UNSET) -> str:
    """Normalize bare account ID, endpoint URL, or host into https://<id>.r2.cloudflarestorage.com."""
    account_id = _account_id(raw)
    if not account_id:
        return ""
    return f"https://{account_id}.r2.cloudflarestorage.com"


def _endpoint_url() -> str:
    origin = normalize_r2_origin()
    if not origin:
        raise RuntimeError("Cloudflare R2 account ID is not configured")
    return origin


def healthcheck() -> dict:
    if not _enabled():
        return {"ok": False, "configured": False, "bucket": os.getenv("R2_BUCKET") or None}
    try:
        _client().head_bucket(Bucket=os.environ["R2_BUCKET"])
        return {
            "ok": True,
            "configured": True,
            "bucket": os.environ["R2_BUCKET"],
            "account_id_format": "normalized",
        }
    except Exception as exc:
        return {
            "ok": False,
            "configured": True,
            "bucket": os.getenv("R2_BUCKET") or None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def is_reference(reference: str | None) -> bool:
    return bool(reference and str(reference).startswith(R2_REFERENCE_PREFIX))


def _client():
    if not _enabled():
        raise RuntimeError("Cloudflare R2 is not configured")
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=_endpoint_url(),
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def upload_file(local_path: str, key: str, content_type: Optional[str] = None, skip_audio_strip: bool = False) -> str:
    """Upload moderated content to private R2.

    Video audio policy (Option A: all published video bytes are silent):
    by default (``skip_audio_strip=False``) any ``video/*`` upload is stripped
    of audio in place before upload, failing closed on any error. Callers that
    already stripped the bytes through ``services.media_processor``
    ``_make_video_derivatives`` (the async worker path and quarantine
    promotion) may pass ``skip_audio_strip=True`` to avoid a redundant second
    ffmpeg pass. Every other video caller (``persist_before_db`` mobile/chat
    uploads, legacy web after-request persistence, tools) MUST leave the
    default on — there is no other strip on those paths.
    """
    path = Path(local_path)
    if not path.is_file():
        raise FileNotFoundError(local_path)
    ctype = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if ctype.lower().startswith("video/") and not skip_audio_strip:
        from services.media_sanitizer import strip_video_audio_in_place

        strip_video_audio_in_place(str(path))
    key = _write_key(key)
    _client().upload_file(
        str(path),
        os.environ["R2_BUCKET"],
        key,
        ExtraArgs={
            "ContentType": ctype,
            "CacheControl": "private, no-store, max-age=0",
        },
    )
    return f"uploads/r2/{key}"


def _acknowledge_deleted_reference(reference: str) -> None:
    """Best-effort acknowledgement for DB-triggered media deletion outbox rows."""
    try:
        from database.connection import execute

        execute(
            """UPDATE media_delete_outbox
               SET completed_at=COALESCE(completed_at,NOW()), last_error=NULL
               WHERE reference=%s""",
            (reference,),
        )
    except Exception:
        # The object is already gone and private. A stale outbox row can be
        # reconciled later without turning a successful delete into a 500.
        pass


def delete_reference(reference: str) -> None:
    if not is_reference(reference):
        return
    prefix = (os.getenv("LITTLENET_R2_WRITE_PREFIX") or "").strip("/")
    if prefix and not str(reference).startswith(R2_REFERENCE_PREFIX + prefix + "/"):
        # A cloned LittleMuse database may reference old LittleNet objects.
        # Its delete outbox must never remove those shared-bucket objects.
        _acknowledge_deleted_reference(reference)
        return
    if not _enabled():
        # Never report a successful private-object delete when R2 is unavailable.
        # The durable outbox depends on this exception to retain retry state.
        raise RuntimeError("Cloudflare R2 is not configured")
    _client().delete_object(
        Bucket=os.environ["R2_BUCKET"],
        Key=str(reference)[len(R2_REFERENCE_PREFIX) :],
    )
    _acknowledge_deleted_reference(reference)


def _request_media_gate() -> None:
    """Prevent a signed URL from bypassing child account/time/onboarding controls."""
    try:
        from flask import g, has_request_context, session

        if not has_request_context():
            return
        uid = None
        role = None
        if hasattr(g, "mobile_user") and g.mobile_user:
            uid = int(g.mobile_user.get("user_id") or 0)
            role = str(g.mobile_user.get("role") or "").upper()
        elif session:
            uid = int(session.get("user_id") or 0)
            role = str(session.get("role") or "").upper()

        if role != "CHILD":
            return
        if not uid:
            raise PermissionError("child_session_required")
        from services.social import child_surface_open

        if not child_surface_open(uid):
            raise PermissionError("child_media_locked")
    except PermissionError:
        raise
    except Exception as exc:
        raise PermissionError("child_media_gate_unavailable") from exc


DEFAULT_SIGNED_URL_TTL = 600  # Authoritative 10-minute TTL


def get_playback_ttl(expires_seconds: int | None = None) -> int:
    """Return single authoritative playback signed URL TTL in seconds clamped between 60 and 600."""
    try:
        env_val = int(os.getenv("R2_SIGNED_URL_TTL", str(DEFAULT_SIGNED_URL_TTL)))
    except (TypeError, ValueError):
        env_val = DEFAULT_SIGNED_URL_TTL
    raw = expires_seconds if expires_seconds is not None else env_val
    return max(60, min(int(raw), 600))


def signed_download_url(reference: str, expires_seconds: int | None = None) -> str:
    if not is_reference(reference):
        raise ValueError("not an R2 reference")
    if not _enabled():
        raise RuntimeError("Cloudflare R2 is not configured")
    _request_media_gate()
    effective_ttl = get_playback_ttl(expires_seconds)
    return _client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": os.environ["R2_BUCKET"],
            "Key": str(reference)[len(R2_REFERENCE_PREFIX) :],
        },
        ExpiresIn=effective_ttl,
    )


def signed_upload_url(reference_or_key: str, content_type: str, expires_seconds: int | None = None) -> str:
    """Generate a short-lived presigned PUT URL for direct client-to-R2 upload."""
    if not _enabled():
        raise RuntimeError("Cloudflare R2 is not configured")
    key = str(reference_or_key)
    if key.startswith(R2_REFERENCE_PREFIX):
        key = key[len(R2_REFERENCE_PREFIX) :]
    prefix = (os.getenv("LITTLENET_R2_WRITE_PREFIX") or "").strip("/")
    if prefix and not key.startswith(prefix + "/"):
        raise ValueError("upload_key_outside_deployment_namespace")
    expiry = expires_seconds or int(os.getenv("R2_PRESIGNED_UPLOAD_TTL", "900"))
    return _client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": os.environ["R2_BUCKET"],
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=max(60, min(expiry, 3600)),
    )


def head_object(reference_or_key: str) -> dict | None:
    """Query object metadata in R2.

    Returns None ONLY when the object is genuinely missing (404 / NoSuchKey /
    NotFound). Auth failures (403), server errors (5xx), endpoint failures,
    and timeouts propagate so callers never mistake an outage for "missing":
    the upload-complete endpoint treats a missing object as client fraud
    (410) but treats R2 errors as server errors (500), and the media worker
    quarantines on None but records r2_preflight_failed on raised errors.
    """
    if not _enabled():
        raise RuntimeError("Cloudflare R2 is not configured")
    key = str(reference_or_key)
    if key.startswith(R2_REFERENCE_PREFIX):
        key = key[len(R2_REFERENCE_PREFIX) :]
    try:
        res = _client().head_object(Bucket=os.environ["R2_BUCKET"], Key=key)
        return {
            "content_length": int(res.get("ContentLength", 0)),
            "content_type": str(res.get("ContentType", "")),
            "etag": str(res.get("ETag", "")),
        }
    except ClientError as exc:
        code = str((exc.response or {}).get("Error", {}).get("Code", "") or "")
        status = int((exc.response or {}).get("ResponseMetadata", {}).get("HTTPStatusCode", 0) or 0)
        if code in {"NoSuchKey", "NotFound"} or status == 404:
            return None
        raise


def copy_object(source_ref_or_key: str, target_ref_or_key: str, content_type: str | None = None) -> str:
    """Move/copy an object between R2 namespaces (e.g. quarantine -> published)."""
    if not _enabled():
        raise RuntimeError("Cloudflare R2 is not configured")
    src = str(source_ref_or_key)
    if src.startswith(R2_REFERENCE_PREFIX):
        src = src[len(R2_REFERENCE_PREFIX) :]
    dst = str(target_ref_or_key)
    if dst.startswith(R2_REFERENCE_PREFIX):
        dst = dst[len(R2_REFERENCE_PREFIX) :]
    bucket = os.environ["R2_BUCKET"]
    copy_source = {"Bucket": bucket, "Key": src}
    extra = {}
    if content_type:
        extra["ContentType"] = content_type
        extra["MetadataDirective"] = "REPLACE"
    _client().copy_object(Bucket=bucket, Key=dst, CopySource=copy_source, **extra)
    return f"{R2_REFERENCE_PREFIX}{dst}"


def download_file(reference_or_key: str, local_path: str | Path) -> None:
    """Download an R2 object to local ephemeral storage for worker processing."""
    if not _enabled():
        raise RuntimeError("Cloudflare R2 is not configured")
    key = str(reference_or_key)
    if key.startswith(R2_REFERENCE_PREFIX):
        key = key[len(R2_REFERENCE_PREFIX) :]
    _client().download_file(os.environ["R2_BUCKET"], key, str(local_path))

