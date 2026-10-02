"""
LittleNet Parent Weekly Digest Background Scheduler
Executes weekly parent digest aggregation in the background.
Ensures:
- Idempotent generation (max 1 digest per child per week)
- No duplicate database records
- Deterministic fallback if K2 AI is unavailable
- Parent notification upon generation
- Failure logging and retry resilience
"""

import logging
import os
import sys
import time
import json
from datetime import datetime, timezone
from typing import Dict, Any, List

# Ensure app root is available
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.connection import fetch_all, fetch_one, execute
from parent.service import get_parent_weekly_digest

logger = logging.getLogger("littlenet.parent.digest_scheduler")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def run_weekly_digest_job(max_retries: int = 2) -> Dict[str, Any]:
    """
    Scans all approved parent-child relationships and generates their weekly digest.
    Idempotent: skips any child that already has a digest created within the last 7 days.
    """
    logger.info("Starting LittleNet Weekly Parent Digest background batch...")
    
    # Query approved parent-child pairs
    pairs = fetch_all("""
        SELECT DISTINCT pcm.parent_id, pcm.child_id, u.full_name as child_name
        FROM parent_child_map pcm
        JOIN users u ON u.user_id = pcm.child_id
        WHERE pcm.approved = TRUE AND pcm.parent_id IS NOT NULL
        ORDER BY pcm.parent_id
    """)

    total_eligible = len(pairs)
    skipped_existing = 0
    generated = 0
    failed = 0
    errors = []

    for pair in pairs:
        p_id = pair["parent_id"]
        c_id = pair["child_id"]
        c_name = pair.get("child_name") or f"Child #{c_id}"

        # 1. Idempotency Check: Already generated in the past 7 days?
        existing = fetch_one("""
            SELECT digest_id, week_start_date, created_at
            FROM parent_weekly_digests
            WHERE child_id = %s AND week_start_date >= CURRENT_DATE - INTERVAL '7 days'
            ORDER BY created_at DESC LIMIT 1
        """, (c_id,))

        if existing:
            skipped_existing += 1
            logger.info("Child %s already has weekly digest (ID: %s, date: %s). Skipping.",
                        c_id, existing.get("digest_id"), existing.get("week_start_date"))
            continue

        # 2. Generation with Retry Loop
        success = False
        last_err = None
        for attempt in range(max_retries + 1):
            try:
                digest = get_parent_weekly_digest(p_id, c_id)
                if digest:
                    generated += 1
                    success = True
                    logger.info("Generated weekly digest for %s (Child ID %s, Parent ID %s).",
                                c_name, c_id, p_id)
                    
                    # Notify parent via parent notification table if table exists
                    try:
                        execute("""
                            INSERT INTO parent_notifications(parent_id, child_id, notification_type, notification_message, target_url)
                            VALUES(%s, %s, 'WEEKLY_DIGEST', %s, '/parent/dashboard/')
                        """, (p_id, c_id, f"Your weekly safety & learning digest for {c_name} is ready."))
                    except Exception as notif_err:
                        logger.error("Failed to insert weekly digest notification for parent %s: %s", p_id, notif_err)
                    break
            except Exception as exc:
                last_err = str(exc)
                logger.warning("Attempt %d failed to generate digest for child %s: %s",
                               attempt + 1, c_id, exc)
                time.sleep(1.0)

        if not success:
            failed += 1
            errors.append({"child_id": c_id, "parent_id": p_id, "error": last_err})
            logger.error("Failed to generate digest for child %s after retries: %s", c_id, last_err)

    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_eligible": total_eligible,
        "skipped_existing": skipped_existing,
        "generated_count": generated,
        "failed_count": failed,
        "errors": errors
    }
    logger.info("Weekly digest job complete: %d generated, %d skipped, %d failed.",
                generated, skipped_existing, failed)
    return results


if __name__ == "__main__":
    job_result = run_weekly_digest_job()
    print(json.dumps(job_result, indent=2))
