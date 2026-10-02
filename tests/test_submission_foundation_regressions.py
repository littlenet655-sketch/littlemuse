from pathlib import Path

import pytest

from services.job_queue import validate_job_queue_config


ROOT = Path(__file__).resolve().parents[1]


def test_master_release_migration_curated_music_insert_is_terminated():
    sql = (ROOT / "db/migrations/20260910231500_master_final_release.sql").read_text(encoding="utf-8")
    assert "('Silly Cartoon Bounce', 'ComedyKids', 'Comedy'" in sql
    assert "25);\n\n-- 4. Biometric Secret Key" in sql


def test_parent_blueprint_does_not_duplicate_mobile_api_registration():
    source = (ROOT / "parent/api.py").read_text(encoding="utf-8")
    assert "register_mobile_api(parent_api_bp)" not in source
    assert "register_mobile_admin_api(parent_api_bp)" not in source


def test_deactivated_status_is_migrated_explicitly():
    sql = (ROOT / "db/migrations/20260912235000_allow_deactivated_account_status.sql").read_text(encoding="utf-8")
    assert "DEACTIVATED" in sql
    assert "users_account_status_check" in sql


def test_production_queue_is_modal_only(monkeypatch):
    monkeypatch.setenv("JOB_QUEUE_PROVIDER", "modal")
    assert validate_job_queue_config(is_production=True) == "modal"

    monkeypatch.setenv("JOB_QUEUE_PROVIDER", "local")
    with pytest.raises(RuntimeError, match="must be 'modal'"):
        validate_job_queue_config(is_production=True)

    monkeypatch.setenv("JOB_QUEUE_PROVIDER", "qstash")
    with pytest.raises(RuntimeError, match="must be 'modal'"):
        validate_job_queue_config(is_production=True)


def test_development_queue_rejects_retired_qstash(monkeypatch):
    monkeypatch.setenv("JOB_QUEUE_PROVIDER", "qstash")
    with pytest.raises(RuntimeError, match="must be 'local' or 'modal'"):
        validate_job_queue_config(is_production=False)
