import os
import pytest
from tools.reconcile_operator_v5 import OperatorReconciliationV5

def test_reconcile_operator_dry_run_semantics():
    reconciler = OperatorReconciliationV5(apply=False)
    db_report = reconciler.run_db_reconciliation()
    
    assert db_report["mode"] == "DRY-RUN"
    assert "categories" in db_report
    for cat in ["ACTIVE_VALID", "RECOVERABLE", "EXPIRED", "TERMINAL_HISTORY", "FAILED_OPERATOR_REVIEW", "OPEN_REVIEW"]:
        assert cat in db_report["categories"]
    assert len(db_report["actions_executed"]) == 0

def test_reconcile_media_classification():
    reconciler = OperatorReconciliationV5(apply=False)
    # Feed mock R2 objects
    r2_mock_manifest = [
        "quarantine/old/stale_quarantine.jpg",
        "posts/unreferenced_orphan.jpg"
    ]
    media_report = reconciler.reconcile_media_references(r2_objects=r2_mock_manifest)
    
    assert "categories" in media_report
    assert "VALID" in media_report["categories"]
    assert "LEGACY_LOCAL_PATH" in media_report["categories"]
    assert "ORPHAN_OBJECT" in media_report["categories"]
    assert "STALE_QUARANTINE" in media_report["categories"]
    assert "POSTER_MISSING" in media_report["categories"]
    
    # Check that quarantine mock object is categorized into STALE_QUARANTINE
    quarantine_objs = [item["object"] for item in media_report["categories"]["STALE_QUARANTINE"]]
    assert "quarantine/old/stale_quarantine.jpg" in quarantine_objs