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


# ─── 4. Non-Repeating Fresh Quiz Generation & Account Onboarding Refill ───────

def _procedural_fallback_quizzes(age_group: str, needed: int = 5, child_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Deterministic/procedural fallback generator. Guarantees that even if external AI
    is temporarily unreachable, the child is ALWAYS provided with fresh, non-repeating,
    age-appropriate questions with randomized parameters that have never been attempted.
    """
    import random
    from database.connection import get_db_connection

    # Attempted quiz IDs for this child
    attempted_ids = set()
    if child_id:
        rows = fetch_all('SELECT quiz_id FROM child_quiz_attempts WHERE child_id=%s', (child_id,))
        attempted_ids = {r['quiz_id'] for r in rows}

    fresh_rows = []
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            for _ in range(needed * 3):
                if len(fresh_rows) >= needed:
                    break

                if age_group == '6-8':
                    # Extremely simple questions for 6-8 year olds
                    templates = [
                        ("Math", "What is {a} + {b}?", lambda: (random.randint(1, 5), random.randint(1, 4))),
                        ("Colors", "What color is {item}?", lambda: random.choice([
                            ("a fresh green leaf", "Green", ["Green", "Blue", "Purple", "Pink"]),
                            ("a sweet ripe banana", "Yellow", ["Yellow", "Red", "Black", "Blue"]),
                            ("a bright red strawberry", "Red", ["Red", "Orange", "Green", "White"]),
                            ("the sunny daytime sky", "Blue", ["Blue", "Yellow", "Brown", "Purple"])
                        ])),
                        ("Animals", "Which animal says '{sound}'?", lambda: random.choice([
                            ("Moo", "Cow", ["Cow", "Duck", "Lion", "Cat"]),
                            ("Meow", "Cat", ["Cat", "Dog", "Horse", "Elephant"]),
                            ("Woof woof", "Dog", ["Dog", "Sheep", "Frog", "Fish"]),
                            ("Quack quack", "Duck", ["Duck", "Goat", "Tiger", "Rabbit"])
                        ])),
                        ("Habits", "What should you always do before eating meals?", lambda: (
                            "Wash your hands with soap",
                            ["Wash your hands with soap", "Go to sleep", "Play in the mud", "Run outside"]
                        )),
                        ("Counting", "How many legs does a dog have?", lambda: (
                            "4", ["4", "2", "6", "8"]
                        ))
                    ]
                    choice = random.choice(templates)
                    if choice[0] == "Math":
                        a, b = choice[2]()
                        correct = str(a + b)
                        wrong_pool = [str(x) for x in range(1, 12) if str(x) != correct]
                        random.shuffle(wrong_pool)
                        opts = [correct, wrong_pool[0], wrong_pool[1], wrong_pool[2]]
                        random.shuffle(opts)
                        q_text = f"What is {a} + {b}?"
                        expl = f"{a} plus {b} equals {correct}!"
                        cat = "Math"
                    elif choice[0] in ("Colors", "Animals"):
                        data = choice[2]()
                        if choice[0] == "Colors":
                            item, correct, opts = data
                            q_text = f"What color is {item}?"
                            expl = f"{item.capitalize()} is {correct.lower()}!"
                        else:
                            sound, correct, opts = data
                            q_text = f"Which animal says '{sound}'?"
                            expl = f"A {correct.lower()} says {sound.lower()}!"
                        random.shuffle(opts)
                        cat = choice[0]
                    else:
                        q_text = choice[1]
                        correct, opts = choice[2]()
                        random.shuffle(opts)
                        expl = "Staying clean and healthy keeps you energetic and happy!"
                        cat = choice[0]

                elif age_group == '9-11':
                    templates = [
                        ("Math", "What is {a} x {b}?", lambda: (random.randint(2, 9), random.randint(2, 9))),
                        ("Science", "Which planet is known as the {desc}?", lambda: random.choice([
                            ("Red Planet", "Mars", ["Mars", "Venus", "Jupiter", "Mercury"]),
                            ("largest planet in our Solar System", "Jupiter", ["Jupiter", "Saturn", "Neptune", "Earth"]),
                            ("closest planet to the Sun", "Mercury", ["Mercury", "Mars", "Venus", "Saturn"])
                        ])),
                        ("India GK", "What is the national animal of India?", lambda: (
                            "Bengal Tiger", ["Bengal Tiger", "Elephant", "Lion", "Leopard"]
                        )),
                        ("Nature", "What do honeybees collect from flowers to make honey?", lambda: (
                            "Nectar", ["Nectar", "Leaves", "Soil", "Bark"]
                        ))
                    ]
                    choice = random.choice(templates)
                    if choice[0] == "Math":
                        a, b = choice[2]()
                        correct = str(a * b)
                        wrong_pool = [str(x) for x in range(4, 90) if str(x) != correct]
                        random.shuffle(wrong_pool)
                        opts = [correct, wrong_pool[0], wrong_pool[1], wrong_pool[2]]
                        random.shuffle(opts)
                        q_text = f"What is {a} x {b}?"
                        expl = f"{a} multiplied by {b} equals {correct}!"
                        cat = "Mathematics"
                    elif choice[0] == "Science":
                        desc, correct, opts = choice[2]()
                        q_text = f"Which planet is known as the {desc}?"
                        expl = f"{correct} is famously known as the {desc}."
                        random.shuffle(opts)
                        cat = "Science"
                    else:
                        q_text = choice[1]
                        correct, opts = choice[2]()
                        random.shuffle(opts)
                        expl = f"The correct answer is {correct}."
                        cat = choice[0]

                else: # 12-13 and 14-18
                    templates = [
                        ("Science", "What gas do plants absorb from the atmosphere during photosynthesis?", lambda: (
                            "Carbon Dioxide", ["Carbon Dioxide", "Oxygen", "Nitrogen", "Helium"]
                        )),
                        ("Technology", "What does 'URL' stand for in computer networking?", lambda: (
                            "Uniform Resource Locator", ["Uniform Resource Locator", "Universal Radio Link", "United Resource Language", "Ultra Rapid Line"]
                        )),
                        ("Math", "What is the square of {n}?", lambda: random.choice([
                            (11, "121", ["121", "111", "132", "144"]),
                            (12, "144", ["144", "124", "136", "154"]),
                            (15, "225", ["225", "215", "245", "205"])
                        ]))
                    ]
                    choice = random.choice(templates)
                    if choice[0] == "Math":
                        n, correct, opts = choice[2]()
                        q_text = f"What is the square of {n} ({n} x {n})?"
                        expl = f"{n} squared is {correct}."
                        cat = "Math"
                    else:
                        q_text = choice[1]
                        correct, opts = choice[2]()
                        random.shuffle(opts)
                        expl = f"{correct} is the accurate scientific term."
                        cat = choice[0]

                # Insert into quizzes
                cur.execute(
                    """INSERT INTO quizzes(category, question, option_a, option_b, option_c, option_d,
                                           correct_answer, age_group, explanation, difficulty_level, language, source)
                       VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, 'MEDIUM', 'en', 'PROCEDURAL')
                       ON CONFLICT(question, age_group) DO NOTHING
                       RETURNING *""",
                    (cat, q_text, opts[0], opts[1], opts[2], opts[3], correct, age_group, expl)
                )
                inserted = cur.fetchone()
                if not inserted:
                    cur.execute("SELECT * FROM quizzes WHERE question=%s AND age_group=%s", (q_text, age_group))
                    inserted = cur.fetchone()

                if inserted and inserted['quiz_id'] not in attempted_ids:
                    fresh_rows.append(dict(inserted))
                    attempted_ids.add(inserted['quiz_id'])

        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.warning("Procedural fallback quiz generation failed: %s", exc)
    finally:
        conn.close()

    return fresh_rows


def generate_and_insert_fresh_quizzes(
    age_group: str,
    needed: int = 5,
    child_id: Optional[int] = None,
    grade_level: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Core dynamic generator: uses K2 Horizon AI to generate brand-new, simple,
    age-appropriate questions, inserts them into the database, and returns rows
    guaranteed NOT to have been attempted by this child.
    """
    from database.connection import get_db_connection

    # 1. Fetch stems child has already attempted to prevent AI duplicates
    excluded_stems = []
    past_attempted_ids = set()
    if child_id:
        attempted_rows = fetch_all(
            """SELECT q.quiz_id, q.question FROM quizzes q
               JOIN child_quiz_attempts a ON q.quiz_id = a.quiz_id
               WHERE a.child_id = %s
               ORDER BY a.attempted_at DESC LIMIT 30""",
            (child_id,)
        )
        past_attempted_ids = {r['quiz_id'] for r in attempted_rows}
        excluded_stems = [r['question'] for r in attempted_rows if r.get('question')]

    fresh_results: List[Dict[str, Any]] = []
    seen_in_batch = set(past_attempted_ids)

    # 2. Call K2 AI
    try:
        client = get_ai_client()
        if client.is_k2_available():
            batch_count = max(needed + 2, 5)
            batch = client.generate_quiz_batch(
                age_group=age_group,
                grade_level=grade_level,
                count=batch_count,
                excluded_stems=excluded_stems
            )
            if batch.questions:
                conn = get_db_connection()
                try:
                    with conn.cursor() as cur:
                        for q in batch.questions:
                            cur.execute(
                                """INSERT INTO quizzes(category, question, option_a, option_b, option_c, option_d,
                                                       correct_answer, age_group, explanation, difficulty_level, language, source)
                                   VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'K2_AI')
                                   ON CONFLICT(question, age_group) DO NOTHING
                                   RETURNING *""",
                                (q.category, q.question, q.option_a, q.option_b, q.option_c, q.option_d,
                                 q.correct_answer, age_group, q.explanation, q.difficulty, q.language)
                            )
                            row = cur.fetchone()
                            if not row:
                                cur.execute("SELECT * FROM quizzes WHERE question=%s AND age_group=%s", (q.question, age_group))
                                row = cur.fetchone()

                            if row and row['quiz_id'] not in seen_in_batch:
                                row_dict = dict(row)
                                fresh_results.append(row_dict)
                                seen_in_batch.add(row['quiz_id'])

                                if child_id:
                                    cur.execute(
                                        """INSERT INTO child_personalized_quiz_pool(child_id, quiz_id, reason_for_selection)
                                           VALUES(%s, %s, %s)
                                           ON CONFLICT(child_id, quiz_id) DO NOTHING""",
                                        (child_id, row['quiz_id'], "Tailored by K2 AI for your age")
                                    )
                    conn.commit()
                except Exception as db_exc:
                    conn.rollback()
                    logger.warning("Error saving K2 quiz batch to database: %s", db_exc)
                finally:
                    conn.close()
    except Exception as exc:
        logger.warning("K2 AI quiz batch generation failed (%s), using procedural generator.", exc)

    # 3. If AI results are fewer than requested, supplement with procedural questions
    if len(fresh_results) < needed:
        shortfall = needed - len(fresh_results)
        fallback_rows = _procedural_fallback_quizzes(age_group=age_group, needed=shortfall, child_id=child_id)
        for fb in fallback_rows:
            if fb['quiz_id'] not in seen_in_batch:
                fresh_results.append(fb)
                seen_in_batch.add(fb['quiz_id'])
                if child_id:
                    try:
                        execute(
                            """INSERT INTO child_personalized_quiz_pool(child_id, quiz_id, reason_for_selection)
                               VALUES(%s, %s, %s)
                               ON CONFLICT(child_id, quiz_id) DO NOTHING""",
                            (child_id, fb['quiz_id'], "Dynamic educational practice")
                        )
                    except Exception:
                        pass

    # Strictly guarantee: Return items that are NOT in past_attempted_ids
    return [r for r in fresh_results if r['quiz_id'] not in past_attempted_ids]


def trigger_child_account_creation_refill(child_id: int, age: int):
    """
    Asynchronously called upon child account registration.
    Tailors a fresh batch of simple, age-matched questions using K2 AI and
    populates the child's personalized quiz pool so that fresh unseen questions
    are immediately ready when the child opens the app.
    """
    g = '6-8' if age <= 8 else '9-11' if age <= 11 else '12-13' if age <= 13 else '14-18'

    def worker():
        try:
            logger.info("Starting initial AI quiz generation for newly created child %d (age %d, age_group %s)", child_id, age, g)
            generate_and_insert_fresh_quizzes(age_group=g, needed=10, child_id=child_id)
            populate_child_personalized_pool(child_id, g)
            logger.info("Successfully provisioned initial AI quiz pool for child %d", child_id)
        except Exception as e:
            logger.warning("Background initial quiz refill for child %d failed: %s", child_id, e)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
