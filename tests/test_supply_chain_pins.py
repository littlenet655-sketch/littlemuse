"""Static supply-chain guards (no network, no build)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DBMATE_SHA = "b002d5249d53d0c6c482ed761b5a806c6fb9a364fcc5f9db3e8763c1d9e40e1d"


def test_every_dbmate_download_is_checksum_verified():
    for rel in (
        "Dockerfile",
        "Dockerfile.web",
        "modal_web.py",
        ".github/workflows/ci.yml",
        ".github/workflows/role-e2e.yml",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "dbmate-linux-amd64" in text, rel
        assert DBMATE_SHA in text and "sha256sum -c" in text, rel


def test_all_workflow_actions_are_sha_pinned():
    for wf in (ROOT / ".github" / "workflows").glob("*.yml"):
        for line in wf.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*-?\s*uses:\s*(\S+)", line)
            if m and not m.group(1).startswith("./"):
                assert re.search(r"@[0-9a-f]{40}$", m.group(1)), f"{wf.name}: {line.strip()}"


def test_split_requirement_files_use_exact_pins_for_ml_stack():
    for rel in ("requirements-text.txt", "requirements-ai.txt", "requirements-safety.txt"):
        for line in (ROOT / rel).read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith("-r"):
                continue
            assert "==" in line and ">=" not in line, f"{rel}: {line}"


def test_production_text_runtime_keeps_validated_transformers_510():
    text = (ROOT / "requirements-text.txt").read_text(encoding="utf-8")
    modal = (ROOT / "modal_ai.py").read_text(encoding="utf-8")
    assert "transformers==5.10.0" in text
    assert "transformers==5.10.0" in modal
    for rel in ("Dockerfile", "Dockerfile.web", "modal_ai.py", "modal_web.py"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert "requirements.txt" not in src or "requirements-text.txt" in src
        assert "-r requirements.txt" not in src
        assert "COPY requirements.txt" not in src
