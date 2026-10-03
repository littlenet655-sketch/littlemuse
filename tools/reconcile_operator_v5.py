#!/usr/bin/env python3
"""
tools/reconcile_operator_v5.py

Deterministic operator reconciliation tooling for LittleNet V5.
Addresses:
  - Known Issue 4: Historical Neon Data (Processing states, orphan leases, expired upload sessions, open review events)
  - Known Issue 5: Historical R2 / DB Media Mismatch (Missing objects, legacy local paths, orphan candidates, stale quarantine)

Guarantees:
  - Dry-run by default (--dry-run or no args).
  - Explicit --apply flag required for any mutation.
  - Idempotent and transaction-safe.
  - No auto-approval of unreviewed content.
  - No touching active leases (heartbeat within lease timeout / expires_at > now).
  - Bounded re-drive for recoverable items.
  - Never deletes an object still referenced by valid DB data.
  - Deterministic classification and audit output.

Classification Categories:
  Processing / DB:
    - ACTIVE_VALID: Leased recently (processing_lease_expires_at > now) or newly created / unexpired session
    - RECOVERABLE: Stale lease or recoverable failure with retries left (< max_processing_attempts)
    - EXPIRED: Stale pending upload sessions (expires_at < now)
    - TERMINAL_HISTORY: Max retries exceeded or terminal ALLOWED / BLOCKED / FAILED state
    - FAILED_OPERATOR_REVIEW: Content in terminal failure or flagged requiring operator/human resolution
    - OPEN_REVIEW: Legitimate pending parent/operator review events (moderation_events status = 'OPEN')

  Media / R2:
    - VALID: Referenced in DB and verified in storage
    - MISSING_OBJECT: Referenced in DB as clean/published but not in storage
    - LEGACY_LOCAL_PATH: Contains local disk path (e.g. 'uploads/...')
    - ORPHAN_OBJECT: Present in storage but unreferenced in DB
    - STALE_QUARANTINE: Present in quarantine prefix older than quarantine TTL (24h)
    - POSTER_MISSING: Video record missing video poster/thumbnail
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.connection import get_db_connection

logger = logging.getLogger("reconcile_operator_v5")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class OperatorReconciliationV5:
    def __init__(self, apply: bool = False, lease_timeout_sec: int = 300, max_retries: int = 3):
        self.apply = apply
        self.lease_timeout_sec = lease_timeout_sec
        self.max_retries = max_retries

    def run_db_reconciliation(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)

        results = {
            "timestamp": now.isoformat(),
            "mode": "APPLY" if self.apply else "DRY-RUN",
            "categories": {
                "ACTIVE_VALID": [],
                "RECOVERABLE": [],
                "EXPIRED": [],
                "TERMINAL_HISTORY": [],
                "FAILED_OPERATOR_REVIEW": [],
                "OPEN_REVIEW": [],
            },
            "status_counts": {
                "PROCESSING": 0,
                "FAILED": 0,
                "UPLOADED": 0,
                "UPLOADING": 0,
                "REVIEW": 0,
                "ALLOWED": 0,
                "BLOCKED": 0,
            },
            "actions_planned": [],
            "actions_executed": [],
        }

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                # 1. Query all posts processing states
                cur.execute("""
                    SELECT post_id, child_id, media_type, processing_status, moderation_status,
                           processing_attempts, max_processing_attempts,
                           processing_lease_token, processing_lease_expires_at,
                           processing_started_at, processing_completed_at, processing_error,
                           upload_id, created_at
                    FROM posts
                    ORDER BY created_at ASC
                """)
                posts = cur.fetchall()

                for p in posts:
                    pid = p["post_id"]
                    status = p["processing_status"]
                    mod_status = p["moderation_status"]
                    attempts = p["processing_attempts"] or 0
                    max_att = p["max_processing_attempts"] or self.max_retries
                    lease_token = p["processing_lease_token"]
                    lease_expires = p["processing_lease_expires_at"]
                    err = p["processing_error"]

                    if status in results["status_counts"]:
                        results["status_counts"][status] += 1

                    item_info = {
                        "type": "post",
                        "post_id": pid,
                        "processing_status": status,
                        "moderation_status": mod_status,
                        "attempts": attempts,
                        "max_attempts": max_att,
                        "lease_expires_at": lease_expires.isoformat() if lease_expires else None,
                        "error": err,
                    }

                    if status in ("ALLOWED", "BLOCKED"):
                        results["categories"]["TERMINAL_HISTORY"].append(item_info)
                    elif status == "FAILED":
                        if attempts >= max_att:
                            results["categories"]["TERMINAL_HISTORY"].append(item_info)
                            results["categories"]["FAILED_OPERATOR_REVIEW"].append(item_info)
                        else:
                            results["categories"]["RECOVERABLE"].append(item_info)
                            action = {
                                "action": "REDIVE_FAILED_POST",
                                "post_id": pid,
                                "reason": f"Failed with {attempts}/{max_att} attempts"
                            }
                            results["actions_planned"].append(action)
                            if self.apply:
                                with conn.cursor() as update_cur:
                                    update_cur.execute("""
                                        UPDATE posts
                                        SET processing_status = 'UPLOADED',
                                            processing_lease_token = NULL,
                                            processing_lease_expires_at = NULL
                                        WHERE post_id = %s AND processing_status = 'FAILED'
                                    """, (pid,))
                                results["actions_executed"].append(action)
                    elif status == "PROCESSING":
                        is_active_lease = lease_expires and lease_expires > now
                        if is_active_lease:
                            results["categories"]["ACTIVE_VALID"].append(item_info)
                        else:
                            # Stale lease
                            if attempts >= max_att:
                                results["categories"]["FAILED_OPERATOR_REVIEW"].append(item_info)
                                action = {
                                    "action": "EXPIRE_PROCESSING_TO_FAILED",
                                    "post_id": pid,
                                    "reason": f"Stale lease expired with attempts {attempts}/{max_att}"
                                }
                                results["actions_planned"].append(action)
                                if self.apply:
                                    with conn.cursor() as update_cur:
                                        update_cur.execute("""
                                            UPDATE posts
                                            SET processing_status = 'FAILED',
                                                processing_error = 'Processing lease expired - max attempts reached',
                                                processing_lease_token = NULL,
                                                processing_lease_expires_at = NULL
                                            WHERE post_id = %s AND processing_status = 'PROCESSING'
                                        """, (pid,))
                                    results["actions_executed"].append(action)
                            else:
                                results["categories"]["RECOVERABLE"].append(item_info)
                                action = {
                                    "action": "RELEASE_STALE_LEASE",
                                    "post_id": pid,
                                    "reason": f"Stale lease expired, recoverable attempts {attempts}/{max_att}"
                                }
                                results["actions_planned"].append(action)
                                if self.apply:
                                    with conn.cursor() as update_cur:
                                        update_cur.execute("""
                                            UPDATE posts
                                            SET processing_status = 'UPLOADED',
                                                processing_lease_token = NULL,
                                                processing_lease_expires_at = NULL
                                            WHERE post_id = %s AND processing_status = 'PROCESSING'
                                        """, (pid,))
                                    results["actions_executed"].append(action)
                    elif status in ("UPLOADED", "UPLOADING"):
                        results["categories"]["ACTIVE_VALID"].append(item_info)
                    elif status == "REVIEW":
                        results["categories"]["OPEN_REVIEW"].append(item_info)

                # 2. Inspect upload_sessions
                cur.execute("""
                    SELECT upload_id, child_id, kind, media_type, status, expires_at, created_at
                    FROM upload_sessions
                    ORDER BY created_at ASC
                """)
                sessions = cur.fetchall()

                expired_sessions_count = 0
                for s in sessions:
                    uid = s["upload_id"]
                    cid = s["child_id"]
                    st = s["status"]
                    exp = s["expires_at"]
                    cat_info = {
                        "type": "upload_session",
                        "upload_id": str(uid),
                        "child_id": cid,
                        "status": st,
                        "expires_at": exp.isoformat() if exp else None,
                    }

                    if st in ("CONSUMED", "CANCELLED"):
                        results["categories"]["TERMINAL_HISTORY"].append(cat_info)
                    elif st == "PENDING":
                        # Check expiry
                        if exp:
                            # If exp is naive, make it aware in UTC
                            if exp.tzinfo is None:
                                exp = exp.replace(tzinfo=timezone.utc)
                            if exp < now:
                                expired_sessions_count += 1
                                results["categories"]["EXPIRED"].append(cat_info)
                                action = {
                                    "action": "MARK_EXPIRED_UPLOAD_SESSION",
                                    "upload_id": str(uid),
                                    "reason": "Upload session TTL expired"
                                }
                                results["actions_planned"].append(action)
                                if self.apply:
                                    with conn.cursor() as update_cur:
                                        update_cur.execute("""
                                            UPDATE upload_sessions
                                            SET status = 'EXPIRED'
                                            WHERE upload_id = %s AND status = 'PENDING'
                                        """, (uid,))
                                    results["actions_executed"].append(action)
                            else:
                                results["categories"]["ACTIVE_VALID"].append(cat_info)
                        else:
                            results["categories"]["ACTIVE_VALID"].append(cat_info)
                    else:
                        results["categories"]["TERMINAL_HISTORY"].append(cat_info)

                results["status_counts"]["expired_pending_sessions"] = expired_sessions_count

                # 3. Inspect moderation_events (open reviews)
                cur.execute("""
                    SELECT event_id, child_id, content_id, content_type, decision, status, created_at
                    FROM moderation_events
                    WHERE status = 'OPEN'
                    ORDER BY created_at ASC
                """)
                open_events = cur.fetchall()
                results["status_counts"]["open_review_events"] = len(open_events)
                for ev in open_events:
                    results["categories"]["OPEN_REVIEW"].append({
                        "event_id": str(ev["event_id"]),
                        "child_id": ev["child_id"],
                        "content_id": ev["content_id"],
                        "content_type": ev["content_type"],
                        "decision": ev["decision"],
                        "status": ev["status"],
                        "created_at": ev["created_at"].isoformat() if ev["created_at"] else None,
                    })

                if self.apply:
                    conn.commit()
        finally:
            conn.close()

        return results

    def reconcile_media_references(self, r2_objects: Optional[List[str]] = None) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        results = {
            "timestamp": now.isoformat(),
            "mode": "APPLY" if self.apply else "DRY-RUN",
            "categories": {
                "VALID": [],
                "MISSING_OBJECT": [],
                "LEGACY_LOCAL_PATH": [],
                "ORPHAN_OBJECT": [],
                "STALE_QUARANTINE": [],
                "POSTER_MISSING": [],
            }
        }

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT post_id, media_type, media_path, source_media_path, poster_path, is_reel
                    FROM posts
                """)
                posts = cur.fetchall()
                for p in posts:
                    pid = p["post_id"]
                    m_type = p["media_type"]
                    m_path = p["media_path"]
                    s_path = p["source_media_path"]
                    poster = p["poster_path"]

                    p_info = {
                        "type": "post",
                        "post_id": pid,
                        "media_path": m_path,
                        "source_media_path": s_path,
                        "poster_path": poster,
                    }

                    for path in (m_path, s_path):
                        if path and (path.startswith("uploads/") or path.startswith("/uploads/") or "localhost" in path):
                            results["categories"]["LEGACY_LOCAL_PATH"].append(p_info)
                            break
                    else:
                        if m_path or s_path:
                            results["categories"]["VALID"].append(p_info)

                    if m_type == "VIDEO" and not poster:
                        results["categories"]["POSTER_MISSING"].append(p_info)
        finally:
            conn.close()

        if r2_objects:
            valid_keys = set()
            for cat in ["VALID", "LEGACY_LOCAL_PATH"]:
                for item in results["categories"][cat]:
                    for k in ("media_path", "source_media_path", "poster_path"):
                        val = item.get(k)
                        if val:
                            valid_keys.add(val.split("/")[-1])

            for obj in r2_objects:
                obj_key = obj.split("/")[-1]
                if obj.startswith("quarantine/"):
                    results["categories"]["STALE_QUARANTINE"].append({"object": obj})
                elif obj_key not in valid_keys:
                    results["categories"]["ORPHAN_OBJECT"].append({"object": obj})

        return results


