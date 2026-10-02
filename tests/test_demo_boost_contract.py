from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_demo_boost_migration_is_singleton_and_expiring():
    migration = text("db/migrations/20260929000000_demo_boost.sql")
    assert "demo_boost_state" in migration
    assert "CHECK (state_id = 1)" in migration
    assert "expires_at" in migration
    assert "'OFF','WARMING','READY'" in migration


def test_demo_boost_never_raises_min_container_floor():
    service = text("services/demo_boost.py")
    assert "min_containers=0" in service
    assert "max_containers=1" in service
    assert "scaledown_window=bounded" in service
    assert "START_MINUTES = {15, 30, 60}" in service
    assert "EXTEND_MINUTES = {5, 15, 30}" in service


def test_demo_boost_warmup_is_authenticated():
    ai = text("ai_server.py")
    block = ai.split('@app.get("/warmup")', 1)[1].split("def _sanitize", 1)[0]
    assert "if not authorized()" in block
    assert "check_text(" in block
    assert "check_image(" in block


def test_demo_boost_mobile_permissions_are_role_scoped():
    api = text("mobile/api.py")
    assert '@bp.route("/api/mobile/v1/demo-boost/status")' in api
    assert '@_require_mobile("CHILD", "PARENT", "ADMIN")' in api
    for route in (
        "/api/mobile/v1/admin/demo-boost/start",
        "/api/mobile/v1/admin/demo-boost/extend",
        "/api/mobile/v1/admin/demo-boost/stop",
    ):
        assert route in api
    admin_slice = api.split('/api/mobile/v1/admin/demo-boost/start', 1)[1].split(
        '@bp.route("/api/mobile/v1/admin/dashboard")', 1
    )[0]
    assert admin_slice.count('@_require_mobile("ADMIN")') == 3


def test_demo_boost_ui_has_start_extend_stop_and_global_warning():
    admin = text("mobile_app/src/screens/admin/AdminScreens.tsx")
    assert "Demo Boost" in admin
    for token in ("15, 30, 60", "5, 15, 30", "Stop Demo Boost"):
        assert token in admin
    notice = text("mobile_app/src/components/DemoBoostNotice.tsx")
    assert "5 minutes" in notice
    assert "1 minute" in notice
    assert "Demo Boost ended" in notice
    root = text("mobile_app/src/navigation/RootNavigator.tsx")
    assert "<DemoBoostNotice />" in root
