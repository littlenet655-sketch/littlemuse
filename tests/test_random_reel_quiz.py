"""Comprehensive verification for LittleNet random Reel Brain Break and optional Quiz Zone."""
import secrets
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_random_threshold_bounds_and_distribution():
    from quiz.service import roll_quiz_threshold, QUIZ_PACING_RANGES

    expected = {
        "FREQUENT": (2, 3, 4, 5),
        "BALANCED": (4, 5, 6, 7),
        "LIGHT": (7, 8, 9, 10),
    }
    assert QUIZ_PACING_RANGES == expected
    for policy, allowed in expected.items():
        observed = set()
        for _ in range(300):
            val = roll_quiz_threshold(policy=policy)
            assert val in set(allowed)
            observed.add(val)
        # Each four-value policy should exercise its full range over 300 rolls.
        assert observed == set(allowed)


def test_feed_quiz_interval_reads_persisted_threshold():
    from quiz.service import feed_quiz_interval

    # The exact threshold is a server-persisted latch. Parent policy changes
    # affect the NEXT roll only; they never rewrite the active threshold.
    with patch("quiz.service.setting", return_value={"quiz_pacing_policy": "LIGHT"}):
        for threshold in (2, 3, 4, 5, 6, 7, 8, 9, 10):
            assert feed_quiz_interval(123, row={"next_quiz_threshold": threshold}) == threshold

    # With no persisted threshold, roll from the active parent policy.
    with patch("quiz.service.setting", return_value={"quiz_pacing_policy": "LIGHT"}), \
         patch("secrets.choice", return_value=9):
        assert feed_quiz_interval(123, row={}) == 9


def test_threshold_persists_across_repeated_reads_no_reroll_on_refresh():
    from quiz.service import feed_quiz_state

    mock_row = {
        "posts_seen": 2,
        "quiz_required": False,
        "required_quiz_id": None,
        "required_at": None,
        "viewed_post_ids": ["POST:101", 101, "POST:102", 102],
        "next_quiz_threshold": 4,
    }

    with patch("quiz.service.fetch_one", return_value=mock_row), \
         patch("quiz.service.setting", return_value=None):
        # Refresh 1
        s1 = feed_quiz_state(99)
        assert s1["posts_seen"] == 2
        assert s1["next_quiz_threshold"] == 4
        assert s1["interval"] == 4
        assert s1["required"] is False

        # Refresh 2 (simulating app restart / new request)
        s2 = feed_quiz_state(99)
        assert s2["posts_seen"] == 2
        assert s2["next_quiz_threshold"] == 4
        assert s2["interval"] == 4
        assert s2["required"] is False


def test_reset_rolls_and_persists_new_random_threshold():
    from quiz.service import reset

    executed_queries = []

    def mock_execute(query, params=None):
        executed_queries.append((query, params))

    with patch("quiz.service.execute", side_effect=mock_execute), \
         patch("secrets.choice", return_value=3):
        new_thresh = reset(555)
        assert new_thresh == 3

    assert len(executed_queries) > 0
    query, params = executed_queries[0]
    assert "next_quiz_threshold" in query
    assert params == (555, 3, 3)


def test_unique_reel_counting_and_latching_contracts():
    from quiz.service import record_feed_view

    # Mock DB cursor to test row locking, deduplication, and atomic latch
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    # Initial state: posts_seen = 2, threshold = 3, quiz_required = False
    row_state = {
        "posts_seen": 2,
        "quiz_required": False,
        "required_quiz_id": None,
        "required_at": None,
        "viewed_post_ids": ["POST:1", 1, "POST:2", 2],
        "next_quiz_threshold": 3,
    }
    mock_cur.fetchone.return_value = row_state

    with patch("quiz.service.get_db_connection", return_value=mock_conn), \
         patch("quiz.service.fetch_one", return_value={"id": 3}), \
         patch("quiz.service.setting", return_value=None):
        # Watching Reel 3 should transition to required = True atomically
        res = record_feed_view(77, 3, source_type="POST")
        assert res["accepted"] is True
        assert res["posts_seen"] == 3
        assert res["required"] is True
        assert res["interval"] == 3
        assert res["next_quiz_threshold"] == 3

        # Verify UPDATE query called FOR UPDATE and set quiz_required=True
        update_calls = [c for c in mock_cur.execute.call_args_list if "UPDATE child_quiz_progress" in str(c)]
        assert len(update_calls) > 0


