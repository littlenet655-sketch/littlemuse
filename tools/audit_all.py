import shutil
import subprocess
import sys
from pathlib import Path

R = Path(__file__).parents[1]
steps = [
    # audit_all.py is intentionally run from a normal Git working tree during
    # local development and CI. Keep preflight.py strict for actual exports,
    # but explicitly allow repository metadata for this source-tree audit.
    [sys.executable, 'tools/preflight.py', '--allow-git'],
    [sys.executable, 'tools/audit_routes.py'],
    [sys.executable, 'tools/readiness.py', '--source-only'],
    [sys.executable, 'tools/scope_check.py'],
]
for cmd in steps:
    print('\n==>', ' '.join(cmd))
    result = subprocess.run(cmd, cwd=R)
    if result.returncode:
        raise SystemExit(result.returncode)

if shutil.which('node'):
    for rel in ['static/js/littlenet.js', 'static/js/live_safety.js', 'static/js/chat.js', 'static/js/stories.js']:
        print('\n==> node --check', rel)
        result = subprocess.run(['node', '--check', rel], cwd=R)
        if result.returncode:
            raise SystemExit(result.returncode)

required = [
    R / 'mobile_app/package.json',
    R / 'mobile_app/app.json',
    R / 'mobile_app/App.tsx',
    R / 'mobile_app/src/api/client.ts',
]
missing = [str(p.relative_to(R)) for p in required if not p.is_file()]
if missing:
    raise SystemExit('Missing React Native source: ' + ', '.join(missing))
if (R / 'mobile_flutter').exists() or (R / 'android').exists():
    raise SystemExit('Retired mobile source tree still exists')
if 'package.json' in (R / '.gitignore').read_text(encoding='utf-8').splitlines():
    raise SystemExit('package.json must be tracked')
print('\nREACT NATIVE SOURCE: PASS')
print('\nALL LOCAL SOURCE AUDITS PASSED')
