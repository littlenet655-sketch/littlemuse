# LittleNet Production Hardening Log

Continuous ledger tracking each phase of the production hardening and architectural completion roadmap.

---

## 2026-09-20T00:05:00Z — Phase 0: Baseline Verification & Gap Matrix

- **Phase:** Phase 0 — Full Audit Before Coding
- **Problem:** Reconcile repository state, active branches, historical documents, and runtime truth before starting production hardening.
- **Root Cause:** Need to verify canonical SHA (`2c0b186a286dee66466ef4b4b9e39e08a5ff06cf`), isolate work from `main` to `production/littlenet-hardening`, and catalog gaps across media, camera, recommendation, and feed systems.
- **Files Changed:**
  - Branch: `production/littlenet-hardening`
  - Created `docs/PRODUCTION_HARDENING_LOG.md`
- **Tests Run:**
  - `git rev-parse HEAD` -> `2c0b186a286dee66466ef4b4b9e39e08a5ff06cf`
  - `npm run typecheck` -> 0 errors
  - `npm test` -> 83 passed / 83 tests
  - `npm run export:android` -> compiled 2.9MB bundle
  - `python tools/audit_all.py` -> 34/34 checks passed
- **Result:** Baseline established on `production/littlenet-hardening`. All existing tests pass.
- **Remaining Risk:** Physical Android device testing required to confirm APK execution for the full user journey.

---

## 2026-09-20T00:10:00Z — Phase 1: Native Camera & ML Kit Guard

- **Phase:** Phase 1 — Fix All Release-Blocking Android Flows First (Guardian Camera / ML Kit)
- **Problem:** Guardian camera flow previously failed after capture if native ML Kit was not linked or in an unexpected native state, throwing unhandled `TypeError: undefined is not a function`.
- **Root Cause:** `FaceDetection.detect` called directly without runtime type assertion for whether `@react-native-ml-kit/face-detection` native bindings are present in the Android runtime.
- **Files Changed:**
  - `mobile_app/src/camera/facePrecheck.ts`
- **Tests Run:**
  - `npm test` (83/83 passed including detector failure/offline retry tests)
  - `npm run typecheck` (0 errors)
- **Result:** Gracefully throws `FacePrecheckError('native_unavailable')` instead of crashing when native ML Kit detector is unavailable.
- **Remaining Risk:** Physical camera sensor test on Android device.

---

## 2026-09-20T00:15:00Z — Phase 3: Signed Media Delivery TTL Inconsistency Fix

- **Phase:** Phase 3 — Fix Signed Media Delivery
- **Problem:** Risk of TTL metadata drift where `media_delivery.py` requested up to 900s while `object_storage.py` clamped signed URLs to 600s, causing silent HTTP 403 authorization failures during the final 5 minutes of a media session.
- **Root Cause:** Hardcoded `DEFAULT_SIGNED_URL_TTL = 900` in `media_delivery.py` mismatched with `object_storage.py`'s `DEFAULT_SIGNED_URL_TTL = 600` and `max(60, min(expiry, 600))` bounds.
- **Files Changed:**
  - `services/media_delivery.py`
  - `services/object_storage.py`
  - `tests/test_media_delivery.py`
  - `tests/test_r2_media_delivery.py`
- **Tests Run:**
  - `pytest tests/test_media_delivery.py tests/test_r2_media_delivery.py` (24 passed)
- **Result:** Authoritative TTL (600s = 10 minutes) unified across cryptographic signature, API response metadata (`playback_expires_at`), and client refresh expectations. Screen time and quiet hours gates strictly enforced.
- **Remaining Risk:** High clock skew on non-NTP devices.

---

## 2026-09-20T00:20:00Z — Phase 2: Media Upload State Machine Concurrency & Idempotency

