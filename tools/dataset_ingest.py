"""LittleNet curated multimedia dataset ingestion.

This tool consumes the audited 24-column master CSV plus the six source ZIP
archives. Expected-safe rows are re-moderated, persisted to private R2 and then
inserted into the curated catalog tables. Expected-blocked rows are NEVER uploaded
or inserted into the child-serving catalog; they are only verified as benchmark
samples and reported.

Run with --dry-run first. Production publication is explicit via --publish.
"""
from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import argparse
import csv
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any

EXPECTED_COLUMNS = {
    "id", "archive_file", "raw_category", "app_category", "filename",
    "media_type", "is_reel", "is_story", "width", "height", "resolution",
    "duration_seconds", "file_size_bytes", "file_size_kb", "title", "caption",
    "hashtags", "audience_age_group", "is_safe", "moderation_status",
    "safety_score", "adult_score", "safety_reason", "app_destination_tab",
}

CATEGORY_MAP = {
    "family": "Family & Community",
    "animals": "Nature & Animals",
    "crafts": "Art & Creative Hobbies",
    "gardening": "Science & Gardening",
    "cooking": "Culinary Arts & Food",
}

AGE_RANGES = {
    "ALL": (4, 18),
    "6-8": (6, 8),
    "9-11": (9, 11),
    "12-13": (12, 13),
    "14-18": (14, 18),
}


def _bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _hashtags(raw: str) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    tags = re.findall(r"#([A-Za-z0-9_-]+)", text)
    if not tags:
        tags = [part.strip().lstrip("#") for part in re.split(r"[,;\s]+", text)]
    out: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        clean = tag.strip().lower()[:80]
        if clean and clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def _category(row: dict[str, str]) -> str:
    app = str(row.get("app_category") or "").strip()
    if app in CATEGORY_MAP.values():
        return app
    hay = " ".join(
        str(row.get(k) or "").lower()
        for k in ("app_category", "raw_category", "archive_file")
    )
    for needle, display in CATEGORY_MAP.items():
        if needle in hay or (needle == "animals" and "animal" in hay):
            return display
    raise ValueError(f"unsupported curated category for row {row.get('id')}: {app!r}")


def _find_zip_member(zf: zipfile.ZipFile, filename: str) -> str:
    wanted = filename.replace("\\", "/").lstrip("/")
    names = [n for n in zf.namelist() if not n.endswith("/")]
    if wanted in names:
        return wanted
    matches = [n for n in names if Path(n).name == Path(wanted).name]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise FileNotFoundError(f"{filename!r} not found in archive")
    raise RuntimeError(f"ambiguous filename {filename!r} in archive: {matches[:5]}")


def _materialize_source(row: dict[str, str], archives_dir: Path, temp_dir: Path) -> Path:
    archive = archives_dir / str(row["archive_file"]).strip()
    if not archive.is_file():
        raise FileNotFoundError(f"archive not found: {archive}")
    with zipfile.ZipFile(archive, "r") as zf:
        member = _find_zip_member(zf, str(row["filename"]).strip())
        suffix = Path(member).suffix.lower()
        target = temp_dir / f"{str(row['id']).strip()}_{hashlib.sha1(member.encode()).hexdigest()[:8]}{suffix}"
        with zf.open(member, "r") as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    return target


def _make_reel_delivery(source: Path, temp_dir: Path) -> tuple[Path, Path | None]:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required for reel delivery derivatives")
    delivery = temp_dir / f"{source.stem}_720.mp4"
    poster = temp_dir / f"{source.stem}_poster.webp"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
            "-an", "-vf", "scale=720:-2", "-c:v", "libx264", "-preset", "medium",
            "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(delivery),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "0.2",
            "-i", str(delivery), "-frames:v", "1", "-vf", "scale=480:-2", str(poster),
        ],
        check=True,
    )
    return delivery, poster if poster.is_file() else None


