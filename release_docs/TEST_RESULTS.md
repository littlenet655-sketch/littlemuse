# Test Results (final local regression, 2026-10-02)

Environment: disposable Docker `pgvector/pgvector:pg16` (PostgreSQL 16.15 + vector 0.8.7),
container `littlenet-test-pg` bound to `127.0.0.1:55432`, database `littlenet_test`.
Fresh DB: `python tools/init_db.py` then `dbmate --no-dump-schema --migrations-dir db/migrations up`
(dbmate 2.34.1). **42 applied, 0 pending.** `APP_TIMEZONE=Asia/Kolkata`.
Python 3.11.15 venv from `requirements-core.txt` plus `pydantic>=2,<3` and pytest.
Mobile: existing lockfile / `node_modules`; Node v24.13.0.

| Check | Command | Result |
|---|---|---|
| DB-backed focused | `pytest -q` on `test_upload_session_timezone.py` (7), `test_password_reset.py` (2), `test_login_throttle.py` (8), `test_media_upload_concurrency.py` (1), `test_agent_a_disposable_postgres.py` (12), `test_real_postgres_role_smoke.py` (1) | **31 passed, 0 failed** in 33.20s |
| Backend final | `pytest tests/ -q` | **885 passed, 1 skipped, 0 failed** in 53.60s |
| Mobile final | `npm test` | **281 passed, 0 failed, 0 skipped** in 2.47s |
| TypeScript | `npm run typecheck` (`tsc --noEmit`) | exit 0 |
| Expo Doctor | `npx expo-doctor` | **21/21 passed** (after moving splash to `expo-splash-screen` plugin and cleartext to `plugins/withCleartextDisabled.js`) |
| Expo export | `npm run export:android` (`EXPO_PUBLIC_API_BASE_URL` placeholder) | exit 0; Hermes bundle `_expo/static/js/android/AppEntry-8466fc72ce54b4ea783699fd834cfa76.hbc` 3.7MB |
| Lockfile consistency | `npm ci --dry-run` | exit 0 |
| compileall | `python -m compileall -q` (excluding venv/node_modules) | exit 0 |
| Local source audits | `python tools/audit_all.py` | ALL LOCAL SOURCE AUDITS PASSED |
| Dynamic SQL | `python tools/audit_dynamic_sql.py` | DYNAMIC_SQL_CALLS 2 APPROVED 2 ERRORS 0 |
| Lint | — | not configured in package.json (no lint script) |

Skipped (repository-designed): `tests/test_agent_c_notifications_read.py` — requires a disposable PostgreSQL hostname that is not `localhost` / `127.0.0.1`.

Defects found and fixed in this block:
- Windows `ZoneInfo` failed without the `tzdata` package; added `tzdata==2025.2` to `requirements-core.txt`.
- `test_trained_text_artifact_gate` still treated `config.json` alone as staged; updated to require a real weight file and reject an LFS pointer (matches `safety/littlenet_trained_text.py`).
- Expo SDK 57 schema rejected top-level `splash` and `android.usesCleartextTraffic`; splash stays on the existing plugin; cleartext remains forced false via `mobile_app/plugins/withCleartextDisabled.js`.

NOT EXECUTED: live Neon / Cloudflare R2 / Resend / Modal / EAS cloud build; real-device playback; Android APK; pip-audit / bandit / gitleaks (CI-only scanners, not installed here).
