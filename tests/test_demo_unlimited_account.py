from datetime import datetime
from pathlib import Path

import services.controls as controls
import services.usage as usage

ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_demo_flag_exists_in_baseline_and_migration():
    schema = text("database/schema.sql")
    migration = text("db/migrations/20260929000001_demo_unlimited.sql")
    assert "demo_unlimited BOOLEAN NOT NULL DEFAULT FALSE" in schema
    assert "ADD COLUMN IF NOT EXISTS demo_unlimited BOOLEAN NOT NULL DEFAULT FALSE" in migration


def test_demo_child_bypasses_screen_time_without_reading_limits(monkeypatch):
    monkeypatch.setattr(usage, "is_demo_unlimited", lambda _child_id: True)

    def should_not_read(*_args, **_kwargs):
        raise AssertionError("demo account should short-circuit before time-limit query")

    monkeypatch.setattr(usage, "fetch_one", should_not_read)
    assert usage.lock_state(7) == (False, None)
    assert usage.effective_daily_limit(7) == 24 * 60


def test_demo_child_bypasses_quiet_hours_only(monkeypatch):
    monkeypatch.setattr(controls, "is_demo_unlimited", lambda _child_id: True)
    monkeypatch.setattr(
        controls,
        "controls_for_child",
        lambda _child_id: {
            "quiet_hours_enabled": True,
            "quiet_start": "21:00",
            "quiet_end": "07:00",
        },
    )
    state = controls.quiet_hours_state(7, datetime(2026, 9, 29, 23, 0))
    assert state["active"] is False
    assert state["demo_bypass"] is True


def test_demo_flag_does_not_modify_feature_permission_function():
    source = text("services/controls.py")
    feature_block = source.split("def _feature_allowed_uncached", 1)[1].split("CATEGORY_SYNONYMS", 1)[0]
    assert "is_demo_unlimited" not in feature_block
    assert "controls_for_child" in feature_block


def test_admin_can_toggle_only_explicit_demo_child_flag():
    api = text("mobile/admin_api.py")
    assert "/demo-unlimited" in api
    assert "target['role'] != 'CHILD'" in api
    assert "demo_unlimited=%s" in api
    ui = text("mobile_app/src/screens/admin/AdminScreens.tsx")
    assert "Enable unlimited demo" in ui
    assert "Disable unlimited demo" in ui
    assert "Safety rules still apply." in ui
