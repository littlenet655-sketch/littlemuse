"""Optional Microsoft Presidio enrichment for LittleNet PII screening.

Presidio is an *additional* local recognizer layer. It never replaces the
LittleNet deterministic phone/email/contact/grooming rules because child-safety
blocking must remain available even when an NLP dependency/model is missing.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

_ANALYZER = None
_ANALYZER_ERROR = None

# Only entities whose presence is sufficiently concrete to hard-block in a
# child chat/profile. Broad entities such as PERSON/LOCATION are intentionally
# excluded: children must still be able to mention names and cities normally.
ENTITY_TO_CATEGORY = {
    "PHONE_NUMBER": "PHONE_NUMBER",
    "EMAIL_ADDRESS": "EMAIL_ADDRESS",
    "IP_ADDRESS": "IP_ADDRESS",
    "URL": "URL",
    "IBAN_CODE": "FINANCIAL_IDENTIFIER",
    "CREDIT_CARD": "FINANCIAL_IDENTIFIER",
    "CRYPTO": "FINANCIAL_IDENTIFIER",
}


def _enabled() -> bool:
    return os.getenv("LITTLENET_ENABLE_PRESIDIO", "1").strip().lower() not in {
        "0", "false", "no", "off"
    }


def _get_analyzer():
    global _ANALYZER, _ANALYZER_ERROR
    if _ANALYZER is not None:
        return _ANALYZER
    if _ANALYZER_ERROR is not None:
        return None
    if not _enabled():
        _ANALYZER_ERROR = "disabled"
        return None
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider

        model_name = os.getenv("LITTLENET_PRESIDIO_SPACY_MODEL", "en_core_web_sm")
        config = {
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": model_name}],
        }
        nlp_engine = NlpEngineProvider(nlp_configuration=config).create_engine()
        _ANALYZER = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
        return _ANALYZER
    except Exception as exc:  # fail-safe: caller keeps deterministic coverage
        _ANALYZER_ERROR = f"{type(exc).__name__}: {exc}"
        return None


def _redact_spans(text: str, matches: List[Dict[str, Any]]) -> str:
    redacted = text
    # Replace from right to left so earlier offsets remain stable.
    for row in sorted(matches, key=lambda x: int(x["start"]), reverse=True):
        label = row["category"]
        token = {
            "PHONE_NUMBER": "[PHONE]",
            "EMAIL_ADDRESS": "[EMAIL]",
            "IP_ADDRESS": "[IP_REDACTED]",
            "URL": "[URL]",
            "FINANCIAL_IDENTIFIER": "[FINANCIAL_ID]",
        }.get(label, "[PII]")
        redacted = redacted[: int(row["start"])] + token + redacted[int(row["end"]):]
    return redacted


def analyze_pii(text: str) -> Dict[str, Any]:
    """Return high-confidence Presidio entities without ever failing open/closed.

    The caller decides policy. If Presidio is unavailable, ``available`` is False
    and LittleNet's deterministic scanner continues unchanged.
    """
    if not text or not isinstance(text, str):
        return {"available": bool(_get_analyzer()), "categories": [], "matches": [], "redacted_text": text or ""}

    analyzer = _get_analyzer()
    if analyzer is None:
        return {
            "available": False,
            "error": _ANALYZER_ERROR or "unavailable",
            "categories": [],
            "matches": [],
            "redacted_text": text,
        }

    wanted = list(ENTITY_TO_CATEGORY.keys())
    try:
        rows = analyzer.analyze(
            text=text,
            language="en",
            entities=wanted,
            score_threshold=float(os.getenv("LITTLENET_PRESIDIO_SCORE_THRESHOLD", "0.55")),
        )
    except Exception as exc:
        return {
            "available": False,
            "error": f"{type(exc).__name__}: {exc}",
            "categories": [],
            "matches": [],
            "redacted_text": text,
        }

    matches: List[Dict[str, Any]] = []
    categories: List[str] = []
    for row in rows or []:
        entity = str(getattr(row, "entity_type", ""))
        category = ENTITY_TO_CATEGORY.get(entity)
        if not category:
            continue
        item = {
            "entity": entity,
            "category": category,
            "start": int(row.start),
            "end": int(row.end),
            "score": round(float(row.score), 4),
        }
        matches.append(item)
        if category not in categories:
            categories.append(category)

    return {
        "available": True,
        "categories": categories,
        "matches": matches,
        "redacted_text": _redact_spans(text, matches),
    }
