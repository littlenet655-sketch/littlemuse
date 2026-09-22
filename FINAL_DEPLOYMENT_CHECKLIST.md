# LittleNet — Final Deployment Checklist

Pre-deploy checklist for the fully-fixed tree. Nothing below has been executed against production; this is the runbook, not a log.

## 1. Secrets & config (do not skip)

- [ ] Provision production secrets through the approved vault flow: `DATABASE_URL` (Neon), R2 `S3_*` credentials, Flask `SECRET_KEY`, SMTP credentials, push-notification keys.
- [ ] Confirm **no real `.env` is committed** — repo must contain only `.env.example`. (Archive verification: `git ls-files | grep -iE '\.env$|token|secret|pem$'` must show only `.env.example` and docs.)
- [ ] Set `EXPO_PUBLIC_API_BASE_URL` to the production API origin for the mobile build. It is the only expected mobile env var.
- [ ] Verify `LITTLENET_ENV=production` (or equivalent) disables the `mock-put` upload fallback — covered by `test_mock_put_disabled_in_production`.

## 2. Database (Neon / PostgreSQL 16 + pgvector)

- [ ] `CREATE EXTENSION IF NOT EXISTS vector;`
- [ ] `python tools/init_db.py` (baseline; idempotent, refuses destructive content)
- [ ] `dbmate --no-dump-schema --migrations-dir db/migrations up` → expect 21 applied, 0 pending
- [ ] Re-run `dbmate up` → expect no-op (idempotency check)
- [ ] Back up before first production migration.

## 3. Storage & media (R2)

- [ ] Private R2 buckets for quarantine + published media; signed-URL TTLs as configured.
- [ ] Confirm direct-upload presign flow works end-to-end in staging before enabling.
- [ ] Confirm the media worker (Modal or local) processes `PROCESSING` jobs: BLOCK / REVIEW / ALLOW paths.
- [ ] Confirm `capture_r2_delete_targets` coverage if post deletion is later added (gap 3 — not in this tree).

## 4. Backend deploy

- [ ] Install `requirements.txt` (+ `requirements-ai/safety/modal` as needed for the worker tier).
- [ ] Run the full pytest suite against a staging DB before promoting.
- [ ] Verify 238 Flask routes register (`create_app()` smoke).
- [ ] Confirm rate limits, CSRF exemptions, and bearer auth on `/api/mobile/*`.

## 5. Mobile release

- [ ] `npm run typecheck`, `npm test`, `npx expo install --check` green.
- [ ] `npm run export:android` then **Gradle `assembleDebug` on a machine with localhost TCP** (sandbox-blocked here): `export ANDROID_HOME=/opt/android-sdk && npx expo prebuild --platform android && ./gradlew assembleDebug` (JDK 17).
- [ ] Verify package `com.littlenet.app`, CAMERA permission present, RECORD_AUDIO absent.
- [ ] Follow PHYSICAL_DEVICE_CHECKLIST.md on at least one Android device before store submission.

## 6. Safety gates (must all hold in staging)

- [ ] Unverified parent cannot be activated (web admin 403, bearer admin 403).
- [ ] Legacy v1 sync upload returns 410; all uploads go through v2 quarantine.
- [ ] REVIEW chat messages never reach the receiver (run `test_message_review_visibility.py` E2E against a disposable DB host).
- [ ] Child password-login failures return one generic, non-enumerating message (face login removed 2026-09-22).
- [ ] Child PII redacted before any AI call.

## 7. Do NOT do

- Do not run `dbmate up` on an empty DB without `tools/init_db.py` first.
- Do not enable Cloudflare Stream paths unless R2 fallback is retained (private R2 is the fallback).
- Do not publish the APK/AAB until the physical-device checklist passes.
