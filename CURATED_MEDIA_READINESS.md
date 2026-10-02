# Curated Media Readiness

## Local ffprobe audit

Tooling: `ffprobe` and `ffmpeg` 9.0.1 (gyan.dev essentials build) are installed, so the probe could run. There was nothing to probe.

Search scope: everything under `C:\LittleNet-FINAL-WORK` (the only entry there is `LittleNet\`; no sibling or extracted folders exist), including `mobile_app/` assets, `static/demo`, `datasets/`, `tests/`, `audit/`, `docs/` and `node_modules`. No other part of the disk was scanned.

| Check | Result |
|---|---|
| Files with a video extension (`.mp4 .mov .webm .mkv .m4v .avi .3gp .m3u8 .hevc .h265 .flv .mpg .mpeg .m2ts .mts .wmv .ogv`) | 0 |
| Files whose first bytes look like MP4/MOV (`ftyp`) or WebM/Matroska (EBML), regardless of extension | 0 |
| Files larger than 1 MB, excluding `.git` | 0 |
| Video files tracked in git (`git ls-files`) | 0 |
| `.gitattributes` LFS rules | `*.pth`, `*.safetensors`, `*.bin` only; none for video |
| `datasets/` | one empty entry, `datasets/jigsaw` |
| `uploads/`, `tests/fixtures/`, `tests/data/` | absent |

`.ts` was excluded as a video extension on purpose: it matched TypeScript sources under `mobile_app/`, and none of them is an MPEG transport stream.

Video assets inspected: **0**. Codecs found: **none**. Risky files: **none**. Per-file container, codec, pixel format, resolution, frame rate, duration and audio codec: **NOT EXECUTED** — no local video exists, so there is no output to report. No original media was touched and no normalization script was added, because no risky file exists to normalize.

## Delivery target already in source

User reels and curated reel ingest re-encode to the Android-safe target before publication:

- `services/media_processor.py` `_make_video_derivatives`: MP4, `libx264`, `yuv420p`, `-an`, `+faststart`.
- `tools/dataset_ingest.py` `_make_reel_delivery`: MP4, `libx264`, `yuv420p`, scale 720, `-an`, `+faststart`, plus a webp poster.

HEVC/H.265 sources are not stored as the playback object on those paths. A failed transcode raises instead of publishing the original (`check=True` / fail-closed sanitization).

Curated catalog keys are `curated/{version}/{category}/{sha256[:2]}/{sha256}/delivery.mp4` (see `R2_STORAGE_MAP.md`). Those objects live in R2 after ingest, not in this tree. Source inspection is not evidence that every historical object was transcoded.

## External requirement

Probe the live curated delivery objects with ffprobe once R2 access exists, for example:

```text
ffprobe -v error -show_entries format=format_name,duration:stream=codec_type,codec_name,pix_fmt,width,height,avg_frame_rate -of json <delivery.mp4>
```

Flag anything that is not MP4 + H.264 + `yuv420p` with a valid duration. Add a dry-run normalization utility only if that probe finds real non-conforming files.
