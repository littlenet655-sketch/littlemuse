# Test Results — CURRENT FINAL RELEASE RESULT

**Authoritative local regression** recorded on technical baseline `f4be262`
(`f4be262d90af724877437c5b06334ff3f01d633d`), 2026-10-02.

This documentation-only release-preparation pass did **not** rerun the 885/281
suites. No executable source or runtime/build config was changed after `f4be262`.

## Environment

- Disposable Docker `pgvector/pgvector:pg16` (Docker 29.7.2)
- PostgreSQL **16.15** + pgvector **0.8.7**
- Container bound to `127.0.0.1:55432`, database `littlenet_test`
- Fresh DB: `python tools/init_db.py` then
  `dbmate --no-dump-schema --migrations-dir db/migrations up` (dbmate 2.34.1)
- **42 applied, 0 pending.** Disposable container removed afterward.
- `APP_TIMEZONE=Asia/Kolkata`
- Python 3.11 venv from `requirements-core.txt` plus `pydantic>=2,<3` and pytest
- Mobile: existing lockfile / `node_modules`; Expo SDK 57

## Results

| Check | Command | Result |
|---|---|---|
| DB-backed focused | `pytest -q` on `test_upload_session_timezone.py` (7), `test_password_reset.py` (2), `test_login_throttle.py` (8), `test_media_upload_concurrency.py` (1), `test_agent_a_disposable_postgres.py` (12), `test_real_postgres_role_smoke.py` (1) | **31 passed / 0 failed** |
| Backend final | `python -m pytest tests/ -q` | **885 passed / 1 skipped / 0 failed** in 53.60 s |
| Mobile final | `cd mobile_app && npm test` | **281 passed / 0 failed** |
| TypeScript | `cd mobile_app && npm run typecheck` | PASSED |
| Expo Doctor | `cd mobile_app && npx expo-doctor` | **21/21 PASSED** |
| Android export | `cd mobile_app && npm run export:android` | PASSED |
| Lockfile consistency | `cd mobile_app && npm ci --dry-run` | PASSED |
| compileall | `python -m compileall -q` (excluding venv/node_modules) | PASSED |
| Local source audits | `python tools/audit_all.py` | PASSED |
| Dynamic SQL | `python tools/audit_dynamic_sql.py` | PASSED |

## Single skip

`tests/test_agent_c_notifications_read.py` — repository-designed skip: requires a
disposable PostgreSQL hostname that is not `localhost` / `127.0.0.1`.

## Historical results (not current)

Older documents (`FINAL_TEST_RESULTS.md`, the 2026-09-22 security-audit appendix,
early RC notes) record smaller suites (for example 563 / 567 / 783 backend tests).
Those are **HISTORICAL RESULT** snapshots. They must not be cited as the current
release gate.

## Not executed

Live Neon / Cloudflare R2 / Resend / Modal; EAS cloud APK; physical-device
playback; CI-only scanners (`pip-audit`, `bandit`, `gitleaks`).
