"""Focused checks for the Expo API-origin helper (no network, no EAS)."""
from pathlib import Path

from tools.set_backend_url import public_https_problem, write_expo_api_url


def test_public_https_problem_rejects_cleartext_and_private_hosts():
    assert public_https_problem("https://api.littlenet.example") is None
    assert public_https_problem("http://api.littlenet.example") == "https_required"
    assert public_https_problem("https://127.0.0.1") == "private_host"
    assert public_https_problem("https://192.168.1.8") == "private_host"
    assert public_https_problem("https://10.0.0.2") == "private_host"
    assert public_https_problem("https://172.20.0.2") == "private_host"
    assert public_https_problem("https://169.254.1.1") == "private_host"
    assert public_https_problem("https://100.64.0.1") == "private_host"
    assert public_https_problem("https://[fd12::1]") == "private_host"
    assert public_https_problem("https://[fe80::1]") == "private_host"


def test_write_expo_api_url_updates_mobile_env_only(tmp_path):
    dest = tmp_path / "mobile_app" / ".env"
    write_expo_api_url("https://backend.littlenet.example/", dest)
    assert dest.read_text(encoding="utf-8") == "EXPO_PUBLIC_API_BASE_URL=https://backend.littlenet.example\n"
    assert not (tmp_path / "android").exists()
