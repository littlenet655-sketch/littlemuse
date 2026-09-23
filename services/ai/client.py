import logging
from typing import List, Dict, Any, Optional

from .circuit_breaker import CircuitBreaker, CircuitBreakerOpenException
from .providers.k2 import K2Provider, K2Error
from .sanitizer import (
    sanitize_chat_context,
    sanitize_child_learning_profile,
    sanitize_parent_digest_input,
    sanitize_content_metadata,
    sanitize_text
)
from safety.pii_service import RE_ADDRESS_SHARING
from .schemas import (
    ChatSafetyResult,
    QuizBatchResult,
    GeneratedQuestion,
    QuizExplanationResult,
    LanguageExerciseResult,
    LanguageDrill,
    ContentClassificationResult,
    ParentDigestResult
)

logger = logging.getLogger("littlenet.ai.client")

class AIServiceClient:
    """
    Central provider-neutral AI Service Layer for LittleNet.
    Orchestrates privacy sanitization, circuit-breaking, schema validation, and fail-safe policies.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(AIServiceClient, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.k2 = K2Provider()
        self.circuit_breaker = CircuitBreaker(failure_threshold=4, reset_timeout=60.0)
        self._initialized = True

    def is_k2_available(self) -> bool:
        return self.k2.is_configured() and self.circuit_breaker.allow_request()

    # ── 1. Chat Contextual Safety Evaluation (Tier 3) ─────────────────────────
    def evaluate_chat_safety(
        self,
        recent_messages: List[Dict[str, Any]],
        sender_id: int,
        receiver_id: int,
        current_message: str
    ) -> ChatSafetyResult:
        """
        Evaluates conversational safety (grooming, coercion, photo requests, off-platform solicitation).
        Privacy-sanitizes conversation history.
        Enforces FAIL-CLOSED (defaults to REVIEW) if AI is unavailable or fails.
        """
        if not self.is_k2_available():
            logger.info("K2 unavailable or circuit open. Failing closed to REVIEW for chat safety.")
            return ChatSafetyResult(
                action="REVIEW",
                risk_score=0.5,
                primary_category="GATEWAY_STANDBY",
                reason_code="AI_GATEWAY_STANDBY"
            )

        sanitized_history = sanitize_chat_context(recent_messages, sender_id, receiver_id)
        # SECURITY: the new message must never reach the external LLM provider
        # with raw PII. Apply the same scrubber used for chat history (phone /
        # email redaction) plus physical-address redaction. The provider layer
        # (K2Provider.generate -> format_sandboxed_prompt) still wraps this in
        # <untrusted_user_content> tags; sanitization must happen before that.
        sanitized_current = sanitize_text(current_message or "").strip()
        sanitized_current = RE_ADDRESS_SHARING.sub("[ADDRESS_REDACTED]", sanitized_current)[:500]
        system_prompt = (
            "You are a specialized child safety AI for an under-13 social app. "
            "Analyze the conversational exchange and current message for:\n"
            "1. Grooming, boundary testing, or secrecy ('don't tell your parents')\n"
            "2. Off-platform solicitation ('add my snap', 'let's chat on telegram')\n"
            "3. Coercion, pressure, or manipulation\n"
            "4. Requests for private photos, selfies, or what the child is wearing\n"
            "5. Contact/PII sharing attempts\n"
            "Return JSON matching keys: action (ALLOW, REVIEW, or BLOCK), risk_score (0.0 to 1.0), "
            "primary_category (SAFE, GROOMING, BULLYING, SOLICITATION, PII, COERCION), "
            "reason_code (short snake_case code), contains_grooming (bool), contains_coercion (bool), "
            "contains_off_platform_solicitation (bool), contains_photo_request (bool), contains_pii_attempt (bool)."
        )

        user_content = (
            f"Conversation History:\n{sanitized_history}\n\n"
            f"New Message to evaluate:\n{sanitized_current}"
        )

        try:
            raw_json, telemetry = self.k2.generate(system_prompt, user_content, temperature=0.1)
            self.circuit_breaker.record_success()
            result = ChatSafetyResult.model_validate(raw_json)
            logger.info("K2 Chat Safety evaluated successfully: %s (risk=%.2f, %dms)",
                        result.action, result.risk_score, telemetry.get("latency_ms", 0))
            return result
        except Exception as exc:
            self.circuit_breaker.record_failure()
            logger.warning("K2 Chat Safety evaluation failed (%s). Failing closed to REVIEW.", exc)
            return ChatSafetyResult(
                action="REVIEW",
                risk_score=0.7,
                primary_category="EVALUATION_ERROR",
                reason_code="AI_EVALUATION_FAILED"
            )

    # ── 2. Batch Curriculum-Aligned Quiz Generation ───────────────────────────
    def generate_quiz_batch(
        self,
        age_group: str = "9-11",
        grade_level: str = "Grade 4",
        categories: Optional[List[str]] = None,
        count: int = 10,
        difficulty: str = "MEDIUM",
        language: str = "en"
    ) -> QuizBatchResult:
        """
        Asynchronously generates high-quality multiple-choice questions for the quiz bank.
        Gracefully returns empty list on failure so caller can fall back to existing bank.
        """
        if not self.is_k2_available():
            logger.info("K2 unavailable for batch quiz generation; returning empty pool.")
            return QuizBatchResult(questions=[])

        cats = categories or ["Digital Safety", "Kindness", "Stranger Safety", "Healthy Habits"]
        system_prompt = (
            f"You are a child safety teacher writing quiz questions for children in age group '{age_group}' ({grade_level}). "
            f"Generate {count} multiple-choice questions. Topics to mix: {', '.join(cats)}. "
            f"Language: '{language}'. "
            "SIMPLICITY RULES (follow strictly):\n"
            "- Use short, simple everyday words a 7-year-old can read. No jargon, no technical terms.\n"
            "- Question is ONE short sentence, under 120 characters. Scenario-based: 'What should you do if...?' or 'Is it okay to...?'\n"
            "- Each option is a short phrase, under 40 characters.\n"
            "- Exactly 4 distinct options (option_a, option_b, option_c, option_d)\n"
            "- correct_answer must EXACTLY match one of the 4 options verbatim\n"
            "- Include a 1-sentence kid-friendly explanation of why it is correct\n"
            "- Every question must have a clear safe/unsafe or kind/unkind answer. Never ambiguous.\n"
            "- Difficulty: 'EASY'\n"
            "Return JSON: {\"questions\": [{\"category\": \"...\", \"question\": \"...\", \"option_a\": \"...\", "
            "\"option_b\": \"...\", \"option_c\": \"...\", \"option_d\": \"...\", \"correct_answer\": \"...\", "
            "\"explanation\": \"...\", \"difficulty\": \"EASY\", \"language\": \"en\"}]}"
        )
        user_content = f"Generate {count} verified questions for {age_group}."

        try:
            raw_json, telemetry = self.k2.generate(system_prompt, user_content, temperature=0.3)
            self.circuit_breaker.record_success()
            # Normalize if wrapped or bare list
            if isinstance(raw_json, list):
                raw_json = {"questions": raw_json}
            return QuizBatchResult.model_validate(raw_json)
        except Exception as exc:
            self.circuit_breaker.record_failure()
            logger.warning("K2 Quiz Batch generation failed: %s", exc)
            return QuizBatchResult(questions=[])

    # ── 3. On-Demand Wrong-Answer Explanation ─────────────────────────────────
    def explain_quiz_mistake(
        self,
        question: str,
        selected_answer: str,
        correct_answer: str,
        age_group: str = "9-11"
    ) -> QuizExplanationResult:
        """
        Provides warm, kid-friendly explanation and encouragement when a child gets a question wrong.
        """
        fallback = QuizExplanationResult(
            kid_friendly_explanation=f"Great attempt! The correct answer is '{correct_answer}'. Every mistake helps you learn!",
            encouragement="Keep exploring and trying!",
            fun_fact=None,
            correct_concept=correct_answer
        )
        if not self.is_k2_available():
            return fallback

        system_prompt = (
            f"You are a friendly, encouraging teacher for children aged {age_group}. "
            "The child just answered a quiz question incorrectly. Explain why the correct answer is right "
            "and warmly clear up common misconceptions in 2-3 sentences. Keep tone celebratory and encouraging.\n"
            "Return JSON: {\"kid_friendly_explanation\": \"...\", \"encouragement\": \"...\", \"fun_fact\": \"...\", \"correct_concept\": \"...\"}"
        )
        user_content = (
            f"Question: {question}\n"
            f"Child's incorrect choice: {selected_answer}\n"
            f"Actual correct answer: {correct_answer}"
        )

        try:
            raw_json, _ = self.k2.generate(system_prompt, user_content, temperature=0.3)
            self.circuit_breaker.record_success()
            return QuizExplanationResult.model_validate(raw_json)
        except Exception as exc:
            self.circuit_breaker.record_failure()
            logger.info("K2 Explanation failed, using friendly fallback: %s", exc)
            return fallback

    # ── 4. Multilingual Language Learning Drills (Kannada / Hindi / English) ───
    def generate_language_drills(
        self,
        target_language: str = "kn",  # "kn" (Kannada) or "hi" (Hindi)
        learner_age_group: str = "9-11",
        count: int = 5
    ) -> LanguageExerciseResult:
        """
        Generates culturally resonant language learning exercises pairing English with accurate
        Kannada/Hindi script, phonetics, and kid-safe examples.
        """
        lang_name = "Kannada" if target_language == "kn" else "Hindi" if target_language == "hi" else "English"
        if not self.is_k2_available():
            return LanguageExerciseResult(drills=[])

        system_prompt = (
            f"You are a language teacher for kids aged {learner_age_group} in India. "
            f"Generate {count} vocabulary exercises for learning {lang_name} from English. "
            "Requirements:\n"
            "- word_english: English term (e.g. 'Water')\n"
            "- native_script: Proper Unicode script (e.g. 'ನೀರು' for Kannada, 'पानी' for Hindi)\n"
            "- phonetics: English pronunciation transliteration (e.g. 'Neeru' or 'Paani')\n"
            "- question: Clear question for the child\n"
            "- option_a, option_b, option_c, option_d with exact match in correct_answer\n"
            "- drill_type: 'TRANSLATION_MATCH' or 'WORD_OF_THE_DAY'\n"
            "Return JSON: {\"drills\": [{\"word_english\": \"...\", \"native_script\": \"...\", \"phonetics\": \"...\", "
            f"\"language\": \"{target_language}\", \"question\": \"...\", \"option_a\": \"...\", \"option_b\": \"...\", "
            "\"option_c\": \"...\", \"option_d\": \"...\", \"correct_answer\": \"...\", \"fun_fact\": \"...\", "
            "\"difficulty\": \"EASY\", \"drill_type\": \"TRANSLATION_MATCH\"}]}"
        )
        user_content = f"Generate {count} {lang_name} language drills for children."

        try:
            raw_json, _ = self.k2.generate(system_prompt, user_content, temperature=0.2)
            self.circuit_breaker.record_success()
            if isinstance(raw_json, list):
                raw_json = {"drills": raw_json}
            return LanguageExerciseResult.model_validate(raw_json)
        except Exception as exc:
            self.circuit_breaker.record_failure()
            logger.warning("K2 Language drill generation failed: %s", exc)
            return LanguageExerciseResult(drills=[])

    # ── 5. Content Educational & Age Suitability Classification ──────────────
    def classify_content_metadata(
        self,
        caption: str,
        hashtags: Optional[List[str]] = None,
        declared_category: str = "General"
    ) -> ContentClassificationResult:
        """
        Background task to assess post educational value, subject topic, and age appropriateness.
        """
        fallback = ContentClassificationResult(
            content_category=declared_category,
            educational_score=0.2,
            age_suitability="9-11",
            topic=declared_category,
            learning_tags=[],
            is_safe_for_kids=True
        )
        if not self.is_k2_available():
            return fallback

        sanitized = sanitize_content_metadata({
            "caption": caption,
            "hashtags": hashtags or [],
            "category": declared_category
        })

        system_prompt = (
            "You are an educational content evaluator for a child-safe social platform. "
            "Analyze the caption and hashtags. Classify educational value (0.0 to 1.0), "
            "age suitability ('6-8', '9-11', '12-13', 'ALL'), topic, subtopic, learning tags, "
            "and confirm whether it is safe for kids.\n"
            "Return JSON: {\"content_category\": \"...\", \"educational_score\": 0.8, "
            "\"age_suitability\": \"9-11\", \"topic\": \"...\", \"subtopic\": \"...\", "
            "\"learning_tags\": [\"...\"], \"is_safe_for_kids\": true}"
        )
        user_content = (
            f"Declared Category: {sanitized['declared_category']}\n"
            f"Caption: {sanitized['caption']}\n"
            f"Hashtags: {sanitized['hashtags']}"
        )

        try:
            raw_json, _ = self.k2.generate(system_prompt, user_content, temperature=0.1)
            self.circuit_breaker.record_success()
            return ContentClassificationResult.model_validate(raw_json)
        except Exception as exc:
            self.circuit_breaker.record_failure()
            logger.info("K2 Content classification fallback: %s", exc)
            return fallback

    # ── 6. Parent Weekly Digest Synthesis ─────────────────────────────────────
    def synthesize_parent_digest(self, raw_stats: Dict[str, Any]) -> ParentDigestResult:
        """
        Synthesizes weekly usage, quiz progress, and safety telemetry into an empathetic,
        actionable parent report. Never claims '100% safe'; uses grounded, cautious phrasing.
        """
        sanitized = sanitize_parent_digest_input(raw_stats)
        fallback = ParentDigestResult(
            headline="Weekly Learning & Safety Overview",
            learning_highlights=[
                f"Completed {sanitized['quizzes_completed']} educational quizzes with {sanitized['accuracy_pct']}% accuracy.",
                f"Engaged in positive learning activities for {sanitized['screen_time_hours']} hours."
            ],
            topics_to_practice=sanitized.get("weak_subjects") or ["Review tricky quiz questions together"],
            safety_summary=f"Monitored child interactions continuously. {sanitized['safety_blocks_count']} unsafe items blocked; {sanitized['reviews_count']} flagged for parental review.",
            offline_activity_suggestion="Spend time reading a book together or exploring outdoor nature."
        )

        if not self.is_k2_available():
            return fallback

        system_prompt = (
            "You are a child development specialist writing a weekly progress report for a parent. "
            "Based on the weekly statistics, write a warm, encouraging, realistic summary. "
            "IMPORTANT: Never claim '100% safe'. Highlight academic curiosity and suggest a fun weekend offline activity.\n"
            "Return JSON: {\"headline\": \"...\", \"learning_highlights\": [\"...\"], "
            "\"topics_to_practice\": [\"...\"], \"safety_summary\": \"...\", \"offline_activity_suggestion\": \"...\"}"
        )
        user_content = f"Child Weekly Statistics:\n{sanitized}"

        try:
            raw_json, _ = self.k2.generate(system_prompt, user_content, temperature=0.3)
            self.circuit_breaker.record_success()
            return ParentDigestResult.model_validate(raw_json)
        except Exception as exc:
            self.circuit_breaker.record_failure()
            logger.info("K2 Parent digest fallback: %s", exc)
            return fallback

# Singleton instance access
_ai_client = None
def get_ai_client() -> AIServiceClient:
    global _ai_client
    if _ai_client is None:
        _ai_client = AIServiceClient()
    return _ai_client
