# LittleNet stabilization pre-deployment change report — 2026-09-30

Status: BLOCKED pending complete release gates and authenticated live/physical-device verification. This report records evidence, not a readiness claim.

Starting state: clean `main`, HEAD and `origin/main` both `3618d562d219c5f9186ce011ae0be8d55e1eb0be`. Work is on `codex/final-device-stabilization`. Flask, PostgreSQL, private R2, and the single Expo client are retained. No schema migration is needed or applied to production.

## Findings and regression coverage

| Area | Root cause | Fix | Regression test | Live result |
|---|---|---|---|---|
| Learn | Optional practice treated `required=false` as completion after one answer; refill depended on paid generation | Advance every practice answer, refill unseen batches locally, explicit Finish/Back | `stabilization.test.ts`; `test_final_device_stabilization.py` | >5-question device flow pending |
| Reel resume | Navigation reset unmounted Reels; inserting/removing a quiz row shifted indexes | Pop quiz after authoritative latch refresh; stable Reel list; resume playback | `stabilization.test.ts`; `quizBreaksRandom.test.ts`; release contracts | Device position preservation pending |
| Feed | Historical dismissals can exhaust eligible inventory | Truthful exhaustion copy; preserve NOT_INTERESTED exclusions and refresh | Existing feed/recommendation suites | Account inventory/pagination pending |
| Search | Explicit search reused restrictive school/class suggestions | Exact username/name lookup permits eligible active minors with guardians and Discover controls; suggestions keep cohort rules | Final stabilization tests; discovery/privacy suites | Two-account exact search pending |
| Friend request | No confirmed shared state-machine defect | Preserve REQUESTED → SENDER_PARENT_APPROVED / RECEIVER_PARENT_PENDING → ACTIVE; cancel/reject paths retained | Existing dual-parent and lifecycle suites | Normal request/idempotency/decline pending |
| Parent approvals | Existing database trigger and API enforce both required approvals | No bypass or synthetic live relationship inserted | Dual-parent and disposable PostgreSQL suites | Parent A + Parent B flow pending |
| DM/chat | Depends on ACTIVE relationship and parent feature policy | Existing shared authorization preserved; test stub isolation corrected | Chat/review visibility; dual-parent suites | Bidirectional text, typing, unread/read and revocation pending |
| Moderation speed | Historical job ages cannot measure a fresh upload; INFO timing logs were not enabled in workers | Enable existing worker timing logs; keep CPU async processing and AI scale-to-zero | Existing pipeline/state-machine tests | Fresh T0–T6 trace and seconds-to-tens-of-seconds target pending |
| Partial AI | Healthy OCR text was appended to `errors`, making the result partial | Separate successful OCR evidence from actual stage errors; real failures still REVIEW | OCR tests; final stabilization tests | Recent live partial events identify `ocr_text_present`; deployed safe-image outcome pending |
| Parent email login | Parent redirect lost mode/destination; CSRF refresh lost both | Preserve parent mode and safe `/parent/` destination through login/CSRF refresh; private no-store pages | Redirect/CSRF tests including unsafe next values | Embedded-email browser login pending |
| Review preview | REVIEW source stays quarantined; template expected published media path | Owned OPEN REVIEW preview endpoint signs private R2 GET for 60 seconds; raw keys removed from HTML | Owned/foreign preview and focused-event tests | Authorized IMAGE/VIDEO preview pending |
| Approve/Block | No confirmed terminal-state defect | Existing promotion/cleanup and BLOCK terminal guards retained | BLOCK/state-machine and review lifecycle suites | Legitimate review approve + block pending |
| Profile media | Legacy missing paths, unlabeled placeholders; video URL incorrectly used as image fallback | Explicit review/text/unavailable tiles; video thumbnail requires poster; published count retained | Existing media contracts and mobile suite | Real image loading and refreshed parent decision pending |
| Public feed | Missing legacy media cannot be repaired by client placeholders; Post Detail GET was absent | Add gated shared-visibility Post Detail GET; strip quarantine paths; truthful video unavailable state | Final stabilization tests; shared visibility suites | Live Post Detail and signed media rendering pending |
| Reels inventory | Published curated inventory exists; eligibility is account-specific | Preserve age/category/parent/block/mute policy and cursor feed | Existing feed/curated/Reel suites | Read-only count: 156 published curated Reels; eligible account feed pending |
| Profile UX | Five actions crowded one row; custom grid glyph | Two action rows and consistent vector icons | Mobile suite/typecheck/export | Physical sizing/accessibility pending |
| Create UX | Four source choices plus always-visible optional metadata | Gallery/Camera with native photo/video choices; collapsible tags/location; required category remains visible | `stabilization.test.ts`; draft/upload suites | Native gallery/camera permissions and all four capabilities pending |
| Stories | No confirmed contract defect | Existing private media, expiry, feature controls and safe music preserved | Existing story/media suites | Live story upload/playback/expiry pending |
| Notifications | No confirmed contract defect | Existing child/parent ownership and review/approval notification paths retained | Notification/relationship/review suites | Normal email/in-app delivery pending |
| R2/media delivery | Raw source path leaked in generic post serialization; terminal observations did not invalidate all social caches | Strip source path; terminal cache invalidation and foreground reconciliation/refetch; deployment excludes local env/venv/log files | Final stabilization and processing tests; existing media authorization suites | Private bucket and fresh signed URL playback pending |