def test_duplicate_reel_does_not_increment_counter():
    from quiz.service import record_feed_view

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    # Post 1 is already in seen list
    row_state = {
        "posts_seen": 1,
        "quiz_required": False,
        "required_quiz_id": None,
        "required_at": None,
        "viewed_post_ids": ["POST:1", 1],
        "next_quiz_threshold": 4,
    }
    mock_cur.fetchone.return_value = row_state

    with patch("quiz.service.get_db_connection", return_value=mock_conn), \
         patch("quiz.service.fetch_one", return_value={"id": 1}), \
         patch("quiz.service.setting", return_value=None):
        res = record_feed_view(77, 1, source_type="POST")
        assert res["accepted"] is False
        assert res["posts_seen"] == 1
        assert res["required"] is False


def test_voluntary_quiz_isolation():
    from quiz.service import complete_required_feed_quiz

    # If quiz is not required, complete_required_feed_quiz returns False and never resets
    with patch("quiz.service.feed_quiz_state", return_value={
        "required": False,
        "quiz_id": None,
        "posts_seen": 2,
        "next_quiz_threshold": 4,
    }), patch("quiz.service.reset") as mock_reset:
        ok = complete_required_feed_quiz(100, 42)
        assert ok is False
        mock_reset.assert_not_called()


def test_wrong_answer_clears_compulsory_gate_without_infinite_loop():
    from quiz.service import record_feed_answer, complete_required_feed_quiz

    mock_quiz = {
        "quiz_id": 88,
        "age_group": "9-11",
        "correct_answer": "Tell a trusted adult",
        "explanation": "Always tell a trusted adult if you see something scary online.",
    }

    with patch("quiz.service.fetch_one", return_value=mock_quiz), \
         patch("quiz.service.age_group", return_value="9-11"), \
         patch("quiz.service.execute") as mock_exec:
        # Child selects the WRONG answer
        is_corr, corr_ans, xp, expl = record_feed_answer(123, 88, "Share with everyone")
        assert is_corr is False
        assert corr_ans == "Tell a trusted adult"
        assert xp == 0
        assert "trusted adult" in expl

        # Verify attempt was recorded in child_quiz_attempts
        attempt_call = [c for c in mock_exec.call_args_list if "child_quiz_attempts" in str(c)]
        assert len(attempt_call) > 0

    # Clearing the gate upon submitting authoritative answer
    with patch("quiz.service.feed_quiz_state", return_value={
        "required": True,
        "quiz_id": 88,
        "posts_seen": 3,
        "next_quiz_threshold": 3,
    }), patch("quiz.service.reset") as mock_reset:
        cleared = complete_required_feed_quiz(123, 88)
        assert cleared is True
        mock_reset.assert_called_once_with(123)


def test_static_fallback_when_k2_ai_unavailable():
    from quiz.service import next_feed_quiz

    fallback_quiz = {
        "quiz_id": 1,
        "age_group": "9-11",
        "question": "What is a strong password?",
        "option_a": "123456",
        "option_b": "password",
        "option_c": "Mix of letters, numbers & symbols",
        "option_d": "your name",
        "correct_answer": "Mix of letters, numbers & symbols",
    }

    # Simulate empty personalized pool, DB bank returns static question, K2 raises
    with patch("quiz.service.age_group", return_value="9-11"), \
         patch("quiz.service.fetch_one", side_effect=[
             None,  # personalized pool
             fallback_quiz,  # main quizzes table
             None,  # has_attempted
         ]):
        q = next_feed_quiz(42)
        assert q is not None
        assert q["quiz_id"] == 1
        assert q["question"] == "What is a strong password?"


def test_migration_and_schema_coherence():
    mig = text("db/migrations/20260923000002_random_reel_quiz_threshold.sql")
    assert "ALTER TABLE child_quiz_progress" in mig
    assert "next_quiz_threshold" in mig
    assert "CHECK (next_quiz_threshold BETWEEN 2 AND 5)" in mig or "CHECK(next_quiz_threshold BETWEEN 2 AND 5)" in mig

    schema = text("database/schema.sql")
    assert "next_quiz_threshold" in schema

    upgrade = text("database/upgrade.sql")
    assert "next_quiz_threshold" in upgrade


def test_mobile_compulsory_gate_is_reels_only_source_contract():
    api = text("mobile/api.py")
    feed = text("mobile_app/src/screens/kids/FeedScreen.tsx")
    reels = text("mobile_app/src/screens/kids/ReelsScreen.tsx")
    assert 'if surface == "REELS":' in api
    assert 'if surf == "REELS":' in api
    assert "withQuizBreaks(visibleItems" not in feed
    assert "withQuizBreaks(feed.items" not in reels
    assert "if (result.quiz_required)" in reels
    assert "impressionBatchRef.current.length >= 5" not in reels
