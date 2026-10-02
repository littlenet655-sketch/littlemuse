# Physical Final Smoke Test — Parent Device-Auth

**Keep this checklist as small as reasonably safe.** Everything else is
covered by automation (see `EMULATOR_TEST_REPORT.md`: 216/216 Jest tests,
gate logic, sensitive-action spy tests, direct-navigation audit) or by the
scripted emulator harness (`tools/device_auth_tests/`).

Only real hardware can prove: the *actual* fingerprint sensor, the *actual*
system BiometricPrompt UI, and the *real* camera / ML Kit face pipeline.

## Prerequisites
- Debug APK installed on a real Android phone (API 30+ recommended; one run
  on API 29 or lower if you ship there, for the Keyguard fallback path).
- The phone has a screen lock set (fingerprint enrolled for steps 2–5).

## The checklist (6 steps)

### 1. Install the APK on the real phone
- [ ] `adb install -r app-debug.apk` succeeds; app launches.

### 2. Parent Mode → real fingerprint success
- [ ] Tap Parent Mode → **system** biometric prompt appears (Android UI, not a LittleNet UI).
- [ ] Touch the real fingerprint sensor → Parent Mode opens.

### 3. Sensitive action works after success
- [ ] With Parent Mode open, perform one sensitive action (e.g. change screen-time limit) → it executes without a second prompt (inside the 5-minute window).

### 4. Background → return → biometric required again
- [ ] Press Home (or switch apps), return to LittleNet → attempt a sensitive action → biometric prompt appears again (authorization was invalidated).

### 5. Cancel → action blocked
- [ ] Trigger a sensitive action, **cancel** the system prompt → the action does not execute; no error crash; Parent Mode stays closed (or shows the cancelled state).

### 6. Child password login
- [ ] Child logs in with their password → succeeds.
- [ ] Wrong credentials fail with one generic, non-enumerating message.

## What this checklist deliberately does NOT repeat
- 5-minute window expiry timing, logout/session invalidation, no-lock message
  text, direct-navigation blocking, API-not-called-on-cancel — all covered by
  automated Jest tests (`tests/sensitiveActionGating.test.ts`,
  `tests/parentAuthGate.test.ts`, `tests/parentModeGate.test.ts`).
- PIN-only fallback UI and no-lock blocking UI — covered by the emulator
  harness (`tools/device_auth_tests/run-parent-auth-smoke` profiles `pin`
  and `unsecured`); re-run there, not here.
- Real camera orientation / yaw / ML Kit behavior — **physical device only**;
  step 6 above is the single allowed instance.

## Sign-off
- [ ] All 6 steps pass on one physical device.
- [ ] APK used: _______________ (version/commit `1939c26` or later)
- [ ] Device / API level: _______________
- [ ] Date / tester: _______________

Do not deploy anything. Do not change production.
