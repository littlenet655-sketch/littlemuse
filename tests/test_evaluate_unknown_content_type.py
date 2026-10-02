"""Fail-closed contract for safety.moderation_service.evaluate.

Unknown content types must produce an explicit BLOCK decision (mappable to
4xx at the API boundary) -- never raise (no 500), never ALLOW, never publish.
"""
import sys
import types

import pytest


@pytest.fixture
def moderation_service(monkeypatch):
    """Import safety.moderation_service with database.connection stubbed."""
    db = types.SimpleNamespace(
        execute=lambda *a, **k: {'event_id': 1},
        fetch_one=lambda *a, **k: {'safety_level': 'STRICT'},
        fetch_all=lambda *a, **k: [],
    )
    monkeypatch.setitem(sys.modules, 'database.connection', db)
    sys.modules.pop('safety.moderation_service', None)
    import safety.moderation_service as ms
    return ms


@pytest.mark.parametrize('content_type', ['PDF', 'DOCUMENT', 'FILE', 'GIF', 'PdF', ''])
def test_unknown_content_type_blocked_never_raises(moderation_service, content_type):
    signals, decision = moderation_service.evaluate(1, content_type, 'payload')
    assert decision.action == 'BLOCK'
    assert decision.action != 'ALLOW'
    assert 'unsupported' in decision.reason.lower()
    assert signals['total_safety_failure'] is True
    assert 'unsupported_content_type' in signals['errors']
    assert signals['category'] == content_type.upper()


def test_unknown_content_type_does_not_touch_the_database(moderation_service, monkeypatch):
    # The fail-closed branch returns before safety_level() (a DB read).
    monkeypatch.setattr(
        moderation_service, 'safety_level',
        lambda child_id: (_ for _ in ()).throw(AssertionError('DB must not be hit')),
    )
    _, decision = moderation_service.evaluate(1, 'WEIRD_TYPE', 'payload')
    assert decision.action == 'BLOCK'


def test_standalone_audio_still_hard_blocked(moderation_service):
    for content_type in ('AUDIO', 'VOICE'):
        signals, decision = moderation_service.evaluate(1, content_type, 'payload')
        assert decision.action == 'BLOCK'
        assert 'standalone_audio_disabled' in signals['errors']
