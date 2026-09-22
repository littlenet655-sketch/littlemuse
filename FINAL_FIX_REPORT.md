# LittleNet — Final Fix Report

**Date:** 2026-09-21
**Repo:** `~/workspace/LittleNet-1`, branch `main`
**Scope:** Full integration of the backend crew + mobile crew fixes, plus integration fixes found by read-only audits. Source fixes only — no deployment, no production data touched.

## Commit lineage (exactly two new commits on top of the frozen crews)

| Commit | Message | Content |
|---|---|---|
| `3ceacd5` | (frozen backend crew) | 46 non-`mobile_app/` paths |
| `ce6b39a` | (frozen mobile crew) | 47 `mobile_app/` paths — disjoint from backend crew |
| `401fa06` | `integration-security: block admin activation of unverified parents (A)` | Commit A — exactly 4 files vs parent `ce6b39a`: `admin/routes.py`, `auth/service.py`, `mobile/admin_api.py`, `tests/test_admin_parent_activation.py` |
| `backup/pre-fix-20260921` | safety backup branch at original HEAD `7b33fe8` | Preserved, never rewritten |

Commit B (this integration) is the only other new commit.

## Commit A — admin activation of unverified parents (recap)

- `auth/service.py`: new `parent_verification_complete(parent_user_id)` — authoritative evidence only: `parent_verifications.verification_status='VERIFIED'`, or `parent_email_otps.verified_at` set (verified email OTP is the complete parent identity verification — no face/liveness step).
- `admin/routes.py`: web admin ACTIVATE of an unverified parent → HTTP 403, logs `USER_ACTIVATE_BLOCKED`.
- `mobile/admin_api.py`: bearer admin status endpoint → HTTP 403 `{"error":"parent_verification_incomplete"}`, logs `USER_STATUS_BLOCKED`.
- `tests/test_admin_parent_activation.py`: 13 tests.

## Commit B — integration fixes (this report)

### B1. Release blocker: child face-enrollment deferral dead end (audit gap 8)

The child's "Skip for Now" button (`POST /api/mobile/v1/kids/face/skip`) unconditionally returned 403 `parent_approval_required`, while **nothing in the backend ever set `child_profiles.face_enrollment_skipped=TRUE`** and Parent Mode had no approval action. A child unable to enroll was hard-stuck at FaceEnroll.

- `mobile/api.py`: new `POST /api/mobile/v1/parent/children/<id>/face/deferral` (`@_require_mobile('PARENT')`, `owns()` check, 30/hour rate limit). Body `{action: 'approve'|'reject'}` → sets `face_enrollment_skipped`, writes `FACE_DEFERRAL_APPROVED`/`FACE_DEFERRAL_REJECTED` audit log, `notify()`s the child. No schema change needed (column exists, migration `20260920160000_child_face_enrollment_skipped.sql`).
- `mobile/api.py`: `mobile_child_face_skip` now returns `{ok, deferred}` when the parent has approved; still 403 `parent_approval_required` otherwise. The onboarding gate (`_face_gate_satisfied`) already honors the flag, and enrollment clears it.
- `mobile_app/src/api/client.ts`: `routes.parentFaceDeferral(childId)`.
- `mobile_app/src/api/parentAdmin.ts`: `approveFaceDeferral(token, childId, 'approve'|'reject')`.
- `mobile_app/src/screens/parent/ParentScreens.tsx`: new "Allow Face Skip" tile in the child account section with Approve/Decline.
- Child side (`ChildFace.tsx`) needed no change: `onSkip()` already refreshes the gate on success.
- `tests/test_face_deferral_contract.py`: 8 new tests (auth, RBAC, ownership, invalid action, approve/reject audit+notify, skip 403-before / 200-after).

### B2. Security hardening: face-login anti-enumeration (audit gap 11)

`POST /api/mobile/v1/auth/face-login` returned **404 `reason="not_enrolled"`** when the account existed without enrollment vs 401 otherwise — an unauthenticated oracle.

- `mobile/api.py`: every failure now returns uniform `401 {"error":"face_login_failed"}` with no `reason`.
- `auth/routes.py` (web face login, REMOVED 2026-09-22): one generic failure message instead of per-reason text.
- `mobile_app/src/api/errors.ts`: removed the dead per-reason branch (matches the pre-existing uniform message in `ChildFace.tsx::faceLoginFailureMessage`).
- Tests updated: `tests/test_agent_a_state_machine_and_face.py` (uniform-401 assertions), `mobile_app/tests/errors.test.ts`, `mobile_app/tests/contracts.test.ts`. (2026-09-22: the face endpoints and all face tests were removed entirely.)

### B3. Retired stale synchronous upload route (integration review finding)

`POST /api/mobile/v1/kids/posts` was still synchronously publishing uploads (no audio strip, no moderation queue) and conflicted with the v2 quarantine contract the mobile client uses.

- `mobile/api.py`: now returns HTTP **410** `{"error":"deprecated_use_v2_upload","use":"/api/mobile/v2/uploads/session"}`, bearer-protected.
- `mobile_app/src/api/errors.ts`: user message for `parent_verification_incomplete` (audit UX finding).
- Tests: `tests/test_modules_11_15_contract_cleanup.py` asserts the 410; `tests/test_story_music_e2e.py` rewritten to drive the canonical v2 session→complete flow (passes against live DB).

### B4. Cleanup

- Removed unused `captureLivePhoto()` wrapper in `mobile_app/src/camera/livePhoto.ts` (zero call sites); `CapturedPhoto` type still re-exported.
- Removed 4 unreferenced route constants in `mobile_app/src/api/client.ts`: `health`, `friends`, `registerDevice`, `settings` (verified no hardcoded-string call sites).
- TODO/FIXME scan: none in application code. Remaining `NotImplementedError`s are the abstract `VideoDeliveryProvider` interface (intentional). No other stubs/placeholders.

## What was deliberately NOT changed

- Gaps 1, 2, 3, 4, 5, 6, 7, 10 (messages pagination, like/comment/follow notifications, bearer deletion, story-viewer `avatar_url`, media dimensions, v2 home, bearer learning-report, time-limit staleness) — classified FUNCTIONAL GAP / QUALITY per the contract audit; no visible mobile feature calls a missing/broken contract. Documented in `KNOWN_LIMITATIONS.md`.
- No production systems touched: no Neon/R2 writes, no emails sent, no Cloudflare Stream, no APK published, no secrets modified.
- Frozen crew commits and the backup branch were never rewritten.
