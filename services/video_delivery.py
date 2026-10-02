"""Production-grade Video Delivery Abstraction for LittleNet.

Supports adaptive streaming (e.g. Cloudflare Stream / HLS) with an out-of-the-box
failover to private R2 sanitized MP4 with cryptographic signed download URLs.
Ensures zero secret leakage to mobile client and guarantees strict child-safety
authorization before playback tokens or signed URLs are minted.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

import requests

from config import Config
from database.connection import execute, fetch_one
from services.media_delivery import (
    DEFAULT_SIGNED_URL_TTL,
    get_playback_ttl,
    is_authorized_viewer,
    resolve_media_delivery,
)

logger = logging.getLogger(__name__)


def probe_video_metadata(file_path: Path | str) -> dict[str, Any]:
    """Inspect local sanitized video to extract duration, dimensions, and aspect ratio.

    Falls back safely if ffprobe is absent or parsing fails.
    """
    default_meta = {
        "duration_ms": 15000,
        "width": 1080,
        "height": 1920,
        "aspect_ratio": "9:16",
    }
    path_obj = Path(file_path)
    if not path_obj.is_file() or not shutil.which("ffprobe"):
        return default_meta

    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration:format=duration",
            "-of", "json",
            str(path_obj),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode != 0:
            return default_meta

        data = json.loads(res.stdout or "{}")
        stream = (data.get("streams") or [{}])[0]
        fmt = data.get("format") or {}

        width = int(stream.get("width") or 1080)
        height = int(stream.get("height") or 1920)

        # Duration resolution: prefer stream duration, fall back to format duration
        dur_sec = 0.0
        try:
            dur_sec = float(stream.get("duration") or fmt.get("duration") or 15.0)
        except (ValueError, TypeError):
            dur_sec = 15.0
        duration_ms = max(1000, int(dur_sec * 1000))

        # Calculate aspect ratio tag
        if width > 0 and height > 0:
            ratio = width / height
            if 0.5 <= ratio <= 0.65:
                aspect_ratio = "9:16"
            elif 0.7 <= ratio <= 0.85:
                aspect_ratio = "4:5"
            elif 0.95 <= ratio <= 1.05:
                aspect_ratio = "1:1"
            elif 1.7 <= ratio <= 1.85:
                aspect_ratio = "16:9"
            else:
                aspect_ratio = f"{width}:{height}"
        else:
            aspect_ratio = "9:16"

        return {
            "duration_ms": duration_ms,
            "width": width,
            "height": height,
            "aspect_ratio": aspect_ratio,
        }
    except Exception as exc:
        logger.warning("ffprobe failed on %s: %s", path_obj, exc)
        return default_meta


class VideoDeliveryProvider:
    """Abstract interface for video ingestion, processing, and signed playback."""

    @property
    def provider_name(self) -> str:
        raise NotImplementedError

    def is_configured(self) -> bool:
        raise NotImplementedError

    def ingest(
        self,
        post_id: int,
        source_r2_key: str,
        published_ref: str,
        poster_ref: str | None,
        local_file: Path | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Ingest or register a sanitized video and record in media_assets."""
        raise NotImplementedError

    def get_playback_info(
        self,
        media_asset: dict[str, Any],
        viewer_id: int | None,
        viewer_role: str | None,
        expires_seconds: int = DEFAULT_SIGNED_URL_TTL,
    ) -> dict[str, Any]:
        """Resolve authorized playback URL and metadata for a viewer."""
        raise NotImplementedError


