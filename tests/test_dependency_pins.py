"""Contract tests: exact dependency pins stay in sync.

requirements-ai.txt, requirements-text.txt, requirements-safety.txt and
modal_ai.py must all declare the same exact pinned versions for the shared
AI/safety packages. Drift between any of these surfaces breaks reproducible
builds, so any mismatch fails the suite.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Packages that must be pinned exactly and kept in sync across all surfaces.
SYNCED_PACKAGES = [
    "torch",
    "torchvision",
    "transformers",
    "nudenet",
    "ultralytics",
    "scenedetect-headless",
    "sentencepiece",
]

PIN_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)==([^\s;#]+)")


def parse_requirements(path: Path) -> dict:
    pins = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-r", "--")):
            continue
        m = PIN_RE.match(line)
        if m:
            pins[m.group(1).lower().replace("_", "-")] = m.group(2)
    return pins


def parse_modal_pins(path: Path) -> dict:
    pins = {}
    for m in re.finditer(r'"?([A-Za-z0-9_.\-]+)==([^\s;#"\'\,]+)"?', path.read_text()):
        pins[m.group(1).lower().replace("_", "-")] = m.group(2)
    return pins


def test_requirements_use_exact_pins():
    """Every synced package must use == pins, never ranges, in requirements files."""
    for fname in ("requirements-ai.txt", "requirements-text.txt", "requirements-safety.txt"):
        path = ROOT / fname
        if not path.exists():
            continue
        text = path.read_text()
        for pkg in SYNCED_PACKAGES:
            for line in text.splitlines():
                s = line.strip()
                if not s or s.startswith("#") or s.startswith("-r"):
                    continue
                name = re.split(r"[<>=!~;\s\[]", s, maxsplit=1)[0].lower().replace("_", "-")
                if name == pkg:
                    assert "==" in s and PIN_RE.match(s), (
                        f"{fname}: {pkg} must use an exact == pin, found: {s!r}"
                    )


def test_modal_pins_match_requirements():
    """modal_ai.py pins must equal the pins in the requirements files."""
    modal = parse_modal_pins(ROOT / "modal_ai.py")
    reqs = {}
    for fname in ("requirements-ai.txt", "requirements-text.txt", "requirements-safety.txt"):
        path = ROOT / fname
        if path.exists():
            reqs.update(parse_requirements(path))
    for pkg in SYNCED_PACKAGES:
        assert pkg in reqs, f"{pkg} missing from requirements files"
        assert pkg in modal, f"{pkg} missing from modal_ai.py pip_install list"
        assert modal[pkg] == reqs[pkg], (
            f"{pkg} drift: modal_ai.py has {modal[pkg]!r}, "
            f"requirements files have {reqs[pkg]!r}"
        )
