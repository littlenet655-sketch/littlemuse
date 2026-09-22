from unittest.mock import patch

from parent.service import viewing_insights


def test_viewing_insights_requires_owned_child():
    with patch("parent.service.owns", return_value=False), patch("parent.service.fetch_all") as fetch_all:
        assert viewing_insights(1, 2, 7) is None
        fetch_all.assert_not_called()


def test_viewing_insights_aggregates_surfaces_and_categories_without_content_ids():
    surface_rows = [
        {
            "surface": "FEED",
            "views": 4,
            "watched_ms": 120000,
            "completed": 1,
            "replays": 0,
            "liked": 1,
            "saved": 0,
        },
        {
            "surface": "REELS",
            "views": 5,
            "watched_ms": 300000,
            "completed": 4,
            "replays": 2,
            "liked": 2,
            "saved": 1,
        },
    ]
    category_rows = [
        {"category": "Science", "views": 5, "watched_ms": 240000},
        {"category": "Art", "views": 2, "watched_ms": 90000},
    ]
    with patch("parent.service.owns", return_value=True), patch(
        "parent.service.fetch_all", side_effect=[surface_rows, category_rows]
    ):
        result = viewing_insights(1, 2, 7)

    assert result["total_views"] == 9
    assert result["watched_minutes"] == 7.0
    assert result["reels"]["completion_rate"] == 80.0
    assert result["reels"]["replays"] == 2
    assert result["top_categories"][0] == {
        "category": "Science",
        "views": 5,
        "watched_minutes": 4.0,
    }
    # Parent insights deliberately expose aggregate supervision only.
    assert "source_id" not in str(result)
    assert "message" not in str(result).lower()
