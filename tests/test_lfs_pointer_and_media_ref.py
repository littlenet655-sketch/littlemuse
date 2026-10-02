"""Git LFS pointers are not trained weights, and media refs cannot traverse."""
from pathlib import Path

from safety.model_files import is_git_lfs_pointer
from mobile.api import _unsafe_local_media_ref


def test_repo_custom_weights_are_real_payloads():
    root = Path(__file__).resolve().parents[1]
    payloads = [
        (root / "models" / "littlenet_core_safety_v2.pth", 16335485),
        (root / "models" / "littlenet_weapons_violence_v3.pth", 16327011),
        (root / "models" / "littlenet_text_safety" / "model.safetensors", 541351212),
    ]
    for path, expected_size in payloads:
        assert path.is_file(), path
        assert path.stat().st_size == expected_size, path
        assert not is_git_lfs_pointer(path), path


def test_trained_loaders_treat_real_payloads_as_staged():
    from safety.littlenet_trained_image import available as image_available
    from safety.littlenet_trained_text import available as text_available

    assert image_available() is True
    assert text_available() is True


def test_lfs_pointer_guard_rejects_pointer_files(tmp_path):
    pointer = tmp_path / "model.pth"
    pointer.write_bytes(
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:" + (b"0" * 64) + b"\n"
        b"size 1\n"
    )
    assert is_git_lfs_pointer(pointer) is True


def test_media_ref_rejects_traversal():
    assert _unsafe_local_media_ref("uploads/../.env") is True
    assert _unsafe_local_media_ref("uploads/posts/1.jpg") is False
    assert _unsafe_local_media_ref("/etc/passwd") is True
