# Files Changed (vs upstream 7e15e2d)

| Path | Reason / behaviour changed |
|---|---|
| auth/service.py | Approval-token expiry now compared in SQL on the DB clock (was relabelled as UTC; tokens lived ~5.5h too long under IST). |
| mobile/api.py | upload_sessions.expires_at written as aware UTC; completion expiry decided in SQL; dropped invalid trailing 'Z'; added _target_is_reel/_reel_quiz_latch_block and applied to /v2/media/playback and /v2/curated/media (428 quiz_required for Reels while latch active). |
| services/media_processor.py | Retry-backoff age computed by Postgres (was relabelled as UTC; backoff stretched to ~5.5h). |
| tests/test_upload_session_timezone.py | NEW: 7 regression tests for the three clock fixes. |
| tests/test_quiz_latch_enforcement.py | Structural count 5→6; 6 new behavioural tests for the generic playback routes. |
| tests/test_agent_a_disposable_postgres.py | Fixture connection now sets the production session timezone. |
| tests/test_phase25_production_hardening.py | Fixture writes aware-UTC expiry. |
| mobile_app/src/video/quizGate.ts | NEW: isQuizRequiredError helper (428 / quiz_required). |
| mobile_app/src/video/useReelPlayback.ts | On playback 428: stop fetching, call onQuizRequired, no generic error; one fresh attempt when the cell re-activates; manual retry handled. |
| mobile_app/src/video/ReelPlayer.tsx | Threads onQuizRequired prop. |
| mobile_app/src/screens/kids/ReelsScreen.tsx | handleQuizRequired: latch locally + refreshMe, which opens the Quiz screen. |
| mobile_app/src/query/client.tsx | invalidateSessionQueries: cancel then clear (was invalidate→refetch of active queries with discarded credentials). |
| mobile_app/src/auth/controller.ts | Sign-out clears user-scoped queries before the single server logout call. |
| mobile_app/src/auth/session.ts | NEW shouldInvalidateOnUnauthorized (ignore stale/duplicate/unauthenticated 401s). |
| mobile_app/src/auth/AuthProvider.tsx | 401 handler is token-aware via shouldInvalidateOnUnauthorized. |
| mobile_app/src/api/client.ts | Unauthorized handler receives the rejected request's token. |
| mobile_app/src/screens/ParentOnboarding.tsx | Email-delivery poll: stops on terminal status, capped at 20 polls, skips while backgrounded. |
| mobile_app/src/api/demoBoost.ts, components/DemoBoostNotice.tsx, screens/admin/AdminScreens.tsx | Adaptive Demo Boost polling (fast only while a boost is active). |
| mobile_app/package.json, package-lock.json | `overrides.expo-constants = 57.0.20` to remove the duplicate native module. |
| mobile_app/tsconfig.tests.json | Includes quizGate.ts for the test build. |
| mobile_app/tests/quizLatch428.test.ts | NEW: 8 tests (no retry on 428, one request per 428, latch off, resume, no logout trigger). |
| mobile_app/tests/controller.test.ts, cancellation.test.ts | New logout-ordering and token-aware-401 tests. |
| RELEASE_IDENTITY.md, release_docs/*, ARTIFACT_MANIFEST.sha256 | NEW documentation/manifest (this package). |
