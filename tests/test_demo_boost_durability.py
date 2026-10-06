"""Regression tests for Demo Boost runtime bug fixes and durability."""
import time
from unittest.mock import MagicMock, patch
import pytest

from services.demo_boost import (
    _start_warm_thread,
    auto_restore_if_expired,
    reconcile_demo_boost_on_startup,
    _schedule_auto_restore,
    _TIMER_LOCK,
)


def test_start_warm_thread_no_name_error():
    """Verify _start_warm_thread does not crash with NameError: name 'seconds' is not defined."""
    with patch("services.demo_boost._warm_async"):
        # Calling with expected_expiry and explicit delay_seconds
        _start_warm_thread("2026-10-03T18:00:00Z", delay_seconds=10.0)
        
        # Calling with expected_expiry and default delay_seconds
        with patch("services.demo_boost._row", return_value={"remaining_seconds": 30}):
            _start_warm_thread("2026-10-03T18:00:00Z")


def test_auto_restore_if_expired_on_stale_container_restart():
    """Verify that when a container restarts after an expired lease, auto_restore restores Modal."""
    mock_row = {
        "status": "READY",
        "remaining_seconds": 0,
        "expires_at": "2026-10-03T12:00:00Z",
    }
    with patch("services.demo_boost._row", return_value=mock_row):
        with patch("services.demo_boost._restore_autoscaler", return_value=True) as mock_restore:
            with patch("services.demo_boost.execute") as mock_exec:
                restored = auto_restore_if_expired()
                assert restored is True
                assert mock_restore.called
                assert mock_exec.called
                call_sql = mock_exec.call_args[0][0]
                assert "status='OFF'" in call_sql


def test_auto_restore_retry_backoff_on_modal_failure():
    """Verify auto_restore retries on Modal failure and does not mark OFF if Modal fails."""
    mock_row = {
        "status": "READY",
        "remaining_seconds": 0,
        "expires_at": "2026-10-03T12:00:00Z",
    }
    with patch("services.demo_boost._row", return_value=mock_row):
        with patch("services.demo_boost._restore_autoscaler", side_effect=[False, False, True]) as mock_restore:
            with patch("services.demo_boost.execute") as mock_exec:
                restored = auto_restore_if_expired(max_retries=3, backoff_base=0.01)
                assert restored is True
                assert mock_restore.call_count == 3
                assert mock_exec.called


def test_reconcile_startup_hook():
    """Verify the startup recovery hook runs cleanly and safely."""
    with patch("services.demo_boost.auto_restore_if_expired", return_value=True) as mock_rec:
        result = reconcile_demo_boost_on_startup()
        assert result is True
        assert mock_rec.called
