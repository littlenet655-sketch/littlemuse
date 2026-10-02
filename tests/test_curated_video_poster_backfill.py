from unittest.mock import patch


def test_curated_poster_backfill_dry_run_never_writes():
    from tools import backfill_curated_video_posters as tool

    row = {
        "asset_id": "00000000-0000-0000-0000-000000000001",
        "delivery_object_key": "uploads/r2/curated/v1/family/aa/hash/delivery.mp4",
        "poster_object_key": None,
        "moderation_status": "ALLOWED",
        "is_safe": True,
    }

    with patch.object(tool, "candidates", return_value=[row]),          patch.object(tool.object_storage, "head_object", return_value={"content_length": 100}),          patch.object(tool.object_storage, "download_file") as download,          patch.object(tool.object_storage, "upload_file") as upload,          patch.object(tool, "execute") as execute:
        report = tool.run(apply=False, limit=10)

    assert report["candidates"] == 1
    assert report["generated"] == 0
    assert report["items"][0]["status"] == "DRY_RUN"
    download.assert_not_called()
    upload.assert_not_called()
    execute.assert_not_called()


def test_curated_poster_backfill_skips_missing_delivery_object():
    from tools import backfill_curated_video_posters as tool

    row = {
        "asset_id": "00000000-0000-0000-0000-000000000002",
        "delivery_object_key": "uploads/r2/curated/v1/family/bb/hash/delivery.mp4",
        "poster_object_key": None,
        "moderation_status": "ALLOWED",
        "is_safe": True,
    }

    with patch.object(tool, "candidates", return_value=[row]),          patch.object(tool.object_storage, "head_object", return_value=None),          patch.object(tool.object_storage, "upload_file") as upload,          patch.object(tool, "execute") as execute:
        report = tool.run(apply=True, limit=10)

    assert report["skipped_missing_video"] == 1
    assert report["items"][0]["status"] == "MISSING_VIDEO"
    upload.assert_not_called()
    execute.assert_not_called()


def test_poster_key_stays_with_curated_asset_prefix():
    from tools.backfill_curated_video_posters import _poster_key

    assert _poster_key("uploads/r2/curated/v1/family/aa/hash/delivery.mp4") == (
        "curated/v1/family/aa/hash/poster.jpg"
    )
