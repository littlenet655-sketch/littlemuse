"""Create a clean ZIP suitable for private GitHub upload or handoff."""
from pathlib import Path
import hashlib
import os, zipfile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT.parent/'LittleNet-complete-release.zip'

# Trained safety-model artifacts. Must ship as REAL binaries in the release;
# a Git LFS pointer stub (~130 bytes, text) must never be packaged as a model.
# Expected text companions ride along automatically once models/ is included:
#   models/littlenet_text_safety/{tokenizer.json,config.json,tokenizer_config.json}
REQUIRED_MODELS = {
    'models/littlenet_core_safety_v2.pth': (
        16335485,
        '8a9ccfbfd5f59b65143bb90131750db75ff54b895e82d31af04b1e2ccafd431c'),
    'models/littlenet_weapons_violence_v3.pth': (
        16327011,
        'f028ddfa0264ad9570ec6411666143eb57ec9f9159ca218dd6e27f2c413591e8'),
    'models/littlenet_text_safety/model.safetensors': (
        541351212,
        '7eb1f37efdd95a1f363ed76377e65e512c2f986140a50fea404cdcd5598fe875'),
}
LFS_POINTER_PREFIX = b'version https://git-lfs.github.com/spec/v1'

def verify_model_artifacts():
    """Hard gate: fail the build if any trained model is missing, a pointer
    stub, or byte/hash-mismatched against the baseline."""
    for rel, (want_size, want_sha) in REQUIRED_MODELS.items():
        p = ROOT / rel
        if not p.is_file():
            raise SystemExit(f'RELEASE BLOCKED: model missing: {rel}')
        head = p.read_bytes()[:len(LFS_POINTER_PREFIX)]
        if head == LFS_POINTER_PREFIX:
            raise SystemExit(
                f'RELEASE BLOCKED: model is an LFS pointer stub, not a binary: {rel}')
        size = p.stat().st_size
        if size != want_size:
            raise SystemExit(
                f'RELEASE BLOCKED: model size mismatch: {rel}: '
                f'got {size} bytes, expected {want_size}')
        h = hashlib.sha256()
        with p.open('rb') as f:
            for chunk in iter(lambda: f.read(8 << 20), b''):
                h.update(chunk)
        digest = h.hexdigest()
        if digest != want_sha:
            raise SystemExit(
                f'RELEASE BLOCKED: model sha256 mismatch: {rel}: '
                f'got {digest}, expected {want_sha}')
    print(f'MODELS_OK {len(REQUIRED_MODELS)} trained artifacts verified')

# models/ now ships real binaries; model_cache stays excluded.
EXCLUDE_DIRS={'.git','.pytest_cache','__pycache__','.venv','venv','uploads','model_cache','.gradle','build','datasets','scratch','.agent','.agents','agent','.claude','.cursor','gradle-8.9','node_modules'}
EXCLUDE_FILES={'.env','local.properties'}
EXCLUDE_SUFFIXES={'.pyc','.pyo','.jks','.keystore','.apk','.zip'}

verify_model_artifacts()

if OUT.exists():OUT.unlink()
with zipfile.ZipFile(OUT,'w',zipfile.ZIP_DEFLATED) as z:
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for f in filenames:
            p = Path(dirpath) / f
            rel = p.relative_to(ROOT)
            if any(part in EXCLUDE_DIRS for part in rel.parts):continue
            if p.name in EXCLUDE_FILES or p.suffix in EXCLUDE_SUFFIXES:continue
            z.write(p, rel.as_posix())
print(OUT)
