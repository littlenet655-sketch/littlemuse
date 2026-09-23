"""Stage the trained safety models into the Modal ``littlenet-model-cache`` volume.

Volume strategy (option A, consistent with V2/V3):
- ``modal_ai.py`` sets ``LITTLENET_TRAINED_IMAGE_V2_PATH``,
  ``LITTLENET_TRAINED_IMAGE_V3_PATH`` and ``LITTLENET_TRAINED_TEXT_PATH`` to
  ``/cache/models/...`` — the volume is authoritative at runtime.
- This tool stages the real binaries from ``models/`` into that volume.
  It refuses to upload Git LFS pointer stubs: any ``.pth`` under 1,000 bytes or
  a ``model.safetensors`` that does not match the verified byte size aborts.

Run from the repo root: ``python tools/stage_model_volume.py``
"""
import os
import sys
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"

#: Exact byte sizes of the verified artifacts (also pinned in the release gate).
EXPECTED_BYTES = {
    "littlenet_core_safety_v2.pth": 16_335_485,
    "littlenet_weapons_violence_v3.pth": 16_327_011,
    os.path.join("littlenet_text_safety", "model.safetensors"): 541_351_212,
}

MODEL_FILES = [
    "littlenet_core_safety_v2.pth",
    "littlenet_weapons_violence_v3.pth",
    os.path.join("littlenet_text_safety", "model.safetensors"),
    os.path.join("littlenet_text_safety", "config.json"),
    os.path.join("littlenet_text_safety", "tokenizer.json"),
    os.path.join("littlenet_text_safety", "tokenizer_config.json"),
]

VOLUME_NAME = "littlenet-model-cache"


def _verify_local(rel: str) -> Path:
    local = MODELS_DIR / rel
    if not local.is_file():
        raise SystemExit(f"STAGE BLOCKED: missing local artifact: {local}")
    expected = EXPECTED_BYTES.get(rel)
    if expected is not None and local.stat().st_size != expected:
        raise SystemExit(
            f"STAGE BLOCKED: byte-size mismatch for {rel}: "
            f"got {local.stat().st_size}, expected {expected}. "
            "Refusing to stage a pointer stub or corrupt artifact."
        )
    if rel.endswith(".pth") and local.stat().st_size < 1_000:
        raise SystemExit(f"STAGE BLOCKED: pointer-sized stub at {local}")
    return local


def main() -> None:
    print(f"Staging trained models into modal.Volume('{VOLUME_NAME}')...")
    vol = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
    with vol.batch_upload(force=True) as batch:
        for rel in MODEL_FILES:
            local = _verify_local(rel)
            remote_path = "/models/" + rel.replace("\\", "/")
            print(f"Uploading {local} -> {remote_path} ({local.stat().st_size} bytes)")
            batch.put_file(str(local), remote_path)
    print("Model staging finished. Verifying volume listing...")
    for entry in vol.listdir("/models"):
        print(f"  {entry.path} ({entry.type})")
    print("Done! Next: run preflights before deploy:")
    print("  modal run modal_ai.py --trained-image-preflight-only")
    print("  modal run modal_ai.py --trained-text-preflight-only")


if __name__ == "__main__":
    sys.exit(main())
