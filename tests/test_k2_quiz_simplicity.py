"""K2-generated quiz questions must stay age-tailored and structurally valid."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding='utf-8')


def make_question(**overrides):
    from services.ai.schemas import GeneratedQuestion
    base = dict(
        category="Digital Safety",
        question="What should you do if a stranger asks for your photo?",
        option_a="Say no and tell a parent",
        option_b="Send the photo",
        option_c="Ask them for theirs",
        option_d="Ignore and keep chatting",
        correct_answer="Say no and tell a parent",
        difficulty="EASY",
    )
    base.update(overrides)
    return GeneratedQuestion(**base)


def test_k2_prompt_is_age_tailored_and_structurally_bounded():
    prompt = text('services/ai/client.py')

    # The current generator intentionally varies topics/difficulty by age instead
    # of forcing the old one-size-fits-all "SIMPLICITY RULES" prompt.
    assert "CRITICAL INSTRUCTION FOR AGE 6-8" in prompt
    assert "INSTRUCTION FOR AGE 9-11" in prompt
    assert "INSTRUCTION FOR AGE 12-13" in prompt
    assert "INSTRUCTION FOR AGE 14-18" in prompt

    # Younger children retain the strictest short-option wording.
    assert "under 40 characters" in prompt
    assert "DO NOT ask complex scientific, technical, or historical questions" in prompt

    # Every generated age band must still obey the same MCQ integrity contract.
    assert "Exactly 4 distinct options" in prompt
    assert "correct_answer must EXACTLY match one of the 4 options verbatim" in prompt
    assert "Strict educational value and age appropriateness" in prompt
    assert "DO NOT repeat or duplicate any of these questions" in prompt

    # Representative age-specific curriculum anchors.
    for marker in (
        "Animals & Pets",
        "Online Safety",
        "Smart Internet Habits",
        "Cyber Safety & Privacy",
    ):
        assert marker in prompt


def test_simple_question_passes_validation():
    from quiz.learning_service import _question_is_simple_enough
    assert _question_is_simple_enough(make_question()) is True


def test_long_question_is_dropped():
    from quiz.learning_service import _question_is_simple_enough
    assert _question_is_simple_enough(make_question(question="What " * 60 + "?")) is False


def test_duplicate_options_are_dropped():
    from quiz.learning_service import _question_is_simple_enough
    q = make_question(option_b="Say no and tell a parent")
    assert _question_is_simple_enough(q) is False


def test_long_option_is_dropped():
    from quiz.learning_service import _question_is_simple_enough
    long_opt = "A very long option " * 10
    q = make_question(option_a=long_opt, correct_answer=long_opt)
    assert _question_is_simple_enough(q) is False


def test_missing_category_is_dropped():
    from quiz.learning_service import _question_is_simple_enough
    q = make_question(category="  ")
    assert _question_is_simple_enough(q) is False


def test_refill_path_filters_before_insert():
    service = text('quiz/learning_service.py')
    assert "_question_is_simple_enough" in service
    assert "def _refill_bank_async" in service
    # Filter is applied inside the worker loop before execute().
    worker = service.split("def _refill_bank_async")[1].split("def _refill_language_drills_async")[0]
    assert "if not _question_is_simple_enough(q):" in worker
    assert "continue" in worker
