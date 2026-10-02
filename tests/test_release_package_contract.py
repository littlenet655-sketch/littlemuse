import zipfile
from pathlib import Path

from tools.package_release import portable_arcname, write_release_zip

ROOT = Path(__file__).parents[1]


def test_release_packager_excludes_apk_binaries():
    src = (ROOT / "tools/package_release.py").read_text(encoding="utf-8")
    assert "'.apk'" in src or '".apk"' in src
    assert "portable_arcname" in src
    assert 'f"LittleNet/{posix}"' in src or "LittleNet/" in src


def test_portable_arcname_uses_forward_slashes_under_littlenet():
    assert portable_arcname(Path("services") / "media_outbox.py") == "LittleNet/services/media_outbox.py"
    assert portable_arcname(r"models\littlenet_core_safety_v2.pth") == "LittleNet/models/littlenet_core_safety_v2.pth"
    assert "\\" not in portable_arcname(Path("a") / "b" / "c.txt")


def test_release_zip_entries_are_posix_under_one_top_folder(tmp_path):
    src = tmp_path / "tree"
    nested = src / "models" / "nested"
    nested.mkdir(parents=True)
    (nested / "keep.txt").write_text("ok", encoding="utf-8")
    (src / ".env").write_text("SECRET=1", encoding="utf-8")
    out = tmp_path / "probe.zip"
    write_release_zip(src, out)
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    assert names == ["LittleNet/models/nested/keep.txt"]
    assert all("/" in name or name.endswith("/") or name.count("/") >= 1 for name in names)
    assert all("\\" not in name for name in names)
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(out) as zf:
        zf.extractall(extracted)
    assert (extracted / "LittleNet" / "models" / "nested" / "keep.txt").is_file()
    assert not (extracted / "LittleNet" / ".env").exists()


def test_repository_does_not_ship_a_stale_submission_apk():
    assert not (ROOT / "LittleNet-v1.0-submission.apk").exists()


def test_active_docs_do_not_publish_stale_admin_password_or_whisper_release_claim():
    active = "\n".join((ROOT / name).read_text(encoding="utf-8") for name in (
        "README.md", "SUBMISSION_SUMMARY.md", "DEPLOY_GUIDE.md", "VIVA_DEMO_MAP.md", "MODAL_DEPLOYMENT.md"
    ))
    assert "Littlenet@0ait04" not in active
    assert "Faster-Whisper Speech-to-Text" not in active
