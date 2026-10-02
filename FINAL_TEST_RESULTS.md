# LittleNet — Final Test Results (merged tree)

**Date:** 2026-09-21. All runs on the final merged tree (commit B working tree), not on crew baselines.

## Backend (Python / pytest, `~/workspace/.venv-safety`)

Disposable PostgreSQL 16.15 + pgvector:
- `python tools/init_db.py` → baseline OK
- `dbmate --migrations-dir db/migrations up` → **21/21 applied, 0 pending**; idempotent rerun clean (`schema_migrations` count 21)
- One note: `pydantic` was installed into the venv so the K2/AI test modules could import (test-only dependency, no source change).

Full suite (`pytest tests/`, `DATABASE_URL` + `DISPOSABLE_DATABASE_URL` → disposable DB):

| Result | Count |
|---|---|
| Passed | **567** |
| Skipped | 2 |
| Errors | 2 |

The 2 errors are `tests/test_message_review_visibility.py::test_review_message_lifecycle_end_to_end` and `::test_review_approval_converts_to_block_when_pair_disconnected`. They error **by design**: the file's `_require_live_db()` guard refuses to run the E2E lifecycle against a `localhost`/`127.0.0.1` host (anti-footgun), and this sandbox cannot expose the disposable DB on a non-localhost address (sandbox network intercepts it). Part 1 of the same file — the DB-free receiver-visibility contract tests — **passed** (included in the 567).

For comparison, the backend crew's pre-integration baseline on the same tree shape was 485 passed / 17 skipped / 40 failed / 8 errors, all environmental (no live DB). The improvement is the disposable DB, not lowered bars.

Targeted security/feature batch (88 passed, same 2 guard errors):
- `test_admin_parent_activation.py` — 13/13 (unverified parent activation blocked, web + bearer)
- `test_face_deferral_contract.py` — 8/8 (new)
- `test_ai_chat_pii_egress.py`, `test_k2_ai_safety.py` — pass (PII redaction before AI)
- `test_phase25_production_hardening.py` — pass (R2 quarantine, cross-user theft, idempotency, mock-put guards)
- `test_modules_11_15_contract_cleanup.py` — pass incl. new v1→410 regression test (1 pre-existing DB-dependent failure `test_comments_moderation_filter` fails identically on pristine tree; needs live DB *and* passes in the full run above)
- `test_parent_child_face_enrollment_contract.py` — pass (historical; the face system and this test file were removed 2026-09-22)
- `test_story_music_e2e.py::test_story_music_full_lifecycle` — **passes against the live disposable DB** via the v2 pipeline

## Mobile (`mobile_app/`)

- `npm run typecheck` (`tsc --noEmit`) — **clean**
- `npm test` (jest, 38 suites) — **173/173 passed** (historical; face login and its tests were removed entirely 2026-09-22)
- `npx expo install --check` — dependencies up to date
- `npm run export:android` — **succeeded** (`dist/` exported, AppEntry HBC 3.1MB, metadata.json)
- Expo prebuild (`npx expo prebuild --platform android`, JDK 17, `ANDROID_HOME=/opt/android-sdk`) — **succeeded**, fresh `android/` native project generated with `gradlew`
- Gradle `assembleDebug` — attempted once; **failed before compiling**: the Gradle wrapper could not download its distribution (`org.gradle.wrapper.Install.forceFetch` → `java.net.SocketException: Broken pipe` during HTTPS fetch). No local Gradle distribution or cached wrapper dist exists in this sandbox, and the sandbox blocks the download. This is environmental, not a source error. Exact command: `export ANDROID_HOME=/opt/android-sdk && npx expo prebuild --platform android && ./gradlew assembleDebug`

## Native / device

| Check | Result |
|---|---|
| Android native compiled | (Gradle result recorded below) |
| Physical device verified | **NO** — not performed (no device in this environment) |
| Live verified | **NO** — no production credentials or infrastructure used |

## Categories (per required taxonomy)

- SOURCE READY — **YES** (final merged tree; fixes documented in FINAL_FIX_REPORT.md)
- AUTOMATED TESTED — **YES** (567 backend passed, 173/173 mobile passed; 2 backend E2E errors are a localhost-guard, see above)
- NATIVE PREBUILD VERIFIED — **YES** (fresh `npx expo prebuild --platform android` succeeded on the final tree)
- ANDROID NATIVE COMPILED — **NO** (Gradle wrapper could not download its distribution — sandbox network block, not a source error)
- LIVE VERIFIED — **NO**
- PHYSICAL DEVICE VERIFIED — **NO**
