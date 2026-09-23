import threading
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from database.connection import fetch_one, fetch_all, execute
from services.ai import get_ai_client

logger = logging.getLogger("littlenet.quiz.learning")

# ─── 1. Deterministic Adaptive Difficulty ─────────────────────────────────────

def compute_adaptive_difficulty(recent_attempts: List[bool], default: str = "MEDIUM") -> str:
    """Pure calculation of adaptive difficulty from a boolean sequence of recent attempts."""
    if not recent_attempts or len(recent_attempts) < 3:
        return default
    correct_count = sum(1 for r in recent_attempts if r)
    accuracy = correct_count / len(recent_attempts)
    if accuracy >= 0.80:
        return "HARD" if default in ("MEDIUM", "HARD") else "MEDIUM"
    elif accuracy >= 0.50:
        return "MEDIUM"
    return "EASY" if default in ("EASY", "MEDIUM") else "MEDIUM"

def calculate_next_srs_review(was_correct: bool, current_streak: int = 0) -> datetime:
    """Pure calculation of spaced repetition review interval."""
    now = datetime.utcnow()
    if not was_correct:
        return now + timedelta(minutes=15)
    if current_streak <= 1:
        return now + timedelta(days=1)
    elif current_streak == 2:
        return now + timedelta(days=3)
    elif current_streak == 3:
        return now + timedelta(days=7)
    return now + timedelta(days=14)

def normalize_question_stem(stem: str) -> str:
    """Normalizes question text to prevent duplicate quiz generation."""
    import re
    cleaned = re.sub(r'[^\w\s]', '', (stem or '').lower())
    return ' '.join(cleaned.split())

def get_child_difficulty_level(child_id: int) -> str:
    """
    Calculates child's current mastery level based on last 10 quiz attempts.
    High accuracy (>=80%) -> HARD
    Moderate accuracy (50-79%) -> MEDIUM
    Low accuracy (<50%) -> EASY
    """
    rows = fetch_all(
        '''SELECT is_correct FROM child_quiz_attempts
           WHERE child_id=%s
           ORDER BY attempted_at DESC LIMIT 10''',
        (child_id,)
    )
    if not rows or len(rows) < 3:
        return "MEDIUM"  # Balanced default for early attempts

    attempts = [bool(r.get('is_correct')) for r in rows]
    return compute_adaptive_difficulty(attempts, default="MEDIUM")

# ─── 2. Spaced Repetition System (SRS) for Vocabulary ────────────────────────

def record_vocabulary_attempt(child_id: int, word: str, language: str, is_correct: bool):
    """
    Deterministic Spaced Repetition algorithm for language learning.
    Intervals:
      Incorrect: review immediately (4 hours)
      1 correct: 1 day
      2 correct: 3 days
      3+ correct: 7 days (Mastered)
    """
    if not word or not language:
        return

    now = datetime.now()
    existing = fetch_one(
        'SELECT * FROM child_vocabulary_progress WHERE child_id=%s AND word=%s AND language=%s',
        (child_id, word, language)
    )

    if not existing:
        next_due = now + (timedelta(days=1) if is_correct else timedelta(hours=4))
        mastery = 'LEARNING' if is_correct else 'REVIEW_NEEDED'
        execute(
            '''INSERT INTO child_vocabulary_progress(child_id, word, language, times_seen, times_correct, last_tested_at, next_review_due, mastery_level)
               VALUES(%s, %s, %s, 1, %s, NOW(), %s, %s)
               ON CONFLICT(child_id, word, language) DO NOTHING''',
            (child_id, word, language, 1 if is_correct else 0, next_due, mastery)
        )
    else:
        new_seen = existing['times_seen'] + 1
        new_correct = existing['times_correct'] + (1 if is_correct else 0)

        if not is_correct:
            next_due = now + timedelta(hours=4)
            mastery = 'REVIEW_NEEDED'
        else:
            if new_correct == 1:
                next_due = now + timedelta(days=1)
                mastery = 'LEARNING'
            elif new_correct == 2:
                next_due = now + timedelta(days=3)
                mastery = 'PRACTICING'
            else:
                next_due = now + timedelta(days=7)
                mastery = 'MASTERED'

        execute(
            '''UPDATE child_vocabulary_progress
               SET times_seen=%s, times_correct=%s, last_tested_at=NOW(), next_review_due=%s, mastery_level=%s
               WHERE progress_id=%s''',
            (new_seen, new_correct, next_due, mastery, existing['progress_id'])
        )