## Change report

| Files | Reason / issue solved | Check |
|---|---|---|
| `quiz/service.py`, `mobile_app/src/quiz/decision.ts`, `mobile_app/src/screens/Quiz.tsx` | Unseen local practice refill, complete only the appropriate mode, preserve mounted Reels | Quiz behavior and local fallback regressions |
| `mobile_app/src/screens/kids/ReelsScreen.tsx` | Remove index-shifting prompt rows; unpause when server latch clears | Stable-list and latch regressions |
| `child/service.py`, `child/routes.py`, `mobile_app/src/screens/kids/DiscoverScreen.tsx` | Separate exact eligible lookup from suggestions; whitelist public profile fields; explain exact lookup in search copy | Discovery privacy and exact-search regressions |
| `app.py`, `decorators.py`, `auth/routes.py`, `auth/templates/login.html` | Parent deep link survives authentication and CSRF recovery; reject unsafe redirect | Parent redirect/CSRF regressions |
| `parent/routes.py`, `parent/templates/safety_review.html`, `tools/audit_routes.py` | Authorized focused event and private preview; classify exact readonly preview route correctly | Preview ownership/TTL tests and route audit |
| `mobile/api.py`, `mobile_app/src/api/kidsSocial.ts` | Missing Post Detail GET; shared visibility; remove quarantine key serialization | Gated detail endpoint tests |
| `safety/visual_service.py`, `tests/test_image_ocr_safety.py` | Healthy OCR evidence must not mark a result incomplete | Healthy OCR ALLOW and failed OCR REVIEW checks |
| `mobile_app/src/kids/useProcessing.ts`, `mobile_app/src/query/client.tsx` | Reconcile foreground and refresh social caches after terminal status | Processing regression and mobile suite |
| `mobile_app/src/navigation/RootNavigator.tsx` | Parent Pause applies even to demo-unlimited users | Existing demo/parent-pause contracts |
| `mobile_app/src/screens/kids/OwnProfileScreen.tsx`, `mobile_app/src/screens/kids/OtherProfileScreen.tsx`, `mobile_app/src/kids/PostCard.tsx`, `mobile_app/src/screens/kids/FeedScreen.tsx` | Clear hierarchy, honest pending/missing-media and exhaustion states, correct video preview type, image errors display an unavailable tile and a new signed URL retries | Mobile suite/typecheck/export |
| `mobile_app/src/screens/kids/CreateScreen.tsx`, `mobile_app/src/kids/postMedia.ts` | Two source actions, all photo/video capabilities, optional metadata disclosure | Picker/create regression and draft/upload suites |
| `modal_web.py`, `modal_ai.py` | Exclude local env/venv/logs from deployment; enable existing worker timings without warming GPU | Deployment source contracts |
| `requirements-core.txt` | PyJWT 2.13.0 has nine audited vulnerabilities, patched in 2.14.0 | Core dependency audit and backend auth suite |
| `tests/conftest.py`, `tests/test_agent_a_disposable_postgres.py`, `tests/test_real_app_acceptance_e2e.py`, `tests/test_message_review_visibility.py`, `tests/test_chat_realtime.py`, `tests/test_video_push_feed_modes.py` | Explicit disposable DB isolation; no production email/media/AI calls; correct fixture encoding, module restoration, CSRF setup, sender identity, bounded reaper isolation and unit-only feed mode refill stub | Full backend suite; focused fixture run: 16 passed |
| `tests/test_final_device_stabilization.py`, `mobile_app/tests/stabilization.test.ts`, `tests/test_release_experience_contracts.py`, `mobile_app/tests/quizBreaksRandom.test.ts` | New root-cause regressions and update old prompt-row assumptions | Focused and complete suites |

## Production data and test incident

Initial production inspection was read-only. A subsequent early integration test launch inherited `.env`'s production database via the old test harness. It was stopped. Before/after counts rose from 130 users / 520 posts to 142 users / 533 posts: the observed delta is 12 users and 13 posts, consistent with that harness's random `user_<hex>` fixtures. This was unintended. The new root conftest isolates subsequent runs to an explicit disposable database and blanks external email/media/AI credentials. No cleanup or production deletion was attempted. Historical fixture rows predate this run, so deleting all matching names would be unsafe.

