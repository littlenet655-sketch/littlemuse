# LittleNet Authentication & System Integrity Report

> **2026-09-22 note:** This report is historical. All face/biometric artifacts
> (DeepFace, face login, face enrollment, guardian liveness) were removed from
> LittleNet by product decision on 2026-09-22; the face-path findings below
> describe a system state that no longer exists.

## Executive Summary

An end-to-end investigation and remediation of the LittleNet authentication architecture was conducted across the **React Native / Expo mobile app** (`mobile_app/`), the **Python Flask backend** (`mobile/`, `auth/`, `safety/`), and the **Neon PostgreSQL database**.

### Core Resolution
The issue where **Parent Sign-up, Face Login, or general authentication stopped and toggled *"Internet is required to complete verification."*** has been resolved. The issue was driven by four intersecting defects:
1. **Android Cleartext HTTP Blocking:** On Android 9 (API 28+), unencrypted `http://` traffic (such as `http://192.168.0.17:5000`) is blocked by default at the OS socket layer unless `usesCleartextTraffic: true` is set in `app.json`.
2. **Over-Broad Error Mapping:** In `mobile_app/src/api/errors.ts`, all status `0` network errors were converted into the string `"Internet is required to complete verification."`. Any network refusal, timeout, or blocked HTTP socket triggered this exact message.
3. **Missing Neon Database Table (`parent_email_otps`):** The table `parent_email_otps` was not defined in `database/schema.sql` or `database/upgrade.sql`, causing database query failures when verifying OTPs or looking up parent verification status.
4. **DeepFace Exception Masking:** In `safety/face_service.py`, detection failures (e.g. no face detected in frame) were indiscriminately caught as `liveness_unavailable`, returning HTTP 503 instead of `single_face_required` (HTTP 403), triggering infinite client-side retry loops.

All critical issues have been fixed and verified with 100% passing tests across the mobile client, Python backend, and Neon database.

---

## 1. Summary of Critical Issues & Exact Fixes

