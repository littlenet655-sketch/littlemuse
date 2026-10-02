# Test Results — CURRENT FINAL RELEASE RESULT

**Authoritative local regression** recorded on the outbox-trigger freeze
(parent `826e633`), 2026-10-02.

## Environment

- Disposable Docker `pgvector/pgvector:pg16` (Docker 29.7.2)
- PostgreSQL **16.15** + pgvector **0.8.7**
- Container bound to `127.0.0.1:55432`, database `littlenet_test`
- Fresh DB: `python tools/init_db.py` then
  `dbmate --no-dump-schema --migrations-dir db/migrations up` (dbmate 2.34.1)
- **43 applied, 0 pending.** Rollback of `20261002120000` succeeded; re-apply succeeded.
- Disposable container removed afterward.
- `APP_TIMEZONE=Asia/Kolkata`
- Python 3.11 venv from `requirements-core.txt` plus `pydantic>=2,<3` and pytest
- Mobile: existing lockfile / `node_modules`; Expo SDK 57

## Results

| Check | Command | Result |
|---|---|---|
| Backend final | `python -m pytest tests/ -q` | **898 passed / 2 skipped / 0 failed** in 58.24 s |
| Mobile final | `cd mobile_app && npm test` | **283 passed / 0 failed** |
| TypeScript | `cd mobile_app && npx tsc --noEmit` | PASSED |
| Expo Doctor | `cd mobile_app && npx expo-doctor` | **21/21 PASSED** |
| Android export | `cd mobile_app && npm run export:android` | PASSED |
| Lockfile consistency | `cd mobile_app && npm ci --dry-run` | PASSED |
| compileall | `python -m compileall -q` (excluding venv/node_modules) | PASSED |
| Local source audits | `python tools/audit_all.py` | PASSED |
| Dynamic SQL | `python tools/audit_dynamic_sql.py` | PASSED |

## Skips

Two existing harness skips (not product failures). They are not the
`test_agent_c_notifications_read.py` localhost skip from the earlier 42-migration run.

## Historical results (not current)

Older documents (`FINAL_TEST_RESULTS.md`, the 2026-09-22 security-audit appendix,
early RC notes, the `f4be262` 885/281/42/42 snapshot) are **HISTORICAL RESULT**.
They must not be cited as the current release gate.

## Not executed

Live Neon / Cloudflare R2 / Resend / Modal; EAS cloud APK; physical-device
playback; CI-only scanners (`pip-audit`, `bandit`, `gitleaks`).
