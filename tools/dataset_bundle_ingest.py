"""Stage the uploaded two-part LittleNet dataset bundles for curated ingestion.

The collected dataset may arrive as one or more bundle ZIPs such as
LittleNet_Dataset_Part1_of_2.zip / Part2_of_2.zip. Each bundle contains the
master CSV plus category folders, while tools.dataset_ingest expects the original
six archive names declared in the CSV. This adapter reconstructs those archives
in a temporary directory, verifies exact completeness, and then delegates to the
curated ingestion pipeline.

Examples:
  python tools/dataset_bundle_ingest.py \
    --bundle LittleNet_Dataset_Part1_of_2.zip \
    --bundle LittleNet_Dataset_Part2_of_2.zip \
    --dataset-version v1

  python tools/dataset_bundle_ingest.py \
    --bundle LittleNet_Dataset_Part1_of_2.zip \
    --bundle LittleNet_Dataset_Part2_of_2.zip \
    --dataset-version v1 --execute --publish

Without --execute this performs a dry run only. Publication additionally requires
--publish so a normal execution cannot accidentally make catalog rows child-visible.
"""
from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import argparse
import csv
import hashlib
import io
import json
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

from tools.dataset_ingest import ingest

MASTER_CSV = "littlenet_dataset_captions.csv"
ARCHIVE_TO_FOLDER = {
    "family.zip": "family",
    "Member3Animals.zip": "Member3Animals",
    "Member3Crafts&Hobbies.zip": "Member3Crafts&Hobbies",
    "Member3Gardening.zip": "Member3Gardening",
    "Member3Cooking.zip": "Member3Cooking",
    "18+images.zip": "18+images",
}
EXPECTED_COUNTS = {
    "family.zip": 74,
    "Member3Animals.zip": 58,
    "Member3Crafts&Hobbies.zip": 26,
    "Member3Gardening.zip": 21,
    "Member3Cooking.zip": 15,
    "18+images.zip": 12,
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_bundle(path: Path) -> tuple[zipfile.ZipFile, bytes | None]:
    zf = zipfile.ZipFile(path, "r")
    csv_bytes = None
    for name in zf.namelist():
        if Path(name).name == MASTER_CSV:
            candidate = zf.read(name)
            if csv_bytes is not None and candidate != csv_bytes:
                zf.close()
                raise ValueError(f"bundle {path} contains multiple different master CSV files")
            csv_bytes = candidate
    return zf, csv_bytes


def _rows(csv_bytes: bytes) -> list[dict[str, str]]:
    text = csv_bytes.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    if len(rows) != 206:
        raise ValueError(f"expected 206 rows in master CSV, found {len(rows)}")
    counts = Counter(row.get("archive_file") for row in rows)
    if dict(counts) != EXPECTED_COUNTS:
        raise ValueError(f"unexpected archive counts in master CSV: {dict(counts)}")
    return rows


def _find_member(zf: zipfile.ZipFile, folder: str, filename: str) -> str | None:
    exact = f"{folder}/{filename}".replace("\\", "/")
    names = set(zf.namelist())
    if exact in names:
        return exact
    suffix = "/" + exact
    matches = [name for name in zf.namelist() if name.replace("\\", "/").endswith(suffix)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise RuntimeError(f"ambiguous bundle member for {exact}: {matches[:5]}")
    return None


def stage_bundles(bundle_paths: list[Path], staging_root: Path) -> tuple[Path, Path, dict]:
    bundles: list[tuple[Path, zipfile.ZipFile]] = []
    master_csv: bytes | None = None
    master_hash: str | None = None

    try:
        for path in bundle_paths:
            if not path.is_file():
                raise FileNotFoundError(path)
            zf, csv_bytes = _load_bundle(path)
            bundles.append((path, zf))
            if csv_bytes is not None:
                digest = _sha256_bytes(csv_bytes)
                if master_csv is None:
                    master_csv, master_hash = csv_bytes, digest
                elif digest != master_hash:
                    raise ValueError("bundle ZIPs contain different master CSV versions")

        if master_csv is None:
            raise FileNotFoundError(f"{MASTER_CSV} not found in any supplied bundle")

        rows = _rows(master_csv)
        archives_dir = staging_root / "archives"
        archives_dir.mkdir(parents=True, exist_ok=True)
        csv_path = staging_root / MASTER_CSV
        csv_path.write_bytes(master_csv)

        writers = {
            archive: zipfile.ZipFile(archives_dir / archive, "w", zipfile.ZIP_DEFLATED)
            for archive in ARCHIVE_TO_FOLDER
        }
        found_counts = Counter()
        hashes: dict[str, str] = {}
        missing: list[dict] = []

        try:
            for row in rows:
                archive = str(row["archive_file"]).strip()
                filename = str(row["filename"]).strip().replace("\\", "/")
                folder = ARCHIVE_TO_FOLDER.get(archive)
                if folder is None:
                    raise ValueError(f"unsupported archive_file {archive!r}")

                candidates: list[tuple[Path, zipfile.ZipFile, str]] = []
                for bundle_path, zf in bundles:
                    member = _find_member(zf, folder, filename)
                    if member:
                        candidates.append((bundle_path, zf, member))

                if not candidates:
                    missing.append({"archive_file": archive, "filename": filename})
                    continue
                if len(candidates) > 1:
                    locations = [f"{p}:{m}" for p, _zf, m in candidates]
                    raise RuntimeError(f"dataset media duplicated across bundles: {locations}")

                _bundle_path, zf, member = candidates[0]
                payload = zf.read(member)
                digest = _sha256_bytes(payload)
                prior = hashes.get(digest)
                if prior is not None:
                    raise RuntimeError(f"duplicate media bytes detected: {prior!r} and {filename!r}")
                hashes[digest] = filename
                writers[archive].writestr(filename, payload)
                found_counts[archive] += 1
        finally:
            for writer in writers.values():
                writer.close()

        report = {
            "bundles": [str(p) for p in bundle_paths],
            "master_csv_sha256": master_hash,
            "expected_total": 206,
            "found_total": sum(found_counts.values()),
            "missing_total": len(missing),
            "expected_by_archive": EXPECTED_COUNTS,
            "found_by_archive": dict(found_counts),
            "missing": missing,
        }
        (staging_root / "bundle_stage_report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )

        if missing:
            sample = missing[:10]
            raise RuntimeError(
                f"dataset bundles incomplete: {len(missing)} of 206 files are missing; sample={sample}"
            )
        if dict(found_counts) != EXPECTED_COUNTS:
            raise RuntimeError(f"unexpected reconstructed archive counts: {dict(found_counts)}")

        return csv_path, archives_dir, report
    finally:
        for _path, zf in bundles:
            zf.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", action="append", required=True, help="Path to one bundle ZIP; repeat for part 2")
    parser.add_argument("--dataset-version", default="v1")
    parser.add_argument("--execute", action="store_true", help="Actually upload/insert; default is dry-run")
    parser.add_argument("--publish", action="store_true", help="Publish ALLOWED rows; requires --execute")
    parser.add_argument("--report-out", default="dataset_bundle_ingest_report.json")
    args = parser.parse_args()

    if args.publish and not args.execute:
        parser.error("--publish requires --execute")

    with tempfile.TemporaryDirectory(prefix="littlenet-dataset-stage-") as temp:
        csv_path, archives_dir, stage_report = stage_bundles(
            [Path(p).resolve() for p in args.bundle], Path(temp)
        )
        ingest_report = ingest(
            csv_path,
            archives_dir,
            args.dataset_version,
            dry_run=not args.execute,
            publish=bool(args.publish),
        )

    result = {"stage": stage_report, "ingest": ingest_report}
    Path(args.report_out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