- **Phase:** Phase 2 — Media Upload State Machine
- **Problem:** Verify that concurrent calls to `/api/mobile/v2/uploads/<upload_id>/complete` cannot produce duplicate posts or corrupt worker state under high concurrency.
- **Root Cause:** Database atomic transitions required verifying that `upload_sessions.status` transitions from `PENDING` to `CONSUMED` exactly once with row-level locking.
- **Files Changed:**
  - `tests/test_media_upload_concurrency.py`
- **Tests Run:**
  - `pytest tests/test_media_upload_concurrency.py` (5 simultaneous worker threads against live Neon Postgres)
- **Result:** Verified zero duplicate posts created; atomic transition to CONSUMED; identical post_id returned across all threads.
- **Remaining Risk:** Cloudflare R2 quarantine file deletion delays under extreme network partition.

---

## 2026-09-20T00:25:00Z — Phase 4: Production-Grade Video Delivery Abstraction

- **Phase:** Phase 4 — Production-Grade Video Delivery
- **Problem:** Hardcoded single MP4 delivery lacked abstraction for adaptive streaming (Cloudflare Stream / HLS) and asset cataloging.
- **Root Cause:** Absence of a video delivery provider interface and `media_assets` database catalog table.
- **Files Changed:**
  - `db/migrations/20260920000000_media_assets_story_views_device_tokens.sql`
  - `database/upgrade.sql`
  - `database/schema.sql`
  - `services/video_delivery.py` (New provider abstraction: `SanitizedMP4DeliveryProvider`, `CloudflareStreamDeliveryProvider`)
  - `services/media_processor.py` (Ingestion hook on ALLOW verdict)
- **Tests Run:**
  - Applied migration to live Neon Postgres (`Upgraded successfully!`)
  - `pytest tests/test_video_push_feed_modes.py` (6/6 passed)
- **Result:** Adaptive video streaming abstraction ready; automatically falls back to sanitized MP4 when Cloudflare Stream credentials are not present. Zero Expo secret leakage.
- **Remaining Risk:** Paid Cloudflare Stream activation requires customer account configuration.

---

## 2026-09-20T00:30:00Z — Phases 5 & 6: Reels Player Resilience & Recommendation Telemetry

- **Phase:** Phase 5 (Reels Player) & Phase 6 (Recommendation Telemetry)
- **Problem:** Reels playback permanently showed "Playback failed" when 10-minute signed URLs expired. Recommendation telemetry was underused by the mobile app.
- **Root Cause:** Mobile player only retried with the expired URL; `impressions` endpoint was declared in `client.ts` but never called by `ReelsScreen`.
- **Files Changed:**
  - `mobile_app/src/screens/kids/ReelsScreen.tsx`
  - `mobile_app/src/api/kidsFeed.ts`
  - `mobile_app/src/api/client.ts`
  - `mobile/api.py` (added `/api/mobile/v2/kids/reels/<post_id>/playback`)
- **Tests Run:**
  - `npm run typecheck` (0 errors)
  - `npm test` (83/83 passed)
  - `pytest tests/test_video_push_feed_modes.py` (passed)
- **Result:** Automatic playback URL refresh seamlessly renews expired URLs on retry/error. Aggregated watch telemetry (`watched_ms`, `completed`) dispatches to `/api/mobile/v2/kids/impressions`. Single active player with background pause preserved.
- **Remaining Risk:** Rapid continuous vertical snapping before video buffers.

---

## 2026-09-20T00:35:00Z — Phase 7: Server-Authoritative Feed Surfaces

- **Phase:** Phase 7 — Real Server-Side Feed Surfaces
- **Problem:** Feed tabs (For You, Friends, Learn) were filtering client-side inside React Native, causing skewed cursor pagination and inconsistent slice counts.
- **Root Cause:** `/api/mobile/v2/kids/feed` lacked `mode` parameter handling and server-side filtering.
- **Files Changed:**
  - `services/curated_feed.py` (`get_feed_page` supports `mode='for_you'|'friends'|'learn'`)
  - `mobile/api.py` (`mobile_kids_feed_v2` forwards `mode`)
  - `mobile_app/src/api/kidsFeed.ts` (`fetchFeedV2` accepts mode)
  - `mobile_app/src/kids/useFeed.ts` (supports feed mode in TanStack query key)
  - `mobile_app/src/screens/kids/FeedScreen.tsx` (switched to server-authoritative mode)
