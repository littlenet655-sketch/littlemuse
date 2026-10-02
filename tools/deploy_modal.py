import sys, os, subprocess

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

env = os.environ.copy()
env['PYTHONIOENCODING'] = 'utf-8'

print("Deploying modal_web.py with UTF-8 encoding...")
res = subprocess.run([
    sys.executable, "-m", "modal", "deploy", "modal_web.py"
], env=env)

sys.exit(res.returncode)
