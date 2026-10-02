# Final Fix Report — PARTIAL

This report covers only what was actually examined. The prompt's allowed statuses were extended with
**NOT AUDITED** because many issues were not reached; they are NOT claimed as fixed or verified.

| ID | Problem | Root Cause | Fix / Finding | Status | Verification |
|---|---|---|---|---|---|
| 1 | Source/live/APK drift | Unknown live version | Recorded identity; live Modal/APK not inspectable | EXTERNAL VERIFICATION REQUIRED | RELEASE_IDENTITY.md |
| 2 | Moderation _merge_signals drops visual signals | services/media_processor.py::_merge_signals | Already fixed upstream (7e15e2d) with regression test; a second unused copy exists in mobile/api.py (left untouched) | ALREADY FIXED / VERIFIED | code inspection + full suite green |
| 3 | Parent Review flow | — | Handler audited: approved-link scoping, FOR UPDATE, ownership recheck, 404 on foreign event, terminal-block guard. Existing real-DB approve/block tests. Gap: no direct test for child-role call / invalid action / duplicate decision. Live E2E REQUIRES LEGITIMATE REVIEW EVENT | ALREADY FIXED / VERIFIED | existing tests; see KNOWN_LIMITATIONS |
| 4 | Stuck PROCESSING/PENDING media | Retry backoff clock skew (media_processor) | Backoff bug fixed. Full upload lifecycle, cleanup scripts, abandoned-upload handling NOT fully audited | FIXED (backoff only) — remainder NOT AUDITED | tests/test_upload_session_timezone.py |
| 5 | Timezone/timestamp correctness | Naive TIMESTAMP columns read in DB session tz; Python labelled/wrote UTC | Fixed upload_sessions, media backoff, approval token. Not fixed: services/recommendation.py (~line 203, small effect). Other tables not swept | FIXED (3 sites) — sweep incomplete | tests/test_upload_session_timezone.py (fail pre-fix, pass post-fix) |
| 6 | R2 consistency / storage map | — | NOT AUDITED; R2_STORAGE_MAP.md NOT produced | NOT AUDITED | — |
| 7 | Reel codec HEVC vs H.264 | — | NOT AUDITED; ffprobe not run; no transcode tool added | NOT AUDITED | — |
| 8 | Reel startup/playback | — | Existing reelStartup tests pass; playback-428 handoff added. No device test | EXTERNAL VERIFICATION REQUIRED | mobile tests 281 pass |
| 9 | HTTP 428 retry storm | Playback 428 showed generic error, no quiz handoff | HTTP layer already never retried 428 (verified + tests). Added playback handoff and per-activation bound | FIXED | mobile_app/tests/quizLatch428.test.ts |
| 10 | Server quiz enforcement | /v2/media/playback and /v2/curated/media had no latch check | Reel-scoped 428 guard added. Residual: /v1/media?ref= not latched (would blank Reel thumbnails) | FIXED (2 bypass routes) | tests/test_quiz_latch_enforcement.py (mutation-checked) |
| 11 | Demo Boost/polling | Fixed-interval polling for all roles; unbounded email poll | Adaptive Demo Boost intervals; email poll bounded. Other pollers verified bounded | FIXED | tsc + mobile tests |
| 12 | Logout / 401 storm | invalidateQueries refetched with discarded creds; 401 handler not token-aware | Cancel-then-clear, clear before server logout, token-aware 401 | FIXED | mobile_app/tests/controller.test.ts, cancellation.test.ts |
| 13 | Heartbeat/session races | — | useScreenTimeHeartbeat verified: 60s, foreground-only, stable callback, torn down on logout | ALREADY FIXED / VERIFIED | code inspection |
| 14 | Profile query / follower_id | Reversed or stale social-graph queries | Source now uses `child_id`=requester and `following_child_id`=target; own/other profile, counts, pending/approved, and batched media auth are consistent. Friendship `followers`/`following` counts are the same by design (ACTIVE pairs). Residual: discover/suggested still does per-row follow lookups (listing size 15; not redesigned) | ALREADY FIXED / VERIFIED | tests/test_follow_back_fix.py, tests/test_two_parent_friendship.py, tests/test_discovery_privacy.py |
| 15 | Story hook crash | Conditional hooks before empty/error return | `StoriesScreen` keeps gesture/auth/focus hooks above early returns; empty/next/exit/broken-media/tab/foreground paths remain | ALREADY FIXED / VERIFIED | mobile_app/tests/stabilization.test.ts, waveB_contracts.test.ts, parityWave2Contracts.test.ts |
| 16 | Post/Reel rendering from R2 | — | NOT AUDITED | NOT AUDITED | — |
| 17 | Neon/PostgreSQL | — | Migrations verified on PG16+pgvector (42 applied). Pooling/SSL review and DATABASE_READINESS.md NOT done. Live Neon: EXTERNAL VERIFICATION REQUIRED | EXTERNAL VERIFICATION REQUIRED | migrations run locally |
| 18 | Resend/OTP | Remaining signup / parent-email / reset / approval gaps after the OTP hardening block | Generation, hashing, expiry, attempts, replay, resend cooldown, attempt-carry, email lowercase, approval-token single-use/expiry/guardian bind are covered. Residual: forgot-password still returns `user_id`+`masked_email` for real accounts (mobile reset still needs that). Live reset/login-throttle DB tests not run here | ALREADY FIXED / VERIFIED (residual deferred) | tests/test_otp_hardening_mock.py, tests/test_login_throttle_mock.py |
| 19 | Child–parent linking | — | Parent review/follow routes authorise via server-side owns()/approved parent_child_map (seen). Not exhaustively audited | NOT AUDITED (partial) | — |
| 20 | Parent routes 404s | — | NOT AUDITED | NOT AUDITED | — |
| 21 | Mobile API base URL | Production could accept extra private ranges; `set_backend_url.py` wrote a dead android/ WebView path | Guard now also rejects 169.254/16, 100.64/10, IPv6 ULA/link-local. Helper writes `mobile_app/.env` `EXPO_PUBLIC_API_BASE_URL` only. No hardcoded Modal URL in mobile source | FIXED | mobile_app/tests/contracts.test.ts, tests/test_set_backend_url.py |
| 22 | Android ID/version | — | Current source: name LittleNet, package `com.littlenet.app`, version `1.0.2`, versionCode `3`, EAS preview = internal APK, `usesCleartextTraffic=false`. npm `package.json` version remains `1.0.0` (not the Android version) | ALREADY FIXED / VERIFIED | app.json, eas.json |
| 23 | EAS/APK readiness | expo-constants duplicate | Deduped; export OK; preview profile = APK. No cloud build run | FIXED | Doctor 19/21 (2 network-only) |
| 24 | Modal cost/GPU | — | NOT AUDITED (only Demo Boost status cost examined: one row read, Modal touched once on expiry) | NOT AUDITED | — |
| 25 | Model loading | — | Three trained weights are LFS pointers here; loader NOT reviewed | EXTERNAL VERIFICATION REQUIRED | ARTIFACT_MANIFEST.sha256 |
| 26 | Moderation pipeline doc | — | MODERATION_PIPELINE.md NOT produced | NOT AUDITED | — |
| 27 | Security | — | Pattern scan of tracked files: no real credentials found (localhost/CI/placeholder URLs only). Not a full audit (no IDOR/upload/CORS review) | NOT AUDITED (partial scan) | scan done in-session |
| 28 | .env.example | Missing a few deploy names / required-vs-optional notes | Root template now lists required production names and adds `STRICT_PRODUCTION_PREFLIGHT`, `LITTLENET_WEB_MODAL_APP`, `LITTLENET_R2_WRITE_PREFIX`. Expo template remains the single public var | VERIFIED | .env.example, mobile_app/.env.example |
| 29 | Error handling paths | — | NOT AUDITED | NOT AUDITED | — |
| 30 | Performance | — | NOT AUDITED beyond polling | NOT AUDITED | — |
| 31 | Tests | — | Backend 783/2 skipped/0 failed; mobile 281/0 | FIXED | TEST_RESULTS.md |
| 32 | No fake results | — | Process rule followed; unexecuted items listed | NOT APPLICABLE | — |
| 33 | README | — | NOT updated | NOT AUDITED | — |
| 34 | Deployment config audit | — | NOT AUDITED | NOT AUDITED | — |
| 35 | Health endpoint | Secret / DSN / path / traceback leak | After later commits, `/healthz`, `/readyz`, `/api/mobile/v1/health` still return only status/mode booleans or static identity | ALREADY FIXED / VERIFIED | tests/test_health_no_leak.py |
| 36 | Curated media doc | — | NOT produced | NOT AUDITED | — |
| 37 | Release noise | — | ZIP built from tracked files only | FIXED | zip listing |
| 38 | Artifact manifest | — | Manifest of model files created | FIXED | ARTIFACT_MANIFEST.sha256 |