class SanitizedMP4DeliveryProvider(VideoDeliveryProvider):
    """Default high-performance video provider using private R2 sanitized MP4."""

    @property
    def provider_name(self) -> str:
        return "R2_SANITIZED_MP4"

    def is_configured(self) -> bool:
        return True

    def ingest(
        self,
        post_id: int,
        source_r2_key: str,
        published_ref: str,
        poster_ref: str | None,
        local_file: Path | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        meta = metadata or {}
        if local_file and local_file.is_file() and not metadata:
            meta = probe_video_metadata(local_file)

        duration_ms = meta.get("duration_ms", 15000)
        width = meta.get("width", 1080)
        height = meta.get("height", 1920)
        aspect_ratio = meta.get("aspect_ratio", "9:16")
        provider_asset_id = f"post_{post_id}"
        playback_id = f"play_{post_id}"

        # Insert or update media_assets
        existing = fetch_one("SELECT media_id FROM media_assets WHERE post_id=%s", (post_id,))
        if existing:
            media_id = existing["media_id"]
            execute(
                """UPDATE media_assets
                   SET published_reference=%s, poster_reference=%s, provider=%s,
                       provider_asset_id=%s, playback_id=%s, duration_ms=%s,
                       width=%s, height=%s, aspect_ratio=%s, status='READY', updated_at=NOW()
                   WHERE media_id=%s""",
                (
                    published_ref,
                    poster_ref,
                    self.provider_name,
                    provider_asset_id,
                    playback_id,
                    duration_ms,
                    width,
                    height,
                    aspect_ratio,
                    media_id,
                ),
            )
        else:
            media_id = execute(
                """INSERT INTO media_assets(
                       post_id, media_kind, source_r2_key, published_reference,
                       provider, provider_asset_id, playback_id, poster_reference,
                       duration_ms, width, height, aspect_ratio, status
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING media_id""",
                (
                    post_id,
                    "REEL",
                    source_r2_key,
                    published_ref,
                    self.provider_name,
                    provider_asset_id,
                    playback_id,
                    poster_ref,
                    duration_ms,
                    width,
                    height,
                    aspect_ratio,
                    "READY",
                ),
                returning=True,
            )

        return {
            "media_id": media_id,
            "post_id": post_id,
            "provider": self.provider_name,
            "provider_asset_id": provider_asset_id,
            "playback_id": playback_id,
            "duration_ms": duration_ms,
            "width": width,
            "height": height,
            "aspect_ratio": aspect_ratio,
            "status": "READY",
        }

    def get_playback_info(
        self,
        media_asset: dict[str, Any],
        viewer_id: int | None,
        viewer_role: str | None,
        expires_seconds: int = DEFAULT_SIGNED_URL_TTL,
    ) -> dict[str, Any]:
        pub_ref = media_asset.get("published_reference")
        poster_ref = media_asset.get("poster_reference")

        delivery = resolve_media_delivery(pub_ref, viewer_id=viewer_id, viewer_role=viewer_role, expires_seconds=expires_seconds)
        poster_delivery = resolve_media_delivery(poster_ref, viewer_id=viewer_id, viewer_role=viewer_role, expires_seconds=expires_seconds) if poster_ref else {}

        return {
            "media_id": media_asset.get("media_id"),
            "post_id": media_asset.get("post_id"),
            "provider": self.provider_name,
            "playback_id": media_asset.get("playback_id"),
            "delivery_type": "MP4",
            "playback_url": delivery.get("url"),
            "playback_expires_at": delivery.get("expires_at"),
            "poster_url": poster_delivery.get("url"),
            "duration_ms": media_asset.get("duration_ms"),
            "width": media_asset.get("width"),
            "height": media_asset.get("height"),
            "aspect_ratio": media_asset.get("aspect_ratio") or "9:16",
            "delivery_mode": delivery.get("delivery_mode"),
        }


class CloudflareStreamDeliveryProvider(VideoDeliveryProvider):
    """Cloudflare Stream adaptive-HLS provider with private playback.

    Videos are provisioned through a one-time direct-upload URL with signed
    playback required from creation. The sanitized private R2 MP4 remains
    available as a fail-safe while Stream is encoding or unavailable.
    """

    def __init__(self) -> None:
        self.account_id = os.getenv("CLOUDFLARE_STREAM_ACCOUNT_ID", "").strip()
        self.api_token = os.getenv("CLOUDFLARE_STREAM_API_TOKEN", "").strip()
        self.subdomain = os.getenv("CLOUDFLARE_STREAM_SUBDOMAIN", "").strip()
        self.enabled = os.getenv("CLOUDFLARE_STREAM_ENABLED", "0").strip() == "1"
        self.api_timeout = max(5, min(60, int(os.getenv("CLOUDFLARE_STREAM_API_TIMEOUT_SECONDS", "20"))))
        self.signing_key_id = os.getenv("CLOUDFLARE_STREAM_SIGNING_KEY_ID", "").strip()
        self.signing_private_key_b64 = os.getenv("CLOUDFLARE_STREAM_SIGNING_PRIVATE_KEY_B64", "").strip()

    @property
    def provider_name(self) -> str:
        return "CLOUDFLARE_STREAM"

    @property
    def _api_base(self) -> str:
        return f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/stream"

    @property
    def _stream_host(self) -> str:
        host = self.subdomain.strip().removeprefix("https://").removeprefix("http://").strip("/")
        if not host:
            return ""
        return host if "." in host else f"{host}.cloudflarestream.com"

    def is_configured(self) -> bool:
        if not self.enabled:
            return False
        missing = [
            name
            for name, value in (
                ("CLOUDFLARE_STREAM_ACCOUNT_ID", self.account_id),
                ("CLOUDFLARE_STREAM_API_TOKEN", self.api_token),
                ("CLOUDFLARE_STREAM_SUBDOMAIN", self._stream_host),
            )
            if not value
        ]
        if missing:
            logger.error("Cloudflare Stream enabled but missing %s", ", ".join(missing))
            return False
        return True

    def _api_request(self, method: str, suffix: str, *, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
        response = requests.request(
            method,
            f"{self._api_base}{suffix}",
            headers={"Authorization": f"Bearer {self.api_token}"},
            json=json_body,
            timeout=self.api_timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise RuntimeError("cloudflare_stream_api_unsuccessful")
        result = payload.get("result")
        return result if isinstance(result, dict) else {}

    def _video_details(self, uid: str) -> dict[str, Any]:
        return self._api_request("GET", f"/{uid}")

    @staticmethod
    def _status_from_details(details: dict[str, Any]) -> str:
        if details.get("readyToStream") is True:
            return "READY"
        state = str((details.get("status") or {}).get("state") or "").lower()
        if state == "error":
            return "FAILED"
        return "ENCODING"

    def _persist_asset(
        self,
        *,
        post_id: int,
        source_r2_key: str,
        published_ref: str,
        poster_ref: str | None,
        uid: str,
        status: str,
        metadata: dict[str, Any],
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        details = details or {}
        input_meta = details.get("input") if isinstance(details.get("input"), dict) else {}
        fallback_duration = float(metadata.get("duration_ms", 15000)) / 1000.0
        duration_ms = max(1000, int(float(details.get("duration") or fallback_duration) * 1000))
        width = int(input_meta.get("width") or metadata.get("width", 1080))
        height = int(input_meta.get("height") or metadata.get("height", 1920))
        aspect_ratio = metadata.get("aspect_ratio", "9:16")

        existing = fetch_one("SELECT media_id FROM media_assets WHERE post_id=%s", (post_id,))
        if existing:
            media_id = existing["media_id"]
            execute(
                """UPDATE media_assets
                   SET published_reference=%s, poster_reference=%s, provider=%s,
                       provider_asset_id=%s, playback_id=%s, duration_ms=%s,
                       width=%s, height=%s, aspect_ratio=%s, status=%s, updated_at=NOW()
                   WHERE media_id=%s""",
                (
                    published_ref, poster_ref, self.provider_name, uid, uid,
                    duration_ms, width, height, aspect_ratio, status, media_id,
                ),
            )
        else:
            media_id = execute(
                """INSERT INTO media_assets(
                       post_id, media_kind, source_r2_key, published_reference,
                       provider, provider_asset_id, playback_id, poster_reference,
                       duration_ms, width, height, aspect_ratio, status
                   ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING media_id""",
                (
                    post_id, "REEL", source_r2_key, published_ref,
                    self.provider_name, uid, uid, poster_ref,
                    duration_ms, width, height, aspect_ratio, status,
                ),
                returning=True,
            )

        return {
            "media_id": media_id,
            "post_id": post_id,
            "provider": self.provider_name,
            "provider_asset_id": uid,
            "playback_id": uid,
            "duration_ms": duration_ms,
            "width": width,
            "height": height,
            "aspect_ratio": aspect_ratio,
            "status": status,
        }

    def ingest(
        self,
        post_id: int,
        source_r2_key: str,
        published_ref: str,
        poster_ref: str | None,
        local_file: Path | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fallback = SanitizedMP4DeliveryProvider()
        if not self.is_configured():
            return fallback.ingest(post_id, source_r2_key, published_ref, poster_ref, local_file, metadata)
        if not local_file or not Path(local_file).is_file():
            logger.warning("Cloudflare Stream ingest skipped for post %s: sanitized local file unavailable", post_id)
            return fallback.ingest(post_id, source_r2_key, published_ref, poster_ref, local_file, metadata)

        local_path = Path(local_file)
        if local_path.stat().st_size > 190 * 1024 * 1024:
            logger.warning("Cloudflare Stream ingest skipped for post %s: file exceeds basic upload limit", post_id)
            return fallback.ingest(post_id, source_r2_key, published_ref, poster_ref, local_file, metadata)

        meta = metadata or probe_video_metadata(local_path)

        # Idempotency for worker retries: if this post already has a real Stream
        # UID in flight/ready, reuse it instead of creating a second billable
        # video. FAILED assets may be retried with a fresh upload.
        existing_asset = get_video_asset(post_id)
        if (
            existing_asset
            and str(existing_asset.get("provider") or "").upper() == self.provider_name
            and existing_asset.get("provider_asset_id")
            and str(existing_asset.get("status") or "").upper() in {"ENCODING", "READY"}
        ):
            return dict(existing_asset)

        uid = ""
        try:
            provision = self._api_request(
                "POST",
                "/direct_upload",
                json_body={
                    "maxDurationSeconds": int(getattr(Config, "VIDEO_MAX_SECONDS", 600)),
                    "requireSignedURLs": True,
                    "meta": {"littlenet_post_id": str(post_id)},
                },
            )
            uid = str(provision.get("uid") or "").strip()
            upload_url = str(provision.get("uploadURL") or "").strip()
            if not uid or not upload_url.startswith("https://"):
                raise RuntimeError("cloudflare_stream_direct_upload_invalid")

            with local_path.open("rb") as fh:
                response = requests.post(
                    upload_url,
                    files={"file": (local_path.name, fh, "video/mp4")},
                    timeout=180,
                )
            response.raise_for_status()

            details = self._video_details(uid)
            status = self._status_from_details(details)
            return self._persist_asset(
                post_id=post_id,
                source_r2_key=source_r2_key,
                published_ref=published_ref,
                poster_ref=poster_ref,
                uid=uid,
                status=status,
                metadata=meta,
                details=details,
            )
        except Exception as exc:
            # If provisioning succeeded but a later step failed, remove the
            # orphaned Stream object best-effort so retries do not accumulate
            # unused billable assets.
            if uid:
                try:
                    self._api_request("DELETE", f"/{uid}")
                except Exception:
                    logger.warning("Could not remove orphaned Cloudflare Stream asset for post %s", post_id)
            logger.warning(
                "Cloudflare Stream ingest failed for post %s; retaining private R2 fallback: %s",
                post_id,
                type(exc).__name__,
            )
            return fallback.ingest(post_id, source_r2_key, published_ref, poster_ref, local_file, meta)

    def _refresh_stream_status(self, media_asset: dict[str, Any]) -> str:
        uid = str(media_asset.get("provider_asset_id") or media_asset.get("playback_id") or "").strip()
        if not uid:
            return "FAILED"
        try:
            details = self._video_details(uid)
            status = self._status_from_details(details)
            input_meta = details.get("input") if isinstance(details.get("input"), dict) else {}
            execute(
                """UPDATE media_assets
                   SET status=%s,
                       duration_ms=COALESCE(%s,duration_ms),
                       width=COALESCE(%s,width),
                       height=COALESCE(%s,height),
                       updated_at=NOW()
                   WHERE media_id=%s""",
                (
                    status,
                    int(float(details.get("duration") or 0) * 1000) or None,
                    int(input_meta.get("width") or 0) or None,
                    int(input_meta.get("height") or 0) or None,
                    media_asset.get("media_id"),
                ),
            )
            return status
        except Exception as exc:
            logger.warning(
                "Cloudflare Stream status refresh failed for media %s: %s",
                media_asset.get("media_id"),
                type(exc).__name__,
            )
            return str(media_asset.get("status") or "ENCODING").upper()

    def _local_signed_token(self, uid: str, expires_at: int) -> str | None:
        if not self.signing_key_id or not self.signing_private_key_b64:
            return None
        try:
            import jwt

            private_key = base64.b64decode(self.signing_private_key_b64).decode("utf-8")
            now = int(time.time())
            return str(
                jwt.encode(
                    {"sub": uid, "kid": self.signing_key_id, "exp": expires_at, "nbf": now - 5},
                    private_key,
                    algorithm="RS256",
                    headers={"kid": self.signing_key_id},
                )
            )
        except Exception as exc:
            logger.warning("Local Cloudflare Stream token signing failed: %s", type(exc).__name__)
            return None

    def _signed_token(self, uid: str, expires_at: int) -> str:
        token = self._local_signed_token(uid, expires_at)
        if token:
            return token
        result = self._api_request(
            "POST",
            f"/{uid}/token",
            json_body={"exp": expires_at, "downloadable": False},
        )
        token = str(result.get("token") or "").strip()
        if not token:
            raise RuntimeError("cloudflare_stream_token_missing")
        return token

    def get_playback_info(
        self,
        media_asset: dict[str, Any],
        viewer_id: int | None,
        viewer_role: str | None,
        expires_seconds: int = DEFAULT_SIGNED_URL_TTL,
    ) -> dict[str, Any]:
        pub_ref = media_asset.get("published_reference")
        if not is_authorized_viewer(viewer_id, viewer_role, pub_ref or ""):
            return {
                "media_id": media_asset.get("media_id"),
                "post_id": media_asset.get("post_id"),
                "provider": self.provider_name,
                "delivery_type": "HLS",
                "playback_url": None,
                "playback_expires_at": None,
                "delivery_mode": "DENIED",
            }

        if not self.is_configured():
            return SanitizedMP4DeliveryProvider().get_playback_info(
                media_asset, viewer_id, viewer_role, expires_seconds
            )

        status = str(media_asset.get("status") or "").upper()
        if status != "READY":
            status = self._refresh_stream_status(media_asset)
        if status != "READY":
            return SanitizedMP4DeliveryProvider().get_playback_info(
                media_asset, viewer_id, viewer_role, expires_seconds
            )

        uid = str(media_asset.get("playback_id") or media_asset.get("provider_asset_id") or "").strip()
        if not uid:
            return SanitizedMP4DeliveryProvider().get_playback_info(
                media_asset, viewer_id, viewer_role, expires_seconds
            )

        ttl = get_playback_ttl(expires_seconds)
        expires_at = int(time.time()) + ttl
        try:
            token = self._signed_token(uid, expires_at)
        except Exception as exc:
            logger.warning(
                "Cloudflare Stream token minting failed for media %s: %s",
                media_asset.get("media_id"),
                type(exc).__name__,
            )
            return SanitizedMP4DeliveryProvider().get_playback_info(
                media_asset, viewer_id, viewer_role, expires_seconds
            )

        poster_ref = media_asset.get("poster_reference")
        poster_delivery = (
            resolve_media_delivery(
                poster_ref,
                viewer_id=viewer_id,
                viewer_role=viewer_role,
                expires_seconds=expires_seconds,
            )
            if poster_ref
            else {}
        )
        return {
            "media_id": media_asset.get("media_id"),
            "post_id": media_asset.get("post_id"),
            "provider": self.provider_name,
            "playback_id": uid,
            "delivery_type": "HLS",
            "playback_url": f"https://{self._stream_host}/{token}/manifest/video.m3u8",
            "playback_expires_at": expires_at,
            "poster_url": poster_delivery.get("url"),
            "duration_ms": media_asset.get("duration_ms"),
            "width": media_asset.get("width"),
            "height": media_asset.get("height"),
            "aspect_ratio": media_asset.get("aspect_ratio") or "9:16",
            "delivery_mode": "DIRECT_SIGNED",
        }


def video_delivery_healthcheck() -> dict[str, Any]:
    """Validate the configured video-delivery mode without exposing credentials."""
    cfs = CloudflareStreamDeliveryProvider()
    if not cfs.enabled:
        return {
            "ok": True,
            "provider": "R2_SANITIZED_MP4",
            "adaptive_streaming": False,
            "mode": "private_r2_fallback",
        }
    if not cfs.is_configured():
        return {
            "ok": False,
            "provider": "CLOUDFLARE_STREAM",
            "adaptive_streaming": True,
            "mode": "configuration_incomplete",
        }
    try:
        response = requests.get(
            cfs._api_base,
            headers={"Authorization": f"Bearer {cfs.api_token}"},
            params={"per_page": 1},
            timeout=cfs.api_timeout,
        )
        response.raise_for_status()
        payload = response.json()
        ok = isinstance(payload, dict) and payload.get("success") is True
        return {
            "ok": bool(ok),
            "provider": "CLOUDFLARE_STREAM",
            "adaptive_streaming": True,
            "mode": "api_verified" if ok else "api_unsuccessful",
        }
    except Exception as exc:
        logger.warning("Cloudflare Stream preflight failed: %s", type(exc).__name__)
        return {
            "ok": False,
            "provider": "CLOUDFLARE_STREAM",
            "adaptive_streaming": True,
            "mode": "api_unreachable",
            "error_type": type(exc).__name__,
        }


def get_video_provider() -> VideoDeliveryProvider:
    """Factory returning the active video delivery provider."""
    cfs = CloudflareStreamDeliveryProvider()
    if cfs.is_configured():
        return cfs
    return SanitizedMP4DeliveryProvider()


def ingest_post_video(
    post_id: int,
    child_id: int,
    source_r2_key: str,
    published_ref: str,
    poster_ref: str | None,
    local_file: Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ingest a sanitized video into the active video delivery provider."""
    provider = get_video_provider()
    return provider.ingest(
        post_id=post_id,
        source_r2_key=source_r2_key,
        published_ref=published_ref,
        poster_ref=poster_ref,
        local_file=local_file,
        metadata=metadata,
    )


def get_video_asset(post_id: int) -> dict[str, Any] | None:
    """Retrieve media asset row by post_id."""
    return fetch_one(
        """SELECT media_id, post_id, media_kind, source_r2_key, published_reference,
                  provider, provider_asset_id, playback_id, poster_reference,
                  duration_ms, width, height, aspect_ratio, status, created_at, updated_at
           FROM media_assets
           WHERE post_id=%s
           ORDER BY media_id DESC
           LIMIT 1""",
        (post_id,),
    )


def resolve_video_playback(
    post_id: int,
    viewer_id: int | None,
    viewer_role: str | None,
    expires_seconds: int = DEFAULT_SIGNED_URL_TTL,
) -> dict[str, Any]:
    """Authoritatively resolve video playback for a given viewer context."""
    asset = get_video_asset(post_id)
    if not asset:
        # Fallback: check posts table directly
        post = fetch_one(
            "SELECT post_id, media_path, poster_path, child_id FROM posts WHERE post_id=%s",
            (post_id,),
        )
        if not post or not post.get("media_path"):
            return {"playback_url": None, "delivery_mode": "DENIED", "playback_expires_at": None}

        # Dynamically seed media_assets for backward compatibility
        ingest_post_video(
            post_id=post_id,
            child_id=post["child_id"],
            source_r2_key=post["media_path"],
            published_ref=post["media_path"],
            poster_ref=post.get("poster_path"),
        )
        asset = get_video_asset(post_id)

    if not asset:
        return {"playback_url": None, "delivery_mode": "DENIED", "playback_expires_at": None}

    provider_name = asset.get("provider")
    if provider_name == "CLOUDFLARE_STREAM":
        stream_provider = CloudflareStreamDeliveryProvider()
        # Historical hardening builds could have persisted placeholder Stream
        # asset IDs before real Stream ingestion existed. Never construct a fake
        # HLS URL from those rows: serve the already-sanitized private R2
        # published reference until a verified Stream provider is available.
        provider: VideoDeliveryProvider = (
            stream_provider if stream_provider.is_configured()
            else SanitizedMP4DeliveryProvider()
        )
    else:
        provider = SanitizedMP4DeliveryProvider()

    return provider.get_playback_info(
        media_asset=asset,
        viewer_id=viewer_id,
        viewer_role=viewer_role,
        expires_seconds=expires_seconds,
    )
