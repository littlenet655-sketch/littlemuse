from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_parent_provisioning_accepts_six_through_seventeen():
    source = text("auth/child_provisioning.py")
    assert "if not 6 <= age <= 17:" in source
    assert "Child age must be between 6 and 17." in source
    assert "6 <= age <= 16" not in source


def test_quiz_age_bands_remain_storage_compatible_for_final_scope():
    source = text("quiz/service.py")
    assert "return '6-8'" in source
    assert "return '9-11'" in source
    assert "return '12-13'" in source
    assert "return '14-18'" in source
    assert "'12-14'" not in source
    assert "'15-17'" not in source


def test_startup_quiz_is_permanently_disabled():
    source = text("quiz/service.py")
    block = source.split("def needs_onboarding_quiz", 1)[1].split("# ─── Classic quiz bank", 1)[0]
    assert "return False" in block
    assert "child_quiz_attempts" not in block
