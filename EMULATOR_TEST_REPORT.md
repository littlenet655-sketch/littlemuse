# Emulator Test Report — Parent Device-Auth Architecture

**Date:** 2026-09-21
**Commit under test:** `1939c261e3b906bc2333a67d3f85b0869542c5cb`
(`parent-auth: replace parent face verification with Android system authentication`)
**Scope:** everything reasonably testable without a real phone.
**Rule:** no category is marked PASS without direct evidence.

Status key: **PASS** · **FAIL** · **NOT AUTOMATABLE** (in this sandbox; harness scripts provided for a dev machine) · **PHYSICAL DEVICE REQUIRED**

---

## 1. Build validation

| Step | Status | Evidence |
|---|---|---|
| `npm run typecheck` | **PASS** | `tsc --noEmit` clean |
| `npm test` (full suite) | **PASS** | 216 tests, 216 pass, 0 fail, 0 skipped |
| `npx expo install --check` | **PASS** | "Dependencies are up to date" |
| `npm run export:android` | **PASS** | Exported `dist` successfully |
| `npx expo prebuild --platform android --clean` | **PASS** | Native files regenerated; `ParentDeviceAuthModule.kt` + `ParentDeviceAuthPackage.kt` present; `MainApplication.kt` registers `ParentDeviceAuthPackage()`; `androidx.biometric:biometric:1.2.0-alpha05` in `app/build.gradle` |
| Gradle `assembleDebug` | **FAIL** (environmental) | Gradle wrapper cannot download the distribution in this sandbox (`SSLException` via proxy). No local Gradle. **ANDROID NATIVE COMPILED remains NOT VERIFIED.** Unrelated to the code — retry on a dev machine with network. |

---

## 2. Automated test results (runnable here)

### 2a. Sensitive-action gating — 8/8 PASS
New: `mobile_app/tests/sensitiveActionGating.test.ts`

**Runtime (API-spy) tests — PASS:**
- auth **cancel** → API spy never called, "Authentication cancelled" alert shown
- auth **failure** → API spy never called
- **no device credential** → API spy never called, "Screen lock required" path taken
- auth **success** → API called exactly once

**Static dominance audit — PASS:**
- All 14 sensitive call sites across `ParentScreens.tsx` / `Parent.tsx` are lexically dominated by `ensureParentAuthForAction()`:
  - `createChild`, `resetChildPassword`, `resetChildFace`, `enrollChildFaceByParent` (parent-assisted child enroll), `approveFaceDeferral`, `unlinkChild`
  - `resolveParentReview` (APPROVE/BLOCK), `updateTimeLimit`, `extendChildScreenTime`, `resetChildScreenTime`, `updateParentControls`, `resolveFollowRequest` (approve/reject) — all via gated `.mutate()` calls
- Read-only APIs (`fetchParentDashboard`, `markParentNotificationsRead`, …) intentionally remain ungated — asserted by test
- `RootNavigator` wraps the Parent navigator in `<ParentModeGate>` — asserted by test

### 2b. Gate logic — PASS (pre-existing suites, re-run)
- `parentAuthGate.test.ts`, `parentDeviceAuth.test.ts`, `parentModeGate.test.ts` (11 component tests): all pass, covering system-auth success, device-credential success, cancel/failure blocked, exact no-lock message, background/foreground re-auth, session invalidation, direct-navigation blocking.

### 2c. Child face (removed 2026-09-22 — historical result below)

> 2026-09-22 note: all face artifacts were removed from LittleNet by product
> decision. The 43/43 PASS result below is historical, recorded when the face
> path still existed.

### 2c (historical). Child face — 43/43 PASS
- `cameraRuntime`, `faceQuality`, `livenessStateMachine`, `flows`, `controller`: 43 tests pass, 0 fail.
- No child-face source file was modified by this harness.

---

## 3. Emulator scenarios (Profiles A / B / C)

**Status: NOT AUTOMATABLE in this sandbox.**
This sandbox has no KVM, the Android SDK `sdkmanager` cannot fetch packages behind the proxy (`NoSuchElementException` on repo fetch), and `/tmp` is a 512 MB tmpfs — the emulator (~550 MB) + system image (~1 GB) physically cannot fit. `adb` (platform-tools) was installed and verified working, but there is no emulator binary and no system image to boot.

