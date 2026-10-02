from pathlib import Path
import ast
import json
import sys

R = Path(__file__).parents[1]
checks = []


def add(name, ok, detail=''):
    checks.append((name, bool(ok), detail))


bad = []
for p in R.rglob('*.py'):
    if any(part in ('__pycache__', '.venv', 'venv', 'node_modules', '.git') for part in p.parts):
        continue
    try:
        ast.parse(p.read_text(encoding='utf-8'))
    except Exception as exc:
        bad.append(f'{p.relative_to(R)}:{exc}')
add('Python source parses', not bad, '; '.join(bad))

required = [
    'mobile/api.py', 'mobile/stitch_api.py',
    'mobile_app/package.json', 'mobile_app/app.json', 'mobile_app/App.tsx',
    'mobile_app/src/api/client.ts', 'mobile_app/.env.example',
    'safety/visual_service.py', 'safety/scene_sampler.py',
    'services/job_queue.py', 'services/media_processor.py',
    'modal_ai.py', 'modal_web.py', '.github/workflows/ci.yml',
    '.github/workflows/react-native.yml', '.github/workflows/release-mobile.yml',
    '.github/workflows/deploy-modal.yml',
]
for rel in required:
    add(rel, (R / rel).exists())

package = json.loads((R / 'mobile_app/package.json').read_text(encoding='utf-8'))
app = json.loads((R / 'mobile_app/app.json').read_text(encoding='utf-8'))
client = (R / 'mobile_app/src/api/client.ts').read_text(encoding='utf-8')
mobile_api = (R / 'mobile/api.py').read_text(encoding='utf-8')
visual = (R / 'safety/visual_service.py').read_text(encoding='utf-8')

deps = package.get('dependencies', {})
add('Expo SDK 57 declared', str(deps.get('expo', '')).lstrip('~^<>= ').startswith('57.'))
add('React Native 0.86 declared', str(deps.get('react-native', '')).startswith('0.86.'))
add('Android package contract', app.get('expo', {}).get('android', {}).get('package') == 'com.littlenet.app')
add('Public mobile env only', 'EXPO_PUBLIC_API_BASE_URL' in client)
add('v2 async upload routes mapped', '/api/mobile/v2/uploads/session' in client and 'processing-status' in client)
add('Mobile API identifies React Native', 'client="react-native"' in mobile_api and 'framework="expo"' in mobile_api)
add('Scene-aware video sampling active', 'combined_frame_indices(path,total,max_frames)' in visual)
add('Legacy mobile directories absent', not (R / 'mobile_flutter').exists() and not (R / 'android').exists())

print('LittleNet readiness')
for name, ok, detail in checks:
    print(('PASS' if ok else 'WAIT').ljust(5), name, ('- ' + detail) if detail else '')
source_ready = all(ok for _, ok, _ in checks)
print('\nSOURCE_READY=', source_ready)
raise SystemExit(0 if source_ready else 1)
