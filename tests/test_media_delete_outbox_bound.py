"""Delete outbox retries must stop after repeated storage failures."""
from unittest.mock import patch

from services.media_outbox import reconcile_pending_deletes


def test_reconcile_skips_rows_past_attempt_cap():
    with patch("services.media_outbox.fetch_all", return_value=[]) as fetch_all:
        assert reconcile_pending_deletes() == {"checked": 0, "completed": 0, "failed": 0}
    sql = fetch_all.call_args.args[0]
    assert "attempts < 8" in sql
    assert "completed_at IS NULL" in sql
