"""Final periodic Reel-quiz contracts.

The latch is compulsory inside Reels but never a global Kids Mode/startup gate.
A server-persisted threshold from 2-5 meaningful Reel views triggers the break.
Wrong answers keep the latch active. Optional Learn/Quiz Zone practice never
clears or changes that compulsory latch.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def _child_gate_body():
    api = text("mobile/api.py")
    start = api.index("def _child_gate(")
    end = api.index("def _asset_url(", start)
    lines = [ln for ln in api[start:end].splitlines() if not ln.strip().startswith("#")]
    return "\n".join(lines)


def test_quiz_is_not_a_global_child_gate():
    body = _child_gate_body()
    assert "quiz_required" not in body
    assert "quiz_due" not in body
    assert "feed_quiz_state" not in body
    assert 'error="disabled_by_parent"' in body
    assert 'error="quiet_hours"' in body
    assert 'error="screen_time_limit"' in body
    assert 'error="parent_paused"' in body


def test_reel_impression_returns_due_signal_without_global_428():
    api = text("mobile/api.py")
    assert 'quiz_required=True' in api
    assert 'gate="quiz"' not in api
    # Server-side enforcement (2026-09-29): reels/playback endpoints ARE the
    # final authority and return error="quiz_required" (428) when the latch is
    # active. The impression endpoint still signals without 428; enforcement
    # is scoped to reels surfaces, never a global app gate.
    assert 'error="quiz_required"' in api


def test_server_cadence_is_random_two_to_five_and_persisted():
    service = text("quiz/service.py")
    assert "ALLOWED_QUIZ_THRESHOLDS = (2, 3, 4, 5)" in service
    assert "'FREQUENT': (2, 3, 4, 5)" in service
    assert "'BALANCED': (2, 3, 4, 5)" in service
    assert "'LIGHT': (2, 3, 4, 5)" in service
    assert "next_quiz_threshold" in service
    assert "secrets.choice(values)" in service


def test_wrong_required_answer_does_not_unlock():
    api = text("mobile/api.py")
    assert "if (not practice_mode) and correct and state.get(\"required\")" in api
    assert "complete_required_feed_quiz(uid, quiz_id)" in api
    quiz = text("mobile_app/src/screens/Quiz.tsx")
    assert "if (required)" in quiz
    assert "stays on this question after a wrong answer" in quiz


def test_reels_auto_handoff_has_no_dismiss_path():
    reels = text("mobile_app/src/screens/kids/ReelsScreen.tsx")
    prompt = text("mobile_app/src/components/QuizPromptCard.tsx")
    assert "setPaused(true)" in reels
    assert "nav.navigate('Quiz', { returnTo: 'ReelsTab', autoStart: true })" in reels
    assert "onDismiss=" not in reels
    assert "onDismiss" not in prompt
    assert "Answer to Continue" in prompt


def test_learn_quiz_zone_is_optional_and_isolated_from_latch():
    feed = text("mobile_app/src/screens/kids/FeedScreen.tsx")
    quiz = text("mobile_app/src/screens/Quiz.tsx")
    api = text("mobile/api.py")
    assert "QuizPromoCard" in feed
    assert "tab === 'Learn'" in feed
    assert "practiceMode" in quiz
    assert 'request.args.get("mode")' in api
    assert "and not practice_mode" in api
    assert "rows = rows[:n]" in api
