# Curated Media Readiness

## Local probe

A recursive search of this workspace found **zero** `.mp4`, `.mov`, `.webm`, `.mkv`, or `.m4v` files. There is no `datasets/` payload and no local curated reel library to inspect.

ffprobe on curated files: **NOT EXECUTED** — no local video payloads exist. Originals were not overwritten.

## Delivery target already in source

User reels and curated reel ingest both transcode to the Android-safe target before publication:

- `services/media_processor.py` `_make_video_derivatives`: MP4, `libx264`, `yuv420p`, `-an`, `+faststart`.
- `tools/dataset_ingest.py` `_make_reel_delivery`: MP4, `libx264`, `yuv420p`, scale 720, `-an`, `+faststart`, plus a webp poster.

HEVC/H.265 sources are not stored as the playback object. They are re-encoded on those paths. Invalid duration is not accepted as a published derivative because ffmpeg `check=True` / fail-closed sanitization raises instead of publishing the original.

Curated catalog keys are `curated/{version}/{category}/{sha256[:2]}/{sha256}/delivery.mp4` (see `R2_STORAGE_MAP.md`). Those objects live in R2 after ingest, not in this tree.

## External requirement

Probe the live curated delivery objects with ffprobe after R2 credentials exist. Do not treat this source tree as proof that every historical object was transcoded.