**The full harness is written and ready on a dev machine:** `tools/device_auth_tests/`
- `common.sh` — shared env, AVD create/boot helpers, boot waiter
- `start-biometric-avd` — Profile A (secure lock + fingerprint)
- `start-pin-avd` — Profile B (PIN, biometrics cleared)
- `start-unsecured-avd` — Profile C (no lock at all)
- `install-debug-apk`, `simulate-fingerprint` (`adb emu finger touch`), `reset-app`, `collect-logcat`
- `run-parent-auth-smoke [serial] [biometric|pin|unsecured]` — guided scenario runner that drives everything adb can drive and records PASS/FAIL per scenario to a timestamped report
- `androidTest/ParentDeviceAuthInstrumentedTest.kt` — drop-in instrumented tests for the native module (contract shape, `canAuthenticate` consistency, **no credential material ever exposed**, repeatability, no-activity rejection)

### Profile A — biometric device (scripted, awaiting emulator)

| # | Scenario | Status |
|---|---|---|
| 1 | Open Parent Mode | NOT AUTOMATABLE here |
| 2 | System biometric prompt appears | NOT AUTOMATABLE here |
| 3 | Simulated fingerprint succeeds | NOT AUTOMATABLE here |
| 4 | Parent Mode opens | NOT AUTOMATABLE here |
| 5 | 2nd protected action < 5 min does not re-prompt | **PASS** (unit: `parentAuthGate` window logic) |
| 6–8 | Background → return invalidates auth; prompt reappears | **PASS** (unit: invalidation on AppState/background; component test) |
| 9 | Fingerprint prompt appears again | NOT AUTOMATABLE here |
| 10 | Cancel prevents Parent Mode/action | **PASS** (unit + spy test) |
| 11 | Failed biometric prevents protected action | **PASS** (unit + spy test) |
| 12 | Logout invalidates auth window | **PASS** (unit) |
| 13 | Session/account change invalidates auth window | **PASS** (unit) |

### Profile B — device credential only (scripted, awaiting emulator)

| # | Scenario | Status |
|---|---|---|
| 1 | Parent Mode available | NOT AUTOMATABLE here |
| 2 | System falls back to DEVICE_CREDENTIAL | **PASS** (unit: `parentDeviceAuth` fallback mapping; native module code path reviewed — API 30+ `BIOMETRIC_STRONG\|DEVICE_CREDENTIAL`, ≤29 Keyguard fallback) |
| 3 | Correct credential opens Parent Mode | NOT AUTOMATABLE here |
| 4 | Cancel prevents entry | **PASS** (unit + spy test) |
| 5 | Sensitive actions remain gated | **PASS** (8/8 gating tests) |
| 6 | 5-minute window works | **PASS** (unit) |
| 7 | Background/logout/session invalidates | **PASS** (unit) |
| — | No LittleNet custom PIN exists | **PASS** (verified: no PIN UI/code in source; native module only calls system APIs) |

### Profile C — no device security (scripted, awaiting emulator)

| # | Scenario | Status |
|---|---|---|
| — | Parent Mode blocked with exact message `"Set up a screen lock on this phone to use Parent Mode."` | **PASS** (unit: exact-string test; native module returns `NOT_ENROLLED`) |
| — | Security-settings button works | NOT AUTOMATABLE here (unit covers the `openSettings` call path) |
| — | No sensitive API action executes | **PASS** (spy tests: denied gate → API never called) |
| — | Direct/deep navigation cannot bypass `ParentModeGate` | **PASS** (11 component tests + static RootNavigator audit for ParentControls/ParentChildDetail/ParentSafetyReview/ParentSettings) |

### Child-face camera smoke on emulator
- **NOT AUTOMATABLE here** (no emulator). Marked **PHYSICAL DEVICE REQUIRED** for real camera orientation/yaw/ML Kit face behavior. Camera *logic* (43 tests) passes; do not claim on-device camera behavior without a device.

---

## 4. Native module instrumented tests

`tools/device_auth_tests/androidTest/ParentDeviceAuthInstrumentedTest.kt` — **source-ready, NOT RUN** (requires `connectedDebugAndroidTest` on an emulator; cannot run here). Covers: module name, result-map contract (exactly the 4 documented boolean keys), `canAuthenticate` consistency invariant, **no credential material in the result map** (asserts no key contains pin/password/pattern/template/secret/token/credential), repeatability, clean rejection without an activity.

---

## 5. Summary counts

- **PASS:** 216/216 Jest tests (incl. 8 new gating tests), typecheck, export, prebuild, child-face 43/43, all unit-coverable auth scenarios
- **FAIL:** Gradle `assembleDebug` (environmental — sandbox network; not a code defect)
- **NOT AUTOMATABLE here:** live emulator scenarios (Profiles A/B/C UI flows), instrumented tests — full scripted harness provided under `tools/device_auth_tests/`
- **PHYSICAL DEVICE REQUIRED:** real biometric sensor behavior, real camera orientation/yaw/ML Kit — see `PHYSICAL_FINAL_SMOKE_TEST.md`

**No production system was touched. No deployment occurred. The device-auth architecture was not modified.**
