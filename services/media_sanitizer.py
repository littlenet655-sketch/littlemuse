"""Media sanitization before LittleNet persists child uploads.

LittleNet intentionally retired standalone speech/audio moderation. Therefore a
video may not carry an unmoderated audio track into R2. The web runtime ships
ffmpeg/ffprobe and this helper removes audio without re-encoding the video.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


class MediaSanitizationError(RuntimeError):
    pass


def sanitize_image_in_place(path: str) -> bool:
    """Strip EXIF/GPS metadata and normalize an image before publication."""
    source = Path(path)
    if not source.is_file():
        raise MediaSanitizationError("image_file_missing")
    suffix = source.suffix.lower() or ".jpg"
    output_format = {"jpg": "JPEG", ".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}.get(
        suffix, "JPEG"
    )
    fd, tmp = tempfile.mkstemp(prefix="littlenet_clean_image_", suffix=suffix, dir=str(source.parent))
    os.close(fd)
    try:
        try:
            from PIL import Image, ImageOps
            with Image.open(source) as image:
                clean = ImageOps.exif_transpose(image)
                if output_format == "JPEG":
                    clean = clean.convert("RGB")
                save_kwargs = {"quality": 92} if output_format in {"JPEG", "WEBP"} else {}
                clean.save(tmp, format=output_format, **save_kwargs)
        except Exception as exc:
            raise MediaSanitizationError("image_metadata_strip_failed") from exc
        if not os.path.isfile(tmp) or os.path.getsize(tmp) <= 0:
            raise MediaSanitizationError("clean_image_output_missing")
        os.replace(tmp, str(source))
        return True
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _probe(path: str, selector: str) -> list[str]:
    try:
        result=subprocess.run(
            [
                'ffprobe','-v','error','-select_streams',selector,
                '-show_entries','stream=index','-of','csv=p=0',path,
            ],
            capture_output=True,text=True,timeout=20,check=True,
        )
    except (OSError,subprocess.SubprocessError) as exc:
        raise MediaSanitizationError('ffprobe_unavailable_or_failed') from exc
    return [line.strip() for line in (result.stdout or '').splitlines() if line.strip()]


def has_audio_stream(path: str) -> bool:
    return bool(_probe(path,'a'))


def has_video_stream(path: str) -> bool:
    return bool(_probe(path,'v'))


def strip_video_audio_in_place(path: str) -> bool:
    """Remove all audio streams and atomically replace ``path``.

    Returns True when an audio stream was removed and False when the video was
    already silent. Any uncertainty raises so the caller can fail closed.
    """
    source=Path(path)
    if not source.is_file():
        raise MediaSanitizationError('video_file_missing')
    if not has_video_stream(str(source)):
        raise MediaSanitizationError('video_stream_missing')
    if not has_audio_stream(str(source)):
        return False

    fd,tmp=tempfile.mkstemp(prefix='littlenet_silent_',suffix=source.suffix or '.mp4',dir=str(source.parent))
    os.close(fd)
    try:
        try:
            subprocess.run(
                [
                    'ffmpeg','-y','-loglevel','error','-i',str(source),
                    '-map','0:v:0','-c:v','copy','-an','-map_metadata','-1',tmp,
                ],
                capture_output=True,text=True,timeout=120,check=True,
            )
        except (OSError,subprocess.SubprocessError) as exc:
            raise MediaSanitizationError('ffmpeg_audio_strip_failed') from exc

        if not os.path.isfile(tmp) or os.path.getsize(tmp)<=0:
            raise MediaSanitizationError('silent_video_output_missing')
        if not has_video_stream(tmp):
            raise MediaSanitizationError('silent_video_stream_missing')
        if has_audio_stream(tmp):
            raise MediaSanitizationError('audio_stream_still_present')
        os.replace(tmp,str(source))
        return True
    finally:
        if os.path.exists(tmp):
            try:os.unlink(tmp)
            except OSError:pass
