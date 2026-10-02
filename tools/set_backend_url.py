"""Set the Expo public API origin used by LittleNet mobile builds.

The React Native app is the only client. This writes EXPO_PUBLIC_API_BASE_URL
into mobile_app/.env. It never creates an android/ WebView tree.
"""
from pathlib import Path
from urllib.parse import urlparse
import sys

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / "mobile_app" / ".env"


def public_https_problem(raw: str):
    value = (raw or "").strip()
    if not value:
        return "missing"
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        return "https_required" if parsed.scheme != "https" else "invalid"
    host = parsed.hostname.lower().strip("[]")
    if host in {"localhost", "127.0.0.1", "::1"}:
        return "private_host"
    if host.startswith(("10.", "192.168.", "169.254.")):
        return "private_host"
    parts = host.split(".")
    if len(parts) >= 2 and parts[0] == "172":
        try:
            octet = int(parts[1])
        except ValueError:
            octet = -1
        if 16 <= octet <= 31:
            return "private_host"
    if len(parts) >= 2 and parts[0] == "100":
        try:
            octet = int(parts[1])
        except ValueError:
            octet = -1
        if 64 <= octet <= 127:
            return "private_host"
    if ":" in host and (host.startswith(("fc", "fd")) or host.startswith(("fe8", "fe9", "fea", "feb"))):
        return "private_host"
    return None


def write_expo_api_url(url: str, dest: Path = ENV_PATH) -> Path:
    problem = public_https_problem(url)
    if problem:
        raise SystemExit(f"Refusing {problem} API URL. Use a public https:// origin.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(f"EXPO_PUBLIC_API_BASE_URL={url.strip().rstrip('/')}\n", encoding="utf-8")
    return dest


if __name__ == "__main__":
    if len(sys.argv) != 2 or not sys.argv[1].startswith("https://"):
        raise SystemExit("Usage: python tools/set_backend_url.py https://your-backend.example.com/")
    path = write_expo_api_url(sys.argv[1])
    print("EXPO_PUBLIC_API_BASE_URL set in", path)
