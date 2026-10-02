"""Demo Boost must never leave a long GPU/CPU idle window attached after expiry.

Mock-only: no Modal, no database.
"""
from unittest.mock import Mock

from services import demo_boost


def _install(monkeypatch, row, restore_ok):
    executed = []
    gpu, cpu = Mock(), Mock()
    if not restore_ok:
        gpu.update_autoscaler.side_effect = RuntimeError("modal unavailable")
    monkeypatch.setattr(demo_boost, "_modal_functions", lambda: (gpu, cpu))
    monkeypatch.setattr(demo_boost, "fetch_one", lambda *a, **k: dict(row))
    monkeypatch.setattr(demo_boost, "execute", lambda sql, *a, **k: executed.append(sql))
    return gpu, cpu, executed


def _expired_row():
    return {"status": "READY", "remaining_seconds": 0, "expires_at": None}


def test_expired_boost_restores_default_idle_window_then_marks_off(monkeypatch):
    gpu, cpu, executed = _install(monkeypatch, _expired_row(), restore_ok=True)
    assert demo_boost.status()["active"] is False
    for fn in (gpu, cpu):
        fn.update_autoscaler.assert_called_once_with(
            min_containers=0, max_containers=1, scaledown_window=demo_boost.DEFAULT_SCALEDOWN_SECONDS
        )
    assert any("status='OFF'" in sql for sql in executed)


def test_failed_restore_keeps_row_non_off_so_next_poll_retries(monkeypatch):
    _gpu, _cpu, executed = _install(monkeypatch, _expired_row(), restore_ok=False)
    assert demo_boost.status()["active"] is False
    assert not any("status='OFF'" in sql for sql in executed)


def test_stop_expires_boost_and_restores_via_status(monkeypatch):
    gpu, cpu, executed = _install(monkeypatch, _expired_row(), restore_ok=True)
    demo_boost.stop()
    assert any("expires_at=NOW()" in sql for sql in executed)
    gpu.update_autoscaler.assert_called_once()
    cpu.update_autoscaler.assert_called_once()


def test_stop_with_failed_restore_does_not_forget_override(monkeypatch):
    _gpu, _cpu, executed = _install(monkeypatch, _expired_row(), restore_ok=False)
    assert demo_boost.stop()["active"] is False
    assert not any("status='OFF'" in sql for sql in executed)
