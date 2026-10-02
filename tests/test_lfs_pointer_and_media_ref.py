"""Git LFS pointers are not trained weights, and media refs cannot traverse."""
from pathlib import Path

from safety.model_files import is_git_lfs_pointer
from mobile.api import _unsafe_local_media_ref


def test_repo_custom_weights_are_lfs_pointers():
    root = Path(__file__).resolve().parents[1]
    pointers = [
        root / "models" / "littlenet_core_safety_v2.pth",
        root / "models" / "littlenet_weapons_violence_v3.pth",
        root / "models" / "littlenet_text_safety" / "model.safetensors",
    ]
    for path in pointers:
        assert path.is_file(), path
        assert is_git_lfs_pointer(path), path


def test_trained_loaders_do_not_treat_lfs_pointers_as_staged():
    from safety.littlenet_trained_image import available as image_available
    from safety.littlenet_trained_text import available as text_available

    assert image_available() is False
    assert text_available() is False


def test_media_ref_rejects_traversal():
    assert _unsafe_local_media_ref("uploads/../.env") is True
    assert _unsafe_local_media_ref("uploads/posts/1.jpg") is False
    assert _unsafe_local_media_ref("/etc/passwd") is True
