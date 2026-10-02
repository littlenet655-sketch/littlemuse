from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_release_packager_excludes_apk_binaries():
    src = (ROOT / "tools/package_release.py").read_text(encoding="utf-8")
    assert "'.apk'" in src


def test_repository_does_not_ship_a_stale_submission_apk():
    assert not (ROOT / "LittleNet-v1.0-submission.apk").exists()


def test_active_docs_do_not_publish_stale_admin_password_or_whisper_release_claim():
    active = "\n".join((ROOT / name).read_text(encoding="utf-8") for name in (
        "README.md", "SUBMISSION_SUMMARY.md", "DEPLOY_GUIDE.md", "VIVA_DEMO_MAP.md", "MODAL_DEPLOYMENT.md"
    ))
    assert "Littlenet@0ait04" not in active
    assert "Faster-Whisper Speech-to-Text" not in active
