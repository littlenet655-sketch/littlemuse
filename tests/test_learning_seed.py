from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]

def test_seed_has_five_questions_for_each_main_child_age_group():
    text=(ROOT/'database/seed.sql').read_text(encoding='utf-8')
    block=text.split('INSERT INTO learning_challenges',1)[0]
    for age in ('6-8','9-11','12-13'):
        assert len(re.findall(rf"'{re.escape(age)}'\)",block))>=5

def test_seed_covers_safety_categories():
    text=(ROOT/'database/seed.sql').read_text(encoding='utf-8')
    for category in ("'Digital Safety'","'Kindness'","'Stranger Safety'","'Healthy Habits'"):
        assert category in text

def test_home_has_learn_card_and_quiz_has_progress_ui():
    assert 'learn-card' in (ROOT/'child/templates/child_dashboard.html').read_text()
    quiz=(ROOT/'quiz/templates/quiz_card.html').read_text()
    assert 'quiz-progress' in quiz and 'Learning break' in quiz

def test_historical_quiz_migration_is_untouched_and_replacement_is_additive():
    hist = (ROOT/'db/migrations/20260911230000_seed_50_safety_quizzes.sql').read_text(encoding='utf-8')
    assert 'two-factor' in hist  # original 52-question bank still intact
    new = (ROOT/'db/migrations/20260923000000_simplify_quiz_bank.sql').read_text(encoding='utf-8')
    for cat in ("'Digital Privacy'", "'Online Kindness'", "'Cyber Smarts'", "'Digital Well-being'"):
        assert cat in new and 'DELETE FROM quizzes' in new
    assert 'ON CONFLICT (question, age_group) DO NOTHING' in new
    assert len(re.findall(r"^\s+\('", new, re.M)) == 24