Read-only follow-up: no orphan posts; no duplicate directional friendship rows; 22 open events, 20 older than a week. ALLOWED IMAGE rows include 71 missing published paths. Historical status inconsistencies and stale jobs require owner-reviewed data remediation; they are not silently promoted, retried, or deleted. Normal upload latency cannot be inferred from these historical durations. R2 existence checks and authenticated publication evidence remain pending.

Two temporary Neon test branches were created because the first retained test snapshot lacked current columns; the second clones the actual live branch. Both computes were suspended after checks; branches remain for diagnosis without deleting data. Production schema is unchanged; no bootstrap or migration ran against it.

## Release gates and artifacts

Final Git commit: pending.

- Backend: full local diagnostic run 763 passed / 1 failed / 1 skipped in 19m33s. The failure was duplicate Post Detail route registration from this change; it was fixed by adding GET to the existing DELETE route. Fresh focused route/OCR checks: 34 passed. Final complete green run/CI pending. Earlier focused root-cause/safety run: 51 passed; corrected fixture run: 16 passed.
- Mobile: 260 passed, 0 failed. Typecheck PASS. Android export PASS. Expo install compatibility PASS. npm ci completed with zero reported vulnerabilities.
- Source scope/readiness/routes/dynamic SQL: PASS.
- Security: core, text, safety and AI dependency scans PASS. Standard CI Bandit scope PASS. Broader scan additionally reports the intentional all-interface development bind and two fixed-HTTPS Resend URL open sites; these are not user-supplied URL sinks.
- Neon: production UNCHANGED; read-only consistency findings above.
- Modal AI/Web: new deployment pending; baseline health endpoints respond 200.
- R2: read-only sample of five latest ALLOWED references: two release-namespace objects present with signed GET 206; three references belonging to `user_<hex>` integration-fixture accounts are missing with signed GET 404. All five unsigned requests fail with HTTP 400. This sample does not establish missing real-user media. Fresh authenticated upload/private-review/publication verification pending. No object was modified.
- Resend: baseline readiness configured; real review-email delivery pending.
- EAS build: NOT RUN. Build ID / artifact / final commit / remote versionCode: unavailable until live gate passes.
- Configured app identity: `com.littlenet.app`; local version 1.0.2 / Android versionCode 3; EAS uses remote app versions.
- Required API URL: `https://netlittle2--littlemuse-web-web.modal.run`.
- Real device: NOT YET VERIFIED; adb detects no attached device.

APK creation is intentionally gated on the requested authenticated live backend flows. Neither generated test tokens nor direct fixture manipulation would establish login or normal dual-parent approval success.

## Physical Android checklist

Record account role, time, screenshot/video evidence and observed result for each item; never record passwords/tokens.

1. Login and OTP; mode switching and logout.
2. Home Feed loads, refreshes and paginates; distinguish loading, error and exhaustion.
3. Stories load/play, expire, and respect parent controls.
4. Exact people search with Discover enabled; suspended/blocked accounts stay hidden.
5. Send one friend request; duplicate requests remain idempotent.
6. Parent A approves; DM still unavailable.
7. Parent B approves; relationship becomes ACTIVE; reject/cancel also work.
8. A→B and B→A chat; conversation order, unread count, read state.
9. Typing indicator appears and expires; block/unfriend/disabled messaging immediately revoke DM.
10. Create safe photo from gallery and camera; immediate private acknowledgement.
11. Record T0 acceptance, T1 worker start, T2 fetch, T3 initialization, T4 moderation, T5 terminal DB, T6 device observation; normal completion in seconds to tens of seconds.
12. Real profile image renders; review items are explicitly private and excluded from published count.
13. Real Feed and Post Detail media render; like/save/comment work.
14. Generate a legitimate REVIEW through moderation; review email arrives.
15. Email opens Parent login, returns to exact owned event, private preview loads; foreign parent receives generic 404.
16. Approve promotes sanitized media, resolves event, publishes and refreshes owner/Feed.
17. Block never publishes; already BLOCKED content cannot be resurrected.
18. Eligible Reels load and play; reject videos longer than 45 seconds.
19. Meaningful Reels trigger server-random Brain Break between 2 and 5.
20. Wrong answer keeps Reel latch; other application features remain available.
21. Correct retry clears server latch and resumes playback.
22. Resume preserves previous Reel context, including Back/navigation.
23. Learn answers questions 1–5 then another unseen batch; Finish/Back/retry work without paid AI.
24. Like/save/comment updates other views and respects feature/category policy.
25. Child/parent notifications show only authorized events.
26. All important routes/back paths, loading/error/empty states, and native picker permissions.
27. Parent screen-time/quiet-hours/category controls take effect on the next request.
28. Parent Pause blocks ordinary and demo-unlimited child activity.
29. Leave Processing, background and foreground; late terminal result reconciles without endless polling; signed media refreshes.
30. Complete repeated navigation/upload/Reel/chat session without crashes or repeated 500s.

Final status: BLOCKED until authenticated live flows, measured moderation latency, final release gates, deployment, one APK and physical Android verification are complete.