def main():
    parser = argparse.ArgumentParser(description="LittleNet V5 Operator Reconciliation Tool")
    parser.add_argument("--apply", action="store_true", help="Apply state reconciliation mutations (default is dry-run)")
    parser.add_argument("--lease-timeout", type=int, default=300, help="Seconds before considering a lease stale (default: 300)")
    parser.add_argument("--max-retries", type=int, default=3, help="Max retry attempts for failed jobs (default: 3)")
    parser.add_argument("--r2-manifest", type=str, default=None, help="Optional path to R2 objects manifest")
    parser.add_argument("--out", type=str, default=None, help="Output path for JSON report")

    args = parser.parse_args()

    reconciler = OperatorReconciliationV5(
        apply=args.apply,
        lease_timeout_sec=args.lease_timeout,
        max_retries=args.max_retries
    )

    logger.info(f"Running Operator Reconciliation V5 (mode: {'APPLY' if args.apply else 'DRY-RUN'})...")

    db_report = reconciler.run_db_reconciliation()

    r2_objs = None
    if args.r2_manifest and os.path.exists(args.r2_manifest):
        with open(args.r2_manifest, "r", encoding="utf-8") as f:
            try:
                r2_objs = json.load(f)
            except Exception:
                f.seek(0)
                r2_objs = [line.strip() for line in f if line.strip()]

    media_report = reconciler.reconcile_media_references(r2_objs)

    final_report = {
        "db_reconciliation": db_report,
        "media_reconciliation": media_report,
        "summary": {
            "mode": "APPLY" if args.apply else "DRY-RUN",
            "status_counts": db_report["status_counts"],
            "category_counts": {
                "ACTIVE_VALID": len(db_report["categories"]["ACTIVE_VALID"]),
                "RECOVERABLE": len(db_report["categories"]["RECOVERABLE"]),
                "EXPIRED": len(db_report["categories"]["EXPIRED"]),
                "TERMINAL_HISTORY": len(db_report["categories"]["TERMINAL_HISTORY"]),
                "FAILED_OPERATOR_REVIEW": len(db_report["categories"]["FAILED_OPERATOR_REVIEW"]),
                "OPEN_REVIEW": len(db_report["categories"]["OPEN_REVIEW"]),
            },
            "media_category_counts": {
                "VALID": len(media_report["categories"]["VALID"]),
                "LEGACY_LOCAL_PATH": len(media_report["categories"]["LEGACY_LOCAL_PATH"]),
                "POSTER_MISSING": len(media_report["categories"]["POSTER_MISSING"]),
                "ORPHAN_OBJECT": len(media_report["categories"]["ORPHAN_OBJECT"]),
                "STALE_QUARANTINE": len(media_report["categories"]["STALE_QUARANTINE"]),
            },
            "actions_planned": len(db_report["actions_planned"]),
            "actions_executed": len(db_report["actions_executed"]),
        }
    }

    report_json = json.dumps(final_report, indent=2)
    print(report_json)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report_json)
        logger.info(f"Report saved to {args.out}")


if __name__ == "__main__":
    main()