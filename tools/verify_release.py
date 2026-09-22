from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ZIP = ROOT.parent / 'LittleNet-complete-release.zip'
if not ZIP.exists():
    raise SystemExit('Release ZIP not found; run tools/package_release.py first')

required = [
    'README.md', 'BUILD_STATUS.md', 'SCOPE_STATUS.md', '.env.example',
    'app.py', 'modal_ai.py', 'modal_web.py', 'mobile/api.py', 'mobile/admin_api.py',
    'mobile_app/package.json', 'mobile_app/package-lock.json', 'mobile_app/app.json',
    'mobile_app/App.tsx', 'mobile_app/src/api/client.ts',
    # Trained safety models must ship as real binaries (never LFS pointers).
    'models/littlenet_core_safety_v2.pth', 'models/littlenet_weapons_violence_v3.pth',
    'models/littlenet_text_safety/model.safetensors',
    '.github/workflows/react-native.yml', '.github/workflows/release-mobile.yml',
    '.github/workflows/deploy-modal.yml',
]
errors = []
with zipfile.ZipFile(ZIP) as z:
    names = z.namelist()
    for name in required:
        if name not in names:
            errors.append(f'missing release file: {name}')
    for name in names:
        p = Path(name)
        if p.name in {'.env', 'local.properties'}:
            errors.append(f'forbidden file: {name}')
        if any(part in {'.git', '.pytest_cache', '__pycache__', '.venv', 'venv', 'node_modules', 'mobile_flutter'} for part in p.parts):
            errors.append(f'forbidden runtime/legacy path: {name}')
        if p.parts and p.parts[0] == 'android':
            errors.append(f'forbidden duplicate Android root: {name}')
        if p.suffix in {'.pyc', '.pyo', '.jks', '.keystore', '.apk', '.aab'}:
            errors.append(f'forbidden build/sensitive suffix: {name}')
        # Pointer-stub tripwire: real model artifacts are megabytes; an LFS
        # pointer stub is ~130 bytes of text.
        if p.parts and p.parts[0] == 'models' and z.getinfo(name).file_size < 1000:
            errors.append(f'model entry too small, possible LFS pointer stub: {name}')

print('RELEASE_FILES', len(names), 'ERRORS', len(errors))
for error in errors:
    print('-', error)
sys.exit(bool(errors))
