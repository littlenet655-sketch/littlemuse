# LittleNet — Final Deployment Checklist

Pre-deploy checklist for the fully-fixed tree. Nothing below has been executed against production; this is the runbook, not a log.

## 1. Secrets & config (do not skip)

- [ ] Provision production secrets through the approved vault flow: `DATABASE_URL` (Neon), R2 `S3_*` credentials, Flask `SECRET_KEY`, SMTP credentials, push-notification keys.
- [ ] Confirm **no real `.env` is committed** — repo must contain only `.env.example`. (Archive verification: `git ls-files | grep -iE '\.env$|token|secret|pem$'` must show only `.env.example` and docs.)
- [ ] Set `EXPO_PUBLIC_API_BASE_URL` to the production API origin for the mobile build. It is the only expected mobile env var.
- [ ] Verify `LITTLENET_ENV=production` (or equivalent) disables the `mock-put` upload fallback — covered by `test_mock_put_disabled_in_production`.

## 2. Database (Neon / PostgreSQL 16 + pgvector)

- [ ] Take/verify a Neon restore point before a release migration.
- [ ] For the retained release database, run `modal run modal_web.py --migration-status-check` and require tracked/coherent history.
- [ ] Apply only reviewed pending deltas with `modal run modal_web.py --migrate-db`.
- [ ] Run the status check again and require zero pending versions.
- [ ] Use `python tools/init_db.py` only for a genuinely fresh database baseline.
- [ ] See `docs/DATABASE_RELEASE_RECONCILIATION.md` for stop/rollback rules.

## 3. Storage & media (R2)

- [ ] Private R2 buckets for quarantine + published media; signed-URL TTLs as configured.
- [ ] Confirm direct-upload presign flow works end-to-end in staging before enabling.
- [ ] Confirm the media worker (Modal or local) processes `PROCESSING` jobs: BLOCK / REVIEW / ALLOW paths.
- [ ] Confirm native post/story deletion removes database visibility immediately and queues/reconciles private R2 cleanup.

## 4. Backend deploy

- [ ] Install `requirements.txt` (+ `requirements-ai/safety/modal` as needed for the worker tier).
- [ ] Run the full pytest suite against a staging DB before promoting.
- [ ] Verify the real Flask app boots with no duplicate endpoints and the mobile route-map regression tests pass.
- [ ] Confirm rate limits, CSRF exemptions, and bearer auth on `/api/mobile/*`.

## 5. Mobile release

- [ ] Confirm app.json owner = `akshu1245s-team`, EAS projectId = `c4ce834d-fd50-4504-a311-820c3372b6dc`, package = `com.littlenet.app`.
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
