"""
tools/historical_cleanup_dryrun.py

Phase 12: Historical Data Cleanup Reconciliation Tooling (DRY-RUN ONLY).
Addresses known historical live residue:
  - 82 old UPLOADED posts without media/completed processing
  - 34 terminal FAILED posts
  - 4 old OPEN REVIEW events

STRICT RULES:
  - DRY-RUN ONLY. Absolutely NO mutation of database rows.
  - Classifies exact post IDs and timestamps.
  - Outputs a structured report and reversible SQL proposals for operator manual review.
"""

import os
import sys
import json
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import fetch_all, fetch_one


def generate_dryrun_reconciliation_report() -> Dict[str, Any]:
    """Generates dry-run classification of historical database residue."""
    # 1. Old UPLOADED posts (processing_status = 'UPLOADED' or similar historical status without media)
    uploaded_posts = fetch_all(
        """
        SELECT post_id, child_id, processing_status, moderation_status, media_path, source_media_path, upload_id, created_at
        FROM posts
        WHERE processing_status = 'UPLOADED'
           OR (processing_status = 'PENDING' AND media_path IS NULL AND created_at < NOW() - INTERVAL '7 days')
        ORDER BY post_id ASC
        """
    )
    uploaded_ids = [r["post_id"] for r in uploaded_posts]

    # 2. Terminal FAILED posts
    failed_posts = fetch_all(
        """
        SELECT post_id, child_id, processing_status, processing_error, processing_attempts, created_at
        FROM posts
        WHERE processing_status = 'FAILED'
        ORDER BY post_id ASC
        """
    )
    failed_ids = [r["post_id"] for r in failed_posts]

    # 3. Old OPEN REVIEW events
    review_events = fetch_all(
        """
        SELECT event_id, child_id, decision, status, reason, risk_score, created_at
        FROM moderation_events
        WHERE decision = 'REVIEW' AND status = 'OPEN'
        ORDER BY event_id ASC
        """
    )
    review_ids = [r["event_id"] for r in review_events]

    # Reversible SQL proposal for operator review
    uploaded_sql = ""
    if uploaded_ids:
        ids_str = ", ".join(str(i) for i in uploaded_ids)
        uploaded_sql = f"""-- =====================================================================
-- REVERSIBLE CLEANUP PROPOSAL: 82 HISTORICAL UPLOADED POSTS
-- Status: DRY-RUN ONLY (DO NOT AUTO-APPLY)
-- Rationale: Abandoned upload sessions with no media in R2.
-- =====================================================================
-- Proposed Soft-Archive:
UPDATE posts
SET processing_status = 'EXPIRED_ARCHIVED',
    processing_error = 'Historical abandoned upload session - missing source media'
WHERE post_id IN ({ids_str})
  AND processing_status = 'UPLOADED';

-- Revert:
-- UPDATE posts SET processing_status = 'UPLOADED', processing_error = NULL WHERE post_id IN ({ids_str});
"""

    report = {
        "mode": "DRY_RUN_ONLY",
        "production_mutated": False,
        "summary": {
            "uploaded_posts_count": len(uploaded_posts),
            "failed_posts_count": len(failed_posts),
            "open_review_events_count": len(review_events),
        },
        "uploaded_posts": {
            "count": len(uploaded_posts),
            "exact_ids": uploaded_ids,
            "policy": "Mark as EXPIRED_ARCHIVED (do not delete rows, preserve ID sequence and child references).",
            "proposed_sql": uploaded_sql,
        },
        "failed_posts": {
            "count": len(failed_posts),
            "exact_ids": failed_ids,
            "policy": "LEAVE TERMINAL. Terminal failed posts do not impact feed, queries, or user quotas.",
        },
        "open_review_events": {
            "count": len(review_events),
            "exact_ids": review_ids,
            "policy": "MANUAL OPERATOR REVIEW ONLY. Never auto-approve or auto-dismiss parent review events.",
            "events_metadata": [
                {
                    "event_id": r["event_id"],
                    "child_id": r["child_id"],
                    "reason": r.get("reason"),
                    "risk_score": float(r["risk_score"]) if r.get("risk_score") is not None else None,
                    "created_at": r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"]),
                }
                for r in review_events
            ],
        },
    }
    return report


if __name__ == "__main__":
    rep = generate_dryrun_reconciliation_report()
    print(json.dumps(rep, indent=2))