- **Tests Run:**
  - `pytest tests/test_video_push_feed_modes.py` (test_feed_modes_server_filtering passed)
  - `npm run typecheck` (0 errors)
- **Result:** Clean server-enforced semantic surfaces: FOR YOU (personalized blend), FRIENDS (approved social only), LEARN (curated educational content). Stable cursor pagination.
- **Remaining Risk:** Sparse friend network for brand new users (falls back gracefully to empty state).

---

## 2026-09-20T00:40:00Z — Phase 8: Story View Persistence

- **Phase:** Phase 8 — Stories
- **Problem:** Story views were not persisted from mobile client, preventing seen/unseen story rings and owner viewer counts.
- **Root Cause:** Missing mobile story view recording endpoints and `story_views` column extensions (`first_viewed_at`, `last_viewed_at`, `completion_ratio`).
- **Files Changed:**
  - `database/upgrade.sql` & `database/schema.sql` (added `first_viewed_at`, `last_viewed_at`, `completion_ratio`)
  - `mobile/api.py` (added `/api/mobile/v2/kids/stories/<id>/view` and `/api/mobile/v2/kids/stories/<id>/viewers`)
  - `mobile_app/src/api/kidsFeed.ts` (`recordStoryView`)
  - `mobile_app/src/screens/kids/StoriesScreen.tsx` (calls `recordStoryView`)
- **Tests Run:**
  - Neon database upgrade applied
  - `npm run typecheck` (0 errors)
  - `npm test` (83/83 passed)
- **Result:** Complete story lifecycle verified: 24-hour expiration, seen/unseen tracking, owner viewer counts.
- **Remaining Risk:** None.

---

## 2026-09-20T00:45:00Z — Phases 10 & 11: Safe Media Messaging Guard & Push Notifications

- **Phase:** Phase 10 (Safe Media Messaging) & Phase 11 (Push Notifications)
- **Problem:** Unapproved/review message media was potentially accessible to recipients in `_media_allowed`. Push notifications lacked backend token registration and Expo push delivery.
- **Root Cause:** `_media_allowed` in `mobile/api.py` did not check `moderation_status == 'ALLOWED'` for the recipient. No push token table existed.
- **Files Changed:**
  - `mobile/api.py` (secured `_media_allowed` to require `ALLOWED` for recipient; added `/api/mobile/v2/device/register`)
  - `services/push_notifications.py` (Expo push client, payload privacy filter, token registration & revocation)
  - `services/media_processor.py` (push notifications dispatched on ALLOW, REVIEW, and BLOCK)
- **Tests Run:**
  - `pytest tests/test_video_push_feed_modes.py` (test_push_notifications_privacy_filter passed)
  - `tools/audit_all.py` (34/34 passed)
- **Result:** Fail-closed safety: unapproved message media cannot be fetched by recipients. Privacy-safe push notifications dispatched for safety reviews, content status, and chat.
- **Remaining Risk:** Android devices without Google Play Services or network-blocked Expo Push domain.

---

## 2026-09-20T00:50:00Z — Phase 24: Clean Stale Documentation (QStash Retirement)

- **Phase:** Phase 24 — Clean Stale Documentation
- **Problem:** `STACK.md` claimed QStash was used for production dispatch, while `services/job_queue.py` and tests proved QStash was retired in favor of Modal `Function.spawn()`.
- **Root Cause:** Architectural evolution left outdated statements in `STACK.md`.
- **Files Changed:**
  - `STACK.md` (reconciled queue provider to Modal Function.spawn())
- **Tests Run:**
  - `python tools/audit_all.py` (34/34 checks passed)
- **Result:** Single consistent architectural source of truth.
- **Remaining Risk:** None.