def get_due_vocabulary(child_id: int, language: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
    """Returns vocabulary words currently due for spaced review."""
    if language:
        return fetch_all(
            '''SELECT * FROM child_vocabulary_progress
               WHERE child_id=%s AND language=%s AND next_review_due <= NOW()
               ORDER BY next_review_due ASC LIMIT %s''',
            (child_id, language, limit)
        )
    return fetch_all(
        '''SELECT * FROM child_vocabulary_progress
           WHERE child_id=%s AND next_review_due <= NOW()
           ORDER BY next_review_due ASC LIMIT %s''',
        (child_id, limit)
    )

# ─── 3. Asynchronous Question Refill & Personalization ────────────────────────

def _question_is_simple_enough(q) -> bool:
    """Defense-in-depth: drop K2-generated questions that violate the simplicity rules."""
    stem = (q.question or "").strip()
    opts = [(q.option_a or "").strip(), (q.option_b or "").strip(),
            (q.option_c or "").strip(), (q.option_d or "").strip()]
    ans = (q.correct_answer or "").strip()
    if not stem or len(stem) > 160:
        return False
    if any(not o or len(o) > 60 for o in opts):
        return False
    if len({o.lower() for o in opts}) != 4:
        return False
    if ans not in opts:
        return False
    if not (q.category or "").strip():
        return False
    return True


def _refill_bank_async(age_group: str, grade_level: str = "Grade 4"):
    """Runs batch quiz generation in a background worker thread."""
    def worker():
        try:
            client = get_ai_client()
            if not client.is_k2_available():
                return
            res = client.generate_quiz_batch(age_group=age_group, grade_level=grade_level, count=15)
            kept = 0
            for q in res.questions:
                if not _question_is_simple_enough(q):
                    logger.info("Dropping K2 question that failed simplicity check: %.60s", q.question)
                    continue
                kept += 1
                execute(
                    '''INSERT INTO quizzes(category, question, option_a, option_b, option_c, option_d,
                                           correct_answer, age_group, explanation, difficulty_level, language, source)
                       VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'K2_BATCH')
                       ON CONFLICT(question, age_group) DO NOTHING''',
                    (q.category, q.question, q.option_a, q.option_b, q.option_c, q.option_d,
                     q.correct_answer, age_group, q.explanation, q.difficulty, q.language)
                )
            logger.info("Asynchronously refilled %d questions for age group %s", kept, age_group)
        except Exception as e:
            logger.warning("Background quiz refill failed: %s", e)

    t = threading.Thread(target=worker, daemon=True)
    t.start()

def _refill_language_drills_async(target_language: str = "kn", age_group: str = "9-11"):
    """Runs background generation of language exercises (Kannada/Hindi)."""
    def worker():
        try:
            client = get_ai_client()
            if not client.is_k2_available():
                return
            res = client.generate_language_drills(target_language=target_language, learner_age_group=age_group, count=8)
            for d in res.drills:
                execute(
                    '''INSERT INTO quizzes(category, question, option_a, option_b, option_c, option_d,
                                           correct_answer, age_group, question_type, explanation, difficulty_level,
                                           language, vocabulary_word, native_script, source)
                       VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'K2_DRILL')
                       ON CONFLICT(question, age_group) DO NOTHING''',
                    (f"Language: {target_language.upper()}", d.question, d.option_a, d.option_b, d.option_c, d.option_d,
                     d.correct_answer, age_group, d.drill_type, d.fun_fact, d.difficulty,
                     d.language, d.word_english, d.native_script)
                )
            logger.info("Asynchronously refilled %d %s drills for age %s", len(res.drills), target_language, age_group)
        except Exception as e:
            logger.warning("Background language refill failed: %s", e)

    t = threading.Thread(target=worker, daemon=True)
    t.start()

def trigger_background_refill_if_needed(age_group: str, child_id: int):
    """
    Checks if question pool is running low (< 10 questions).
    Fires background refill without blocking the calling thread.
    """
    row = fetch_one(
        '''SELECT COUNT(*) as c FROM quizzes
           WHERE age_group=%s AND quiz_id NOT IN (
               SELECT quiz_id FROM child_quiz_attempts WHERE child_id=%s
           )''',
        (age_group, child_id)
    )
    unseen = int((row or {}).get('c', 0))
    if unseen < 10:
        _refill_bank_async(age_group)
        _refill_language_drills_async('kn', age_group)

def populate_child_personalized_pool(child_id: int, age_group: str):
    """
    Pre-populates child_personalized_quiz_pool with questions aligned to child's
    approved interests, skills, or ambition tags.
    """
    interests = fetch_all(
        '''SELECT interest_name FROM child_interests WHERE child_id=%s AND approved=TRUE
           UNION SELECT skill_name FROM child_skills WHERE child_id=%s AND approved=TRUE
           UNION SELECT ambition_name FROM child_ambitions WHERE child_id=%s AND approved=TRUE''',
        (child_id, child_id, child_id)
    )
    tags = [r.get('interest_name') for r in interests if r.get('interest_name')]

    if not tags:
        return

    # Find matching questions in existing bank
    for tag in tags[:5]:
        pattern = f"%{tag}%"
        matches = fetch_all(
            '''SELECT quiz_id FROM quizzes
               WHERE age_group=%s AND (category ILIKE %s OR question ILIKE %s)
                 AND quiz_id NOT IN (SELECT quiz_id FROM child_quiz_attempts WHERE child_id=%s)
               LIMIT 3''',
            (age_group, pattern, pattern, child_id)
        )
        for m in matches:
            execute(
                '''INSERT INTO child_personalized_quiz_pool(child_id, quiz_id, reason_for_selection)
                   VALUES(%s, %s, %s)
                   ON CONFLICT(child_id, quiz_id) DO NOTHING''',
                (child_id, m['quiz_id'], f"Matches interest in {tag}")
            )
