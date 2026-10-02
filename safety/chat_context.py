"""Deterministic conversation-level child-safety signals.

This layer catches risk split across several individually ordinary-looking
messages. It is intentionally narrow: one cue never holds a message. Two or
more distinct grooming/solicitation cue families are required.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from .text_service import _normalized_text


_CUES = {
    "secrecy": re.compile(r"\b(?:secret|dont tell|do not tell|delete (?:the |this )?chat|hide this)\b"),
    "photo_request": re.compile(r"\b(?:send|show|share|take)\b.{0,24}\b(?:photo|picture|pic|selfie|body)\b"),
    "off_platform": re.compile(r"\b(?:snapchat|snap|instagram|insta|telegram|whatsapp|discord|dm me|add me)\b"),
    "location_meet": re.compile(r"\b(?:meet|come alone|where do you live|your address|after school|outside school)\b"),
    "boundary_pressure": re.compile(r"\b(?:trust me|prove it|if you love me|dont be scared|do not be scared|no one will know)\b"),
}


def contextual_chat_risk(recent_messages: Iterable[dict[str, Any]], current_message: str) -> dict[str, Any]:
    """Return bounded, non-content evidence for distributed conversational risk."""
    texts = [str(m.get("message_text") or m.get("text") or "") for m in recent_messages]
    texts.append(current_message or "")
    # Keep evaluation bounded and avoid retaining or returning raw conversation text.
    combined = " ".join(_normalized_text(t)[:500] for t in texts[-20:])
    cues = sorted(name for name, pattern in _CUES.items() if pattern.search(combined))
    suspicious = len(cues) >= 2
    return {
        "suspicious": suspicious,
        "cue_families": cues,
        "reason_code": "MULTI_TURN_GROOMING_PATTERN" if suspicious else "NO_CONTEXTUAL_PATTERN",
    }
