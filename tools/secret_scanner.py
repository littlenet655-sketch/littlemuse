import os
import re
import subprocess

PATTERNS = [
    (r'(?i)AIzaSy[A-Za-z0-9_-]{33}', 'Google/Gemini API Key'),
    (r'(?i)sk-[A-Za-z0-9]{20,}', 'OpenAI/K2 Secret Key'),
    (r'(?i)bearer\s+[A-Za-z0-9_.-]{20,}', 'Bearer Token'),
    (r'(?i)ghp_[A-Za-z0-9]{36}', 'GitHub Token'),
    (r'postgres(?:ql)?://[a-zA-Z0-9_\-]+:[^@\s]+@[a-zA-Z0-9_\-\.]+:[0-9]+/[a-zA-Z0-9_\-]+', 'Postgres URL with Password'),
]

root = '.'
ignore_dirs = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', '.idea', '.vscode', 'gradle-8.9', '.gradle', 'build', 'datasets', 'uploads', 'scratch', '.agent', '.agents', 'agent', '.claude', '.cursor'}
findings = []

files = subprocess.check_output(
    ['git', 'ls-files', '--cached', '--others', '--exclude-standard'],
    text=True,
).splitlines()
for relative in files:
    parts = relative.replace('\\', '/').split('/')
    if any(part in ignore_dirs for part in parts):
        continue
    fname = parts[-1]
    if fname.startswith('.env') and fname != '.env.example':
        continue
    if fname.endswith(('.pyc', '.apk', '.png', '.jpg', '.webp', '.zip', '.jar', '.log', '.db', '.tar', '.gz')):
        continue
    fpath = os.path.join(root, relative)
    try:
        if os.path.getsize(fpath) > 500_000:
            continue
        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            for pat, label in PATTERNS:
                for match in re.findall(pat, content):
                    if label == 'Postgres URL with Password' and (
                        relative.endswith('.env.example')
                        or '@localhost:' in match
                        or '@127.0.0.1:' in match
                    ):
                        continue
                    masked = match[:4] + '...' + match[-4:] if len(match) > 10 else '***'
                    findings.append((relative, label, masked))
    except OSError:
        pass

print(f'TOTAL FINDINGS: {len(findings)}')
for f, l, m in findings:
    print(f'{f}: {l} -> {m}')