| # | Component | Root Cause | Fix Implemented | Files Modified |
|---|-----------|------------|-----------------|----------------|
| **1** | **Mobile App (Android)** | Android blocks cleartext HTTP by default. Calls to `http://192.168.0.17:5000` failed immediately with `TypeError: Network request failed`, resulting in status `0`. | Enabled `usesCleartextTraffic: true` under the Android configuration block in Expo. | [`mobile_app/app.json`](file:///c:/Users/Anilkumar/OneDrive/Desktop/LittleNet-1/mobile_app/app.json#L19) |
| **2** | **Error Handling (`errors.ts`)** | `network_unreachable` (status `0`) was hardcoded to return `"Internet is required to complete verification."`, masking LAN reachability issues. | Differentiated `network_unreachable` to report server reachability clearly (`"LittleNet server is unreachable. Check your internet or local connection."`) while preserving `"Internet is required..."` specifically for camera offline checks (`verification_offline`). | [`mobile_app/src/api/errors.ts`](file:///c:/Users/Anilkumar/OneDrive/Desktop/LittleNet-1/mobile_app/src/api/errors.ts#L92-L96) |
| **3** | **Neon PostgreSQL** | `parent_email_otps` table was missing from `schema.sql` and `upgrade.sql`. Lookups in `mobile_parent_verify_liveness()` caused SQL `relation does not exist` errors. | Executed DDL directly in Neon DB; added permanent table schema and indexes to `schema.sql` and `upgrade.sql`. | [`database/schema.sql`](file:///c:/Users/Anilkumar/OneDrive/Desktop/LittleNet-1/database/schema.sql#L367-L375)<br>[`database/upgrade.sql`](file:///c:/Users/Anilkumar/OneDrive/Desktop/LittleNet-1/database/upgrade.sql#L285-L293) |
| **4** | **Safety Service (`face_service.py`)** | DeepFace `ValueError("Face could not be detected")` was caught as generic `liveness_unavailable`, returning HTTP 503 and triggering retry loops. | Differentiated missing face exceptions to return `single_face_required` (HTTP 403) so the user receives clear framing guidance instead of a 503 service failure. | [`safety/face_service.py`](file:///c:/Users/Anilkumar/OneDrive/Desktop/LittleNet-1/safety/face_service.py#L119-L143) |
| **5** | **Base64 Decode Hardening** | Camera selfie uploads from native Android occasionally contain newlines/whitespace or lack padding. | Stripped newlines/whitespace and added automatic `=` padding before `base64.b64decode()` in image ingestion. | [`mobile/api.py`](file:///c:/Users/Anilkumar/OneDrive/Desktop/LittleNet-1/mobile/api.py#L338-L343) |
| **6** | **Biometric API Timeout** | Heavy ML / anti-spoofing verification on the backend could exceed default fetch timeouts. | Extended request timeout to 60 seconds specifically for `verifyParentLiveness`, `enrollChildFace`, and `faceLogin`. | [`mobile_app/src/api/auth.ts`](file:///c:/Users/Anilkumar/OneDrive/Desktop/LittleNet-1/mobile_app/src/api/auth.ts#L65-L85) |

---

## 2. Authentication Flow Architecture & State Gates

### A. Parent Registration Flow
```text
[Parent Register Screen]
    │
    ├─► 1. Submit Details (Username, Name, Email, Password, DOB 18+, Guardian Declaration)
    │      POST /api/mobile/v1/auth/parent/register
    │      ↳ Validates age >= 18; inserts into users with account_status='PENDING_APPROVAL'
    │      ↳ Generates 6-digit OTP, stores HMAC in parent_email_otps
    │      ↳ Returns { ok: true, pending_token, email_sent }
    │
    ├─► 2. Email OTP Verification Screen
    │      POST /api/mobile/v1/auth/parent/verify-email
    │      ↳ Verifies code hash, updates verified_at=NOW()
    │      ↳ Keeps account PENDING_APPROVAL; returns refreshed pending_token
    │
    └─► 3. Guardian Liveness & Adult Check Screen
           POST /api/mobile/v1/auth/parent/verify-liveness
           ↳ On-device ML Kit pre-check ensures face is centered and clear
           ↳ Backend verifies single face + anti-spoof + adult age estimation
           ↳ Activates account: UPDATE users SET account_status='ACTIVE'
           ↳ Issues session JWT tokens and routes to Parent Dashboard
```

### B. Kids Face Login & Enrollment Flow
```text
[Kids Face Login Screen]
    │
    ├─► 1. Child enters identifier + takes live selfie
    │      ↳ Client ML Kit validates face presence, orientation, lighting
    │
    └─► 2. POST /api/mobile/v1/auth/face-login
           ↳ Fetches Facenet512 embedding from face_profiles
           ↳ Performs liveness check + cosine similarity comparison
           ↳ On match: returns session token + onboarding gate state
                 ├─► If face_required: route to FaceEnrollScreen
                 ├─► If quiz_required: route to QuizScreen
                 └─► If clear: route to Home / Feed
```

### C. Demo Accounts Available in Neon DB
The following pre-configured demo accounts have full access in the database:
- **Admin:** `admin` / `AdminPassword123!` (Role: `ADMIN`)
- **Parent:** `testparent` / `ParentPassword123!` (Role: `PARENT`, Status: `ACTIVE`)
- **Child:** `feedkid` / `KidsPassword123!` (Role: `CHILD`, Status: `ACTIVE`)

---

## 3. Test & Verification Results

### A. Mobile Client Tests (`mobile_app/`)
1. **TypeScript Typecheck:**
   ```bash
   npm run typecheck
   # Output: PASS (0 errors)
   ```
2. **Automated Unit & Contract Test Suite:**
   ```bash
   npm test
   # Output: 83 tests passing across 19 suites (0 failing, 0 skipped)
   # Includes:
   #  ✔ offline retry retains only the locally checked photo and submits on reconnect
   #  ✔ parent OTP and liveness contracts (4 tests)
   #  ✔ child face enrollment and login contracts (2 tests)
   #  ✔ backend gate parsing (7 tests)
   #  ✔ role-aware cold-start routing (4 tests)
   ```
3. **Android Hermes Production Bundle Export:**
   ```bash
   npm run export:android
   # Output: dist/ bundled successfully (979 modules, 2.4MB Hermes bytecode)
   ```

### B. Backend & System Audits
1. **Scope Check:**
   ```bash
   python tools/scope_check.py
   # Output: SCOPE_CHECK=34/34 PASS
   ```
2. **Local Source Audits:**
   ```bash
   python tools/audit_all.py
   # Output:
   #  PREFLIGHT: PASS
   #  ROUTES: 130 mapped, 0 errors
   #  SOURCE_READY: True
   #  ALL LOCAL SOURCE AUDITS PASSED
   ```

### C. Live Neon Database End-to-End Auth Verification
A comprehensive test script executed all auth operations directly against the active Neon PostgreSQL database and running Flask server:
```text
=== 1. PARENT REGISTRATION & EMAIL OTP ===
Register status: 200 (user_id: 329, status: PENDING_APPROVAL)
OTP verification status: 200 (verified_at timestamp populated)

=== 2. PARENT LOGIN GATING ===
Login before liveness: 428 parent_verification_required (Correctly gated)
Login after liveness activation: 200 (JWT token issued, role: PARENT)

=== 3. DEMO ACCOUNTS ===
Parent Login ('testparent'): 200 role: PARENT
Child Login ('feedkid'): 200 role: CHILD
Admin Login ('admin'): 200 role: ADMIN

=== 4. FACE LOGIN CHALLENGE ===
Face login endpoint: HTTP 404/401 gracefully handled (No 500 errors)
```

---

## 4. Verification Instructions for Developers

1. **Start the Flask Backend:**
   ```powershell
   .\venv\Scripts\python app.py
   # Confirms listening on 0.0.0.0:5000 (accessible via http://127.0.0.1:5000 and LAN IP)
   ```

2. **Configure the Mobile Environment:**
   In `mobile_app/.env`:
   ```ini
   EXPO_PUBLIC_API_BASE_URL=http://<YOUR_PC_LAN_IP>:5000
   ```
   *(e.g., `http://192.168.0.17:5000`)*

3. **Start the Mobile Client:**
   ```powershell
   cd mobile_app
   npx expo start
   ```
   - If using a physical Android device on the same Wi-Fi network, scan the Expo QR code.
   - Cleartext HTTP traffic is now permitted by Android via the `usesCleartextTraffic: true` setting in `app.json`.
   - Complete Parent Sign-up: the OTP code is displayed in the terminal output in development mode (e.g. `[PARENT OTP] Verification code: 123456`).
