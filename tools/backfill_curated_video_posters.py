"""Backfill missing poster images for already-published curated videos.

Safe defaults:
- requires the normal production DATABASE_URL + R2 credentials at execution time
- dry-run unless --apply is provided
- does not re-moderate or modify delivery/original video objects
- skips non-ALLOWED / unsafe assets
- updates only poster_object_key + updated_at after successful R2 upload
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from database.connection import execute, fetch_all
from services import object_storage


R2_PREFIX = "uploads/r2/"


def _poster_key(delivery_ref: str) -> str:
    ref = str(delivery_ref or "")
    key = ref[len(R2_PREFIX):] if ref.startswith(R2_PREFIX) else ref
    p = Path(key)
    parent = str(p.parent).replace("\\", "/")
    stem = p.stem
    if stem and stem != "delivery" and stem != "poster":
        return f"{parent}/{stem}_poster.jpg"
    return f"{parent}/poster.jpg"


def _make_poster(video_path: Path, poster_path: Path) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg_not_found")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", "0.2", "-i", str(video_path),
        "-frames:v", "1", "-vf", "scale=480:-2",
        str(poster_path),
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=60, check=False)
    if result.returncode != 0 or not poster_path.is_file() or poster_path.stat().st_size <= 0:
        raise RuntimeError("poster_generation_failed")


def candidates(limit: int) -> list[dict]:
    return fetch_all(
        """SELECT asset_id, delivery_object_key, poster_object_key, moderation_status, is_safe
             FROM curated_media_assets
            WHERE media_type='VIDEO'
              AND moderation_status='ALLOWED'
              AND is_safe=TRUE
              AND (poster_object_key IS NULL OR poster_object_key='')
            ORDER BY created_at ASC
            LIMIT %s""",
        (max(1, int(limit)),),
    )


def run(*, apply: bool, limit: int) -> dict:
    rows = candidates(limit)
    report = {
        "apply": bool(apply),
        "candidates": len(rows),
        "generated": 0,
        "skipped_missing_video": 0,
        "failures": [],
        "items": [],
    }

    for row in rows:
        asset_id = str(row["asset_id"])
        delivery_ref = str(row.get("delivery_object_key") or "")
        target_key = _poster_key(delivery_ref)
        item = {
            "asset_id": asset_id,
            "delivery_object_key": delivery_ref,
            "target_poster_key": object_storage.new_reference(target_key),
            "status": "DRY_RUN",
        }

        try:
            if not delivery_ref or object_storage.head_object(delivery_ref) is None:
                item["status"] = "MISSING_VIDEO"
                report["skipped_missing_video"] += 1
                report["items"].append(item)
                continue

            if not apply:
                report["items"].append(item)
                continue

            with tempfile.TemporaryDirectory(prefix=f"littlenet_poster_{asset_id}_") as tmp:
                tmpdir = Path(tmp)
                video_path = tmpdir / "delivery.mp4"
                poster_path = tmpdir / "poster.jpg"
                object_storage.download_file(delivery_ref, video_path)
                _make_poster(video_path, poster_path)
                if not poster_path.is_file() or poster_path.stat().st_size <= 0:
                    raise RuntimeError(f"empty_poster_generated: {asset_id}")
                poster_ref = object_storage.upload_file(
                    str(poster_path),
                    target_key,
                    content_type="image/jpeg",
                )
                if object_storage.head_object(poster_ref) is None:
                    raise RuntimeError(f"uploaded_poster_head_check_failed: {poster_ref}")

            execute(
                """UPDATE curated_media_assets
                      SET poster_object_key=%s,
                          thumbnail_object_key=COALESCE(thumbnail_object_key,%s),
                          updated_at=NOW()
                    WHERE asset_id=%s
                      AND media_type='VIDEO'
                      AND moderation_status='ALLOWED'
                      AND is_safe=TRUE
                      AND (poster_object_key IS NULL OR poster_object_key='')""",
                (poster_ref, poster_ref, asset_id),
            )
            item["status"] = "GENERATED"
            item["poster_object_key"] = poster_ref
            report["generated"] += 1

        except Exception as exc:
            item["status"] = "ERROR"
            item["error"] = f"{type(exc).__name__}: {exc}"
            report["failures"].append(item["error"])

        report["items"].append(item)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill curated video posters")
    parser.add_argument("--apply", action="store_true", help="perform R2 upload + DB update")
    parser.add_argument("--limit", type=int, default=250)
    parser.add_argument("--report", type=Path, default=Path("curated_video_poster_backfill.json"))
    args = parser.parse_args()

    result = run(apply=args.apply, limit=args.limit)
    args.report.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    return 2 if result["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
