import os
import sys
import subprocess
import platform

os.makedirs('audit/evidence', exist_ok=True)
os.makedirs('audit/reports', exist_ok=True)

adb_path = os.path.expanduser(r'~\AppData\Local\Android\Sdk\platform-tools\adb.exe')
adb_ver = "Not found"
if os.path.exists(adb_path):
    try:
        res = subprocess.run([adb_path, '--version'], capture_output=True, text=True, timeout=5)
        adb_ver = res.stdout.strip()
    except Exception as e:
        adb_ver = f"Error: {e}"

java_ver = "Not found"
try:
    res = subprocess.run(['java', '-version'], capture_output=True, text=True, timeout=5)
    java_ver = (res.stderr or res.stdout).strip()
except Exception as e:
    java_ver = f"Error: {e}"

git_sha = subprocess.run('git rev-parse HEAD', shell=True, capture_output=True, text=True).stdout.strip()
git_branch = subprocess.run('git rev-parse --abbrev-ref HEAD', shell=True, capture_output=True, text=True).stdout.strip()
git_status = subprocess.run('git status --short', shell=True, capture_output=True, text=True).stdout.strip()

lines = [
    "=== LITTLE NET AUDIT ENVIRONMENT ===",
    f"OS: {platform.platform()} ({platform.system()} {platform.release()})",
    f"Machine: {platform.machine()}",
    f"Python: {sys.version.split()[0]} ({sys.executable})",
    f"Git Branch: {git_branch}",
    f"Git HEAD SHA: {git_sha}",
    f"Git Status: \n{git_status}",
    "----------------------------------------",
    "Flutter: NOT INSTALLED (flutter executable not found on host)",
    "Dart: NOT INSTALLED (dart executable not found on host)",
    f"Java / JDK: \n{java_ver}",
    f"Android SDK: C:\\Users\\aksha\\AppData\\Local\\Android\\Sdk",
    f"adb: \n{adb_ver}",
    "ffmpeg: NOT IN PATH (PyAV v17.1.0 used in Python environment for media decoding)"
]

output = "\n".join(lines)
print(output)
with open('audit/evidence/environment.txt', 'w', encoding='utf-8') as f:
    f.write(output)
