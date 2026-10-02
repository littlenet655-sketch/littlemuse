from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_auth_pages_use_official_littlenet_logo_not_settings_gear():
    login = (ROOT / "auth/templates/login.html").read_text(encoding="utf-8")
    assert "/static/icons/app_logo.png?v=official-shield-ad60e5d" in login
    assert "settings_gear" not in login
    assert 'alt="LittleNet Logo"' in login


def test_official_logo_assets_and_settings_assets_remain_separate():
    assert (ROOT / "static/icons/app_logo.png").is_file()
    assert (ROOT / "static/icons/app_logo.webp").is_file()
    # Gear assets are legitimate Settings UI assets; they must never replace
    # the app-logo reference used by authentication/admin branding.
    assert (ROOT / "static/icons/settings_gear.svg").is_file()