def _validate_csv(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = EXPECTED_COLUMNS - columns
        if missing:
            raise ValueError(f"master CSV missing columns: {sorted(missing)}")
        rows = [dict(row) for row in reader]
    if len(rows) != 206:
        raise ValueError(f"expected exactly 206 dataset rows, found {len(rows)}")
    ids = [str(r.get("id") or "").strip() for r in rows]
    if len(set(ids)) != len(ids) or any(not x for x in ids):
        raise ValueError("master CSV ids must be non-empty and unique")
    allowed = sum(1 for r in rows if str(r.get("moderation_status") or "").upper() == "ALLOWED")
    blocked = sum(1 for r in rows if str(r.get("moderation_status") or "").upper() == "BLOCKED")
    if (allowed, blocked) != (194, 12):
        raise ValueError(f"expected 194 ALLOWED / 12 BLOCKED rows, found {allowed} / {blocked}")
    return rows


def _asset_exists(sha256: str):
    from database.connection import fetch_one
    return fetch_one(
        "SELECT asset_id,dataset_version,source_row_id FROM curated_media_assets WHERE sha256=%s",
        (sha256,),
    )


def _insert_catalog_row(
    *, row: dict[str, str], sha256: str, category: str, original_ref: str,
    delivery_ref: str, poster_ref: str | None, mime_type: str,
    model_signals: dict[str, Any], decision, dataset_version: str, publish: bool,
):
    from database.connection import get_db_connection

    age_group = str(row.get("audience_age_group") or "ALL").strip().upper()
    if age_group not in AGE_RANGES:
        raise ValueError(f"invalid audience age group: {age_group}")
    min_age, max_age = AGE_RANGES[age_group]
    status = "ALLOWED" if decision.action == "ALLOW" else "REVIEW"
    publish_status = "PUBLISHED" if publish and status == "ALLOWED" else "DRAFT"
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT category_id FROM content_categories WHERE display_name=%s AND active=TRUE", (category,))
        cat = cur.fetchone()
        if not cat:
            raise RuntimeError(f"missing content category seed: {category}")
        category_id = cat["category_id"] if isinstance(cat, dict) else cat[0]

        cur.execute(
            """INSERT INTO curated_media_assets(
                 dataset_version,source_row_id,archive_file,original_filename,sha256,media_type,
                 original_object_key,delivery_object_key,poster_object_key,thumbnail_object_key,mime_type,
                 width,height,duration_seconds,file_size_bytes,moderation_status,is_safe,safety_score,
                 adult_score,violence_score,weapon_score,toxicity_score,moderation_reason)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING asset_id""",
            (
                dataset_version, str(row["id"]).strip(), str(row["archive_file"]).strip(),
                str(row["filename"]).strip(), sha256, str(row["media_type"]).strip().upper(),
                original_ref, delivery_ref, poster_ref, poster_ref, mime_type,
                _int(row.get("width")), _int(row.get("height")),
                _float(row.get("duration_seconds")) if row.get("duration_seconds") else None,
                _int(row.get("file_size_bytes")), status, status == "ALLOWED",
                max(0.0, min(1.0, _float(row.get("safety_score")))),
                max(0.0, min(1.0, _float(model_signals.get("adult_score"), _float(row.get("adult_score"))))),
                max(0.0, min(1.0, _float(model_signals.get("violence_score")))),
                max(0.0, min(1.0, _float(model_signals.get("weapon_score")))),
                max(0.0, min(1.0, _float(model_signals.get("toxicity_score")))),
                str(getattr(decision, "reason", "") or row.get("safety_reason") or ""),
            ),
        )
        asset = cur.fetchone()
        asset_id = asset["asset_id"] if isinstance(asset, dict) else asset[0]

        cur.execute(
            """INSERT INTO curated_content(
                 asset_id,category_id,title,caption,audience_age_group,min_age,max_age,is_reel,is_story,
                 destination_tab,publish_status,published_at)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CASE WHEN %s='PUBLISHED' THEN NOW() ELSE NULL END)
               RETURNING content_id""",
            (
                asset_id, category_id, str(row.get("title") or "").strip(),
                str(row.get("caption") or "").strip(), age_group, min_age, max_age,
                _bool(row.get("is_reel")), _bool(row.get("is_story")),
                str(row.get("app_destination_tab") or "feed").strip(), publish_status, publish_status,
            ),
        )
        content = cur.fetchone()
        content_id = content["content_id"] if isinstance(content, dict) else content[0]
        for tag in _hashtags(str(row.get("hashtags") or "")):
            cur.execute("INSERT INTO hashtags(tag) VALUES(%s) ON CONFLICT DO NOTHING", (tag,))
            cur.execute("SELECT hashtag_id FROM hashtags WHERE LOWER(tag)=LOWER(%s)", (tag,))
            tag_row = cur.fetchone()
            hashtag_id = tag_row["hashtag_id"] if isinstance(tag_row, dict) else tag_row[0]
            cur.execute(
                "INSERT INTO curated_content_hashtags(content_id,hashtag_id) VALUES(%s,%s) ON CONFLICT DO NOTHING",
                (content_id, hashtag_id),
            )
        conn.commit()
        return content_id, publish_status
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ingest(csv_path: Path, archives_dir: Path, dataset_version: str, *, dry_run: bool, publish: bool) -> dict[str, Any]:
    rows = _validate_csv(csv_path)
    report: dict[str, Any] = {
        "dataset_version": dataset_version,
        "source_rows": len(rows),
        "expected_allowed": 194,
        "expected_blocked": 12,
        "verified_blocked": 0,
        "blocked_benchmark_failures": [],
        "ingested": 0,
        "review": 0,
        "duplicates": 0,
        "failures": [],
        "dry_run": dry_run,
        "published": bool(publish and not dry_run),
    }

    from safety.moderation_service import evaluate
    from safety.pii_service import scan_pii

    if not dry_run:
        from services.object_storage import delete_reference, upload_file

    with tempfile.TemporaryDirectory(prefix="littlenet-curated-") as tmp:
        temp_dir = Path(tmp)
        for index, row in enumerate(rows, start=1):
            source: Path | None = None
            uploaded: list[str] = []
            try:
                source = _materialize_source(row, archives_dir, temp_dir)
                actual_size = source.stat().st_size
                expected_size = _int(row.get("file_size_bytes"))
                if expected_size and actual_size != expected_size:
                    raise ValueError(f"size mismatch: CSV={expected_size}, actual={actual_size}")
                sha256 = _sha256(source)
                expected_status = str(row.get("moderation_status") or "").strip().upper()
                expected_safe = _bool(row.get("is_safe"))
                if expected_status == "ALLOWED" and not expected_safe:
                    raise ValueError("ALLOWED row is not marked safe in master CSV")
                if expected_status == "BLOCKED" and expected_safe:
                    raise ValueError("BLOCKED row is marked safe in master CSV")

                caption = str(row.get("caption") or "").strip()
                if scan_pii(caption).get("detected"):
                    raise ValueError("caption contains PII according to current LittleNet policy")

                media_type = str(row.get("media_type") or "").strip().upper()
                if media_type not in {"IMAGE", "VIDEO"}:
                    raise ValueError(f"unsupported media_type: {media_type}")
                signals, decision = evaluate(0, media_type, str(source))

                if expected_status == "BLOCKED":
                    # Benchmark content never enters the production object store or catalog.
                    if decision.action == "BLOCK":
                        report["verified_blocked"] += 1
                    else:
                        report["blocked_benchmark_failures"].append({
                            "id": row.get("id"), "filename": row.get("filename"),
                            "decision": decision.action,
                        })
                    continue

                if decision.action == "BLOCK":
                    raise RuntimeError("expected-safe item is BLOCKED by current runtime moderation")

                existing = _asset_exists(sha256)
                if existing:
                    report["duplicates"] += 1
                    continue

                category = _category(row)
                if dry_run:
                    if decision.action == "REVIEW":
                        report["review"] += 1
                    else:
                        report["ingested"] += 1
                    continue

                ext = source.suffix.lower() or (".mp4" if media_type == "VIDEO" else ".bin")
                prefix = f"curated/{dataset_version}/{category.lower().replace(' & ', '-and-').replace(' ', '-')}/{sha256[:2]}/{sha256}"

                original_ref = upload_file(str(source), f"{prefix}/original{ext}")
                uploaded.append(original_ref)
                delivery_path = source
                poster_path: Path | None = None
                if media_type == "VIDEO" and _bool(row.get("is_reel")):
                    delivery_path, poster_path = _make_reel_delivery(source, temp_dir)
                delivery_ext = delivery_path.suffix.lower() or ext
                delivery_ref = upload_file(str(delivery_path), f"{prefix}/delivery{delivery_ext}")
                uploaded.append(delivery_ref)
                poster_ref = None
                if poster_path and poster_path.is_file():
                    poster_ref = upload_file(str(poster_path), f"{prefix}/poster.webp", "image/webp")
                    uploaded.append(poster_ref)

                mime_type = mimetypes.guess_type(str(delivery_path))[0] or (
                    "video/mp4" if media_type == "VIDEO" else "application/octet-stream"
                )
                _, publish_status = _insert_catalog_row(
                    row=row, sha256=sha256, category=category,
                    original_ref=original_ref, delivery_ref=delivery_ref, poster_ref=poster_ref,
                    mime_type=mime_type, model_signals=signals, decision=decision,
                    dataset_version=dataset_version, publish=publish,
                )
                if publish_status == "PUBLISHED":
                    report["ingested"] += 1
                else:
                    report["review"] += 1
            except Exception as exc:
                if not dry_run and uploaded:
                    for reference in reversed(uploaded):
                        try:
                            delete_reference(reference)
                        except Exception:
                            pass
                report["failures"].append({
                    "row": index,
                    "id": row.get("id"),
                    "archive": row.get("archive_file"),
                    "filename": row.get("filename"),
                    "error": f"{type(exc).__name__}: {exc}",
                })

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest the audited LittleNet curated multimedia dataset")
    parser.add_argument("--csv", required=True, type=Path, help="24-column master CSV")
    parser.add_argument("--archives-dir", required=True, type=Path, help="directory containing the six ZIP archives")
    parser.add_argument("--dataset-version", default="v1")
    parser.add_argument("--dry-run", action="store_true", help="validate and re-moderate without R2/DB writes")
    parser.add_argument("--publish", action="store_true", help="publish ALLOWED items immediately after successful ingest")
    parser.add_argument("--report", type=Path, default=Path("dataset_ingestion_report.json"))
    args = parser.parse_args()

    if not args.csv.is_file():
        parser.error(f"CSV not found: {args.csv}")
    if not args.archives_dir.is_dir():
        parser.error(f"archives directory not found: {args.archives_dir}")
    if args.dry_run and args.publish:
        parser.error("--publish cannot be used together with --dry-run")

    report = ingest(
        args.csv, args.archives_dir, args.dataset_version,
        dry_run=args.dry_run, publish=args.publish,
    )
    args.report.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))

    if report["failures"] or report["blocked_benchmark_failures"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
