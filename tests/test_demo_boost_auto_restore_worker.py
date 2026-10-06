import time
from unittest.mock import Mock, patch
from services import demo_boost


def test_auto_restore_if_expired_success(monkeypatch):
    executed = []
    gpu, cpu = Mock(), Mock()
    monkeypatch.setattr(demo_boost, '_modal_functions', lambda: (gpu, cpu))
    monkeypatch.setattr(demo_boost, 'fetch_one', lambda *a, **k: {'status': 'READY', 'remaining_seconds': 0})
    monkeypatch.setattr(demo_boost, 'execute', lambda sql, *a, **k: executed.append(sql))

    ok = demo_boost.auto_restore_if_expired()
    assert ok is True
    gpyl = gpu.update_autoscaler.call_count
    assert gpyl == 1
    assert any("status='OFF'" in sql for sql in executed)


def test_auto_restore_if_already_off(monkeypatch):
    gpu, cpu = Mock(), Mock()
    monkeypatch.setattr(demo_boost, '_modal_functions', lambda: (gpu, cpu))
    monkeypatch.setattr(demo_boost, 'fetch_one', lambda *a, **k: {'status': 'OFF', 'remaining_seconds': 0})

    ok = demo_boost.auto_restore_if_expired()
    assert ok is True
    gpu.update_autoscaler.assert_not_called()


def test_auto_restore_still_active_reschedules(monkeypatch):
    scheduled_delays = []
    monkeypatch.setattr(demo_boost, 'fetch_one', lambda *a, **k: {'status': 'READY', 'remaining_seconds': 120})
    monkeypatch.setattr(demo_boost, '_schedule_auto_restore', lambda d: scheduled_delays.append(d))

    ok = demo_boost.auto_restore_if_expired()
    assert ok is False
    assert scheduled_delays == [120]


def test_auto_restore_retry_on_failure(monkeypatch):
    gpu, cpu = Mock(), Mock()
    gpyl_calls = [0]
    def fail_twice(**k):
        gpyl_calls[0] += 1
        if gpyl_calls[0] < 3:
            raise RuntimeError('failure')
        return True
    gpu.update_autoscaler.side_effect = fail_twice
    monkeypatch.setattr(demo_boost, '_modal_functions', lambda: (gpu, cpu))
    monkeypatch.setattr(demo_boost, 'fetch_one', lambda *a, **k: {'status': 'READY', 'remaining_seconds': 0})
    monkeypatch.setattr(demo_boost, 'execute', lambda *a, **k: None)

    ok = demo_boost.auto_restore_if_expired(max_retries=3, backoff_base=0.01)
    assert ok is True
    assert gpyl_calls[0] == 3
