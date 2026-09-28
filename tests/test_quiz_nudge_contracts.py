"""Non-blocking periodic quiz nudge contracts.

The periodic feed-quiz latch is a NUDGE, never a content lock:
- no mobile/web gate refuses or redirects on a due quiz,
- a due impression is accepted with HTTP 200 and quiz_required=True,
- quiz cadence/content (quiz/service.py) is untouched,
- safety, quiet-hours, screen-time, parent controls, and moderation blocks
  remain blocking.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding='utf-8')


def _child_gate_body():
    api = text('mobile/api.py')
    start = api.index('def _child_gate(')
    end = api.index('def _mobile_user_payload(')
    # Strip comments: only code-level identifiers count.
    lines = [ln for ln in api[start:end].splitlines() if not ln.strip().startswith('#')]
    return '\n'.join(lines)


def test_child_gate_never_refuses_on_quiz():
    body = _child_gate_body()
    # Code-level identifiers: the gate must not consult the quiz latch at all.
    assert 'quiz_required' not in body
    assert 'quiz_due' not in body
    assert 'feed_quiz_state' not in body
    assert ', 428' not in body
    assert 'error="quiz_required"' not in body


def test_child_gate_still_blocks_safety_controls():
    body = _child_gate_body()
    assert 'error="disabled_by_parent"' in body
    assert 'error="quiet_hours"' in body
    assert 'error="screen_time_limit"' in body
    assert ', 423' in body


def test_impression_accepted_when_due_with_200_and_nudge_signal():
    api = text('mobile/api.py')
    due = api.split('if view_res.get("required"):')[1].split('return jsonify(')[1]
    due = due.split(')')[0]
    assert 'ok=True' in due
    assert 'quiz_required=True' in due
    assert ', 428' not in due


def test_batch_impression_accepted_when_due_with_200_and_nudge_signal():
    api = text('mobile/api.py')
    block = api.split('if view_res.get("required"):')[2].split('batch_qs = feed_quiz_state(uid)')[0]
    assert 'quiz_required = True' in block
    assert ', 428' not in block


def test_quiz_required_is_signal_only():
    api = text('mobile/api.py')
    assert 'error="quiz_required"' not in api
    assert 'gate="quiz"' not in api


def test_child_surface_open_not_denied_by_quiz():
    surface = text('services/social.py')
    assert 'def child_surface_open' in surface
    start = surface.index('def _child_surface_open_uncached(')
    end = surface.index('def ', start + 10)
    body = surface[start:end]
    assert 'quiz_due' not in body
    assert 'quiz_required' not in body
    # Safety controls still deny.
    assert 'quiet_hours_state' in body


def test_web_reels_passes_quiz_due_and_renders_dismissible_card():
    routes = text('uploadPost/routes.py')
    assert 'quiz_due=quiz_due(' in routes
    tpl = text('uploadPost/templates/reels.html')
    assert '{% if loop.index == 2 and quiz_due %}' in tpl
    assert 'id="quiz-prompt-card"' in tpl
    assert 'dismissQuizPrompt' in tpl
    assert '/quiz/start/' in tpl
    # Never a full-page lock.
    assert 'quizLocked' not in tpl


def test_web_js_never_locks_scrolling_or_content():
    js = text('static/js/feed_quiz.js')
    assert 'overflow' not in js
    assert 'lockedOverlay' not in js
    assert 'mandatory' not in js.lower()
    assert 'Not now' in js


def test_quiz_cadence_and_content_untouched():
    service = text('quiz/service.py')
    assert 'def quiz_due' in service
    assert 'def record_feed_view' in service
    assert 'def required_feed_quiz' in service
    assert 'def complete_required_feed_quiz' in service
    assert 'FEED_QUIZ_INTERVAL = 5' in service
