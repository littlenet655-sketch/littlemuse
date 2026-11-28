"""
tools/curated_creator_hygiene_report.py

Phase 11: Curated Creator Hygiene & Cleanup Plan (DRY-RUN ONLY).
Inspects curated_creators table, classifies genuine editorial personas vs legacy test accounts,
and generates a reversible SQL migration plan without mutating production data.
"""

import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.connection import fetch_all

GENUINE_CREATORS = {
    "ananya_explores",
    "aarav_cooking",
    "kabir_sports",
    "maya_astronomy",
    "sam_origami",
    "leo_robotics",
    "ait_star_student",
}

LEGACY_TEST_PERSONAS = {
    "real_kid_alpha",
    "tagkid",
    "prockid",
    "statuskid",
    "kid_hbndif",
    "kid_wpzaxm",
    "hkid_14",
}


def generate_creator_hygiene_report() -> dict:
    rows = fetch_all("SELECT creator_id, username, display_name, interest_vertical, active, created_at FROM curated_creators ORDER BY creator_id ASC")
    
    active_genuine = []
    legacy_test = []
    other = []

    for r in rows:
        uname = r["username"]
        info = {
            "creator_id": r["creator_id"],
            "username": uname,
            "display_name": r["display_name"],
            "topic": r["interest_vertical"],
            "active": r["active"],
        }
        if uname in GENUINE_CREATORS:
            active_genuine.append(info)
        elif uname in LEGACY_TEST_PERSONAS:
            legacy_test.append(info)
        else:
            other.append(info)

    reversible_sql_apply = """-- =====================================================================
-- PRODUCTION CLEANUP PLAN: CURATED CREATOR HYGIENE (DRY-RUN ONLY)
-- DO NOT EXECUTE DIRECTLY WITHOUT OPERATOR AUTHORIZATION
-- =====================================================================
-- Deactivates 7 legacy test accounts created in migration 20260924000002
UPDATE curated_creators
SET active = FALSE, updated_at = NOW()
WHERE username IN (
    'real_kid_alpha', 'tagkid', 'prockid', 'statuskid',
    'kid_hbndif', 'kid_wpzaxm', 'hkid_14'
)
AND active = TRUE;
"""

    reversible_sql_revert = """-- =====================================================================
-- REVERT SCRIPT (REVERSIBLE PLAN)
-- =====================================================================
UPDATE curated_creators
SET active = TRUE, updated_at = NOW()
WHERE username IN (
    'real_kid_alpha', 'tagkid', 'prockid', 'statuskid',
    'kid_hbndif', 'kid_wpzaxm', 'hkid_14'
);
"""

    report = {
        "status": "DRY_RUN_ONLY",
        "production_mutated": False,
        "total_creators_inspected": len(rows),
        "genuine_editorial_creators_count": len(active_genuine),
        "genuine_editorial_creators": active_genuine,
        "legacy_test_personas_count": len(legacy_test),
        "legacy_test_personas": legacy_test,
        "other_creators": other,
        "safe_client_filtering": "Enforced in services/ai_creator.py (TEST_CREATOR_USERNAMES filtered from listing and profiles)",
        "reversible_sql_plan": reversible_sql_apply,
        "reversible_sql_revert": reversible_sql_revert,
    }
    return report


if __name__ == "__main__":
    report = generate_creator_hygiene_report()
    print(json.dumps(report, indent=2))
