from typing import List, Optional, Literal, Any
from pydantic import BaseModel, Field, field_validator, model_validator

class ChatSafetyResult(BaseModel):
    action: Literal["ALLOW", "REVIEW", "BLOCK"] = "REVIEW"
    risk_score: float = Field(default=0.5, ge=0.0, le=1.0)
    primary_category: str = "SAFE"
    reason_code: str = "SAFETY_CHECK_REQUIRED"
    contains_grooming: bool = False
    contains_coercion: bool = False
    contains_off_platform_solicitation: bool = False
    contains_photo_request: bool = False
    contains_pii_attempt: bool = False

class GeneratedQuestion(BaseModel):
    category: str
    question: str
    option_a: str = ""
    option_b: str = ""
    option_c: str = ""
    option_d: str = ""
    correct_answer: str
    explanation: Optional[str] = None
    difficulty: Literal["EASY", "MEDIUM", "HARD"] = "MEDIUM"
    language: str = "en"

    @model_validator(mode="before")
    @classmethod
    def populate_options(cls, data: Any) -> Any:
        if isinstance(data, dict):
            opts = data.get("options")
            if isinstance(opts, list):
                if len(opts) < 3:
                    raise ValueError("Question requires at least 3 options")
                if "option_a" not in data and len(opts) > 0: data["option_a"] = opts[0]
                if "option_b" not in data and len(opts) > 1: data["option_b"] = opts[1]
                if "option_c" not in data and len(opts) > 2: data["option_c"] = opts[2]
                if "option_d" not in data:
                    data["option_d"] = opts[3] if len(opts) > 3 else opts[0]
            if "correct_answer" not in data:
                for k in ("answer", "correct", "correct_option"):
                    if k in data:
                        data["correct_answer"] = data[k]
                        break
            ans = str(data.get("correct_answer", "")).strip().lower()
            opt_map = {
                "option_a": data.get("option_a"), "a": data.get("option_a"),
                "option_b": data.get("option_b"), "b": data.get("option_b"),
                "option_c": data.get("option_c"), "c": data.get("option_c"),
                "option_d": data.get("option_d"), "d": data.get("option_d")
            }
            if ans in opt_map and opt_map[ans]:
                data["correct_answer"] = opt_map[ans]
        return data

    @property
    def options(self) -> List[str]:
        return [self.option_a, self.option_b, self.option_c, self.option_d]

    @field_validator("correct_answer")
    @classmethod
    def validate_correct_answer_matches_option(cls, v: str, info) -> str:
        data = info.data
        options = [data.get("option_a"), data.get("option_b"), data.get("option_c"), data.get("option_d")]
        options = [str(o).strip() for o in options if o is not None]
        if str(v).strip() not in options:
            raise ValueError(f"correct_answer '{v}' does not match any of the provided options: {options}")
        return str(v).strip()

class QuizBatchResult(BaseModel):
    questions: List[GeneratedQuestion]
    category: str = "General"
    age_group: str = "9-11"

class QuizExplanationResult(BaseModel):
    kid_friendly_explanation: str
    encouragement: str
    fun_fact: Optional[str] = None
    correct_concept: Optional[str] = None

class LanguageDrill(BaseModel):
    word_english: str = ""
    native_script: str = ""
    phonetics: str = ""
    language: str = "en"
    question: str = ""
    option_a: str = ""
    option_b: str = ""
    option_c: str = ""
    option_d: str = ""
    correct_answer: str = ""
    fun_fact: Optional[str] = None
    difficulty: Literal["EASY", "MEDIUM", "HARD"] = "EASY"
    drill_type: str = "TRANSLATION_MATCH"
    vocabulary_word: Optional[str] = None
    pronunciation_hint: Optional[str] = None
    english_meaning: Optional[str] = None
    age_group: Optional[str] = "9-11"
    concept_key: Optional[str] = None
    target_language: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def handle_drill_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "vocabulary_word" in data and "native_script" not in data:
                data["native_script"] = data["vocabulary_word"]
            if "pronunciation_hint" in data and "phonetics" not in data:
                data["phonetics"] = data["pronunciation_hint"]
            if "english_meaning" in data and "word_english" not in data:
                data["word_english"] = data["english_meaning"]
            if "target_language" in data and "language" not in data:
                lang_map = {"Kannada": "kn", "Hindi": "hi", "English": "en"}
                data["language"] = lang_map.get(data["target_language"], data["target_language"])
            opts = data.get("options")
            if isinstance(opts, list) and len(opts) >= 3:
                if "option_a" not in data and len(opts) > 0: data["option_a"] = opts[0]
                if "option_b" not in data and len(opts) > 1: data["option_b"] = opts[1]
                if "option_c" not in data and len(opts) > 2: data["option_c"] = opts[2]
            if "correct_answer" not in data:
                for k in ("answer", "correct", "correct_option"):
                    if k in data:
                        data["correct_answer"] = data[k]
                        break
            ans = str(data.get("correct_answer", "")).strip().lower()
            opt_map = {
                "option_a": data.get("option_a"), "a": data.get("option_a"),
                "option_b": data.get("option_b"), "b": data.get("option_b"),
                "option_c": data.get("option_c"), "c": data.get("option_c"),
                "option_d": data.get("option_d"), "d": data.get("option_d")
            }
            if ans in opt_map and opt_map[ans]:
                data["correct_answer"] = opt_map[ans]
        return data

    @property
    def options(self) -> List[str]:
        return [self.option_a, self.option_b, self.option_c, self.option_d]

    @field_validator("correct_answer")
    @classmethod
    def validate_correct_answer_matches_option(cls, v: str, info) -> str:
        data = info.data
        options = [data.get("option_a"), data.get("option_b"), data.get("option_c"), data.get("option_d")]
        options = [str(o).strip() for o in options if o is not None]
        if str(v).strip() not in options:
            raise ValueError(f"correct_answer '{v}' does not match any of the provided options: {options}")
        return str(v).strip()

class LanguageExerciseResult(BaseModel):
    drills: List[LanguageDrill]

class ContentClassificationResult(BaseModel):
    content_category: str
    educational_score: float = Field(default=0.0, ge=0.0, le=1.0)
    age_suitability: Literal["6-8", "9-11", "12-13", "ALL"] = "9-11"
    topic: str = "General"
    subtopic: Optional[str] = None
    learning_tags: List[str] = Field(default_factory=list)
    is_safe_for_kids: bool = True

class ParentDigestResult(BaseModel):
    headline: str
    learning_highlights: List[str] = Field(default_factory=list)
    topics_to_practice: List[str] = Field(default_factory=list)
    safety_summary: str
    offline_activity_suggestion: str

class SafetySummaryResult(BaseModel):
    timeframe: str = "Last 7 Days"
    messages_blocked: int = 0
    contact_attempts_blocked: int = 0
    reviews_queued: int = 0
    safety_status_text: str = "All monitored activity meets safety thresholds."
