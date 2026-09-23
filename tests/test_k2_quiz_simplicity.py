"""K2-generated quiz questions must be simple, short, and structurally valid."""
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


def test_k2_prompt_demands_simple_questions():
    prompt = text('services/ai/client.py')
    assert "SIMPLICITY RULES" in prompt
    assert "under 120 characters" in prompt
    assert "under 40 characters" in prompt
    assert '"difficulty": \\"EASY\\"' in prompt or "'EASY'" in prompt
    for cat in ("Digital Safety", "Kindness", "Stranger Safety", "Healthy Habits"):
        assert cat in prompt


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
    # filter is applied inside the worker loop before execute()
    worker = service.split("def _refill_bank_async")[1].split("def _refill_language_drills_async")[0]
    assert "if not _question_is_simple_enough(q):" in worker
    assert "continue" in worker
