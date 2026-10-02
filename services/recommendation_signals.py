"""Child-safe recommendation feedback recording.

Signals are deliberately kept separate from moderation and publication state.
They are useful for ranking only after the candidate has passed the normal
visibility, age, safety, and Parent Mode gates.
"""
from __future__ import annotations

from collections import defaultdict

from database.connection import execute, fetch_all


SIGNALS = {
    "INTEREST",
    "REEL_COMPLETION",
    "REEL_REPLAY",
    "LIKE",
    "SAVE",
    "COMMENT",
    "SHARE",
    "FOLLOW",
    "SEARCH_CLICK",
    "NOT_INTERESTED",
    "HIDE",
    "MUTE",
    "BLOCK",
    "REPORT",
}

# Explainable, bounded weights. Negative feedback is intentionally stronger
# than engagement so a child can quickly remove an unwanted recommendation.
SIGNAL_WEIGHTS = {
    "INTEREST": 2.0,
    "REEL_COMPLETION": 1.5,
    "REEL_REPLAY": 2.0,
    "LIKE": 2.0,
    "SAVE": 3.0,
    "COMMENT": 2.0,
    "SHARE": 2.5,
    "FOLLOW": 2.5,
    "SEARCH_CLICK": 1.5,
    "NOT_INTERESTED": -8.0,
    "HIDE": -8.0,
    "MUTE": -10.0,
    "BLOCK": -12.0,
    "REPORT": -12.0,
}


def normalize_source_type(source_type: str) -> str:
    value = str(source_type or "SOCIAL").upper()
    if value in {"POST", "REEL", "STORY"}:
        return "SOCIAL"
    if value in {"USER", "CREATOR", "CHILD"}:
        return "CREATOR"
    return value


def record_signal(
    child_id: int,
    source_type: str,
    source_id: int,
    signal: str,
    *,
    metadata: dict | None = None,
) -> bool:
    """Best-effort feedback write; telemetry must never bypass a safety gate."""
    signal_name = str(signal or "").upper()
    source = normalize_source_type(source_type)
    if signal_name not in SIGNALS or source not in {"SOCIAL", "CURATED", "CREATOR"}:
        return False
    try:
        execute(
            """INSERT INTO recommendation_signals
                   (child_id,source_type,source_id,signal,weight,metadata)
               VALUES(%s,%s,%s,%s,%s,%s::jsonb)""",
            (
                int(child_id),
                source,
                int(source_id),
                signal_name,
                SIGNAL_WEIGHTS[signal_name],
                __import__("json").dumps(metadata or {}),
            ),
        )
        return True
    except Exception:
        # A missing/temporarily unavailable analytics table must not turn a
        # successful like, save, or report into a failed user operation.
        return False


def record_reel_completion(
    child_id: int, source_type: str, source_id: int, replay_count: int = 0
) -> None:
    record_signal(child_id, source_type, source_id, "REEL_COMPLETION")
    for _ in range(min(max(int(replay_count or 0), 0), 20)):
        record_signal(child_id, source_type, source_id, "REEL_REPLAY")


def signal_scores(child_id: int, items: list[dict]) -> dict[tuple[str, int], float]:
    """Return feedback scores keyed by item and creator.

    This query is intentionally advisory. Callers still filter all candidates
    through publication and child-safety eligibility before using these scores.
    """
    if not items:
        return {}
    social_ids = {
        int(item.get("source_id", item.get("post_id")))
        for item in items
        if item.get("source_type") == "SOCIAL" and item.get("source_id", item.get("post_id")) is not None
    }
    curated_ids = {
        int(item.get("source_id", item.get("content_id")))
        for item in items
        if item.get("source_type") == "CURATED" and item.get("source_id", item.get("content_id")) is not None
    }
    creator_ids = {
        int((item.get("ranking_metadata") or {}).get("child_id"))
        for item in items
        if (item.get("ranking_metadata") or {}).get("child_id") is not None
    }
    if not social_ids and not curated_ids and not creator_ids:
        return {}
    try:
        rows = fetch_all(
            """SELECT source_type,source_id,SUM(weight) AS score
                 FROM recommendation_signals
                WHERE child_id=%s
                  AND ((source_type='SOCIAL' AND source_id=ANY(%s))
                    OR (source_type='CURATED' AND source_id=ANY(%s))
                    OR (source_type='CREATOR' AND source_id=ANY(%s)))
                GROUP BY source_type,source_id""",
            (int(child_id), list(social_ids), list(curated_ids), list(creator_ids)),
        )
    except Exception:
        return {}
    scores = defaultdict(float)
    for row in rows or []:
        scores[(str(row.get("source_type") or "").upper(), int(row["source_id"]))] += float(
            row.get("score") or 0
        )
    return dict(scores)