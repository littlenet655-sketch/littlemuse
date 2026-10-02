"""Guarded Modal entrypoint for resetting the LittleNet college/demo database.

Usage after Modal credentials are configured:
  modal run modal_reset_demo.py --dry-run --confirm RESET_ALL_ACCOUNTS
  modal run modal_reset_demo.py --confirm RESET_ALL_ACCOUNTS

The reset keeps schema, quizzes and learning challenge banks, but removes all
Parent/Child/Admin accounts and user-owned demo state.
"""
from pathlib import Path
import os

import modal

ROOT = Path(__file__).resolve().parent
app = modal.App("littlemuse-demo-reset")
web_secret = modal.Secret.from_name(
    os.getenv("LITTLENET_WEB_SECRET", "littlemuse-web-secrets"),
    required_keys=["DATABASE_URL", "SECRET_KEY", "AI_SERVICE_URL", "AI_SHARED_SECRET"],
)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_requirements(str(ROOT / "requirements-core.txt"))
    .workdir("/root/littlenet")
    .add_local_dir(
        str(ROOT),
        remote_path="/root/littlenet",
        ignore=[".git/**", ".pytest_cache/**", "**/__pycache__/**", "uploads/**", "*.zip", "*.apk", ".env"],
        copy=True,
    )
)


@app.function(image=image, secrets=[web_secret], timeout=120)
def reset_demo(confirm: str, dry_run: bool = True):
    os.chdir("/root/littlenet")
    from tools.reset_demo_accounts import reset_all_accounts

    return reset_all_accounts(confirm, dry_run=dry_run)


@app.local_entrypoint()
def main(confirm: str = "", dry_run: bool = True):
    result = reset_demo.remote(confirm, dry_run)
    print(result)
