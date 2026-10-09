# LittleNet → LittleMuse day-one-to-deploy retrospective

**Audit date:** 2026-10-08. **Canonical release source:** `littlenet655-sketch/littlemuse`, not the retired LittleNet-1 or superseded feature branches. **Status:** repository-source candidate; latest code still needs a controlled Modal release and physical end-to-end testing.

## Counting method and verified scale
- Historical `littlenet655-sketch/LittleNet-1`: 56 PRs, 53 merged, 3 closed unmerged.
- `littlenet655-sketch/littlemuse`: 41 PRs through #41, 33 merged, 8 closed unmerged, before the present audit PR.
- **Combined: 97 historical PRs, 86 merged, 11 closed unmerged**. These are *PRs, not 97 independent issues/fixes*. One PR often fixes many bugs; two PRs can represent successive corrections of the same bug; some merges are architecture work.
- The September 24 explicit scope was **16 named product tasks + one shared feed/refill prerequisite**, not a count of defects. The later locked demo/product decisions supersede older design options.
- There is **no trustworthy unique all-time issue count** across chats/PRs because informal bugs, changed scope and reworked patches were never kept in a single normalized issue tracker. Never claim all historical errors are fixed merely by counting merged PRs.

## Effective fixes by subsystem (count each cause once; latest implementation wins)

| Subsystem | Root incidents / iterative corrections | Effective current implementation / evidence |
|---|---|---|
| Architecture/build | Cloud Run/Flutter/WebView phases abandoned; Expo migrations, native Kotlin parent gate, APK identity/build fixes | React Native + Expo/TypeScript under `mobile_app/`; Python Flask API; Modal/Neon/R2/Resend. No WebView or Flutter release root. Original PRs #31–41; LittleMuse #5–9, #29. |
| Identity/auth | Parent OTP, adult checks, wrong mode, stale session/401/logout, enumeration/reset OTP, outbox expiry, device auth crashes | Parent email OTP + DOB/adult declaration + Android device lock; child password + onboarding quiz; password reset hardened, outbox sweeps in LittleMuse #26, #29–30. Child/guardian face and Whisper *retired intentionally*. |
| Relationships/DMs | One-parent follow mistakenly activated friendships; reverse/approval actions, follower_id SQL 500, repeated Follow cancelling request, stale authorized chat, chat media presign leaks | Two-family staged `followers` trigger and ACTIVE-only `can_interact`; parent queue OUTGOING/INCOMING/WAITING; bearer chat/send/typing; review messages withheld until parent decision, video/photo messages in LittleMuse #15, #21, #38. |
| Child-safety image and OCR | Failing classifiers, YOLO mapping, false-positive visual CLIP merge, malformed evidence, lost text/PII provenance, optional engine absent | `safety.visual_service.check_image`, RapidOCR default-on (image) pinned in core/Modal AI, trained image models + YOLO/NudeNet/FalconsAI/CLIP, canonical `services.media_processor._merge_signals` and `policy.decide`. PR #25/#26, present audit closes stale browser _merge bypass. Per-frame video OCR stays opt-in. |
| Video/Reels | First-frame-only design, missing coverage, blocked videos with audio, poster missing, first-frame/rebuffer UX stalls | Adaptive bounded 3–8-frame video moderation, fail-closed insufficient coverage, video audio stripping, private MP4/posters, native Reel player timing and fallback in #24/#29; real-world TTFF and audio still require device measurement. |
| Upload/R2/worker | Signed URL, R2 key mismatch and CSP, status terminal UI, atomic tags/commit, queue dispatch crash window, stale worker lease, HEAD 403 misread as 404, abandoned sessions, error retries | Quarantine→moderation→publish worker, atomic completion, durable lease/recovery cron, bounded pool, error semantics in #26/#28; chat presign fix #31; #41 refreshes expired R2 PUT session & terminalizes source-less orphan jobs. Historical FAILED media cannot be reconstructed without bytes. |
| Feed/visibility/recommendations | Global vs friends-only visibility confusion, old SQL parameter mismatch, 6–9 item session stop, stale cached sessions, misleading approved REVIEW content | Global public-safe For You with age/category/block/mute; Friends gated on ACTIVE, session refill, conservative publication filters in #11/#26/#38/#41. Present audit extends processing-state guard to legacy social/story/profile paths. |
| Parent review | Parent notification and content approval, unblurred poster paths, Review no media preview, terminal BLOCK resurrection, hidden REVIEW DM | OWNED-child-only `/parent/safety` and mobile `/parent/safety`, safe quarantine previews + explicit reveal, approved media sanitization/publication, BLOCK remains final. #20/#37; present audit conceals poster-only fallback and alerts verified secondary guardian. |
| Parent upload supervision | Browser `/parent/child-posts/` existed, native parent detail lacked direct upload record, while activity/insights existed | Present audit adds owner-checked, paginated native API and Child Summary upload panel. History displays only fully published thumbnails; pending reviews link to existing Parent Safety. |
| Quiz and screen time | Client fixed markers, quota lock stuck, wrong answer incorrectly cleared latch, rate-limited external questions, offline screen-time bypass, misleading pacing UI | Mandatory random 2–5 Reel impressions and server-side 428 latch until **correct answer**, practice independent; local quiz fallback, parent control/quiet-hours server + offline guard, one heartbeat (#8/#19/#20/#24/#26/#35). |
| Notifications/Resend | OTP delivery and webhook, expired reset emails, incomplete parent review fanout, push provider/device unknown | Resend domain/preflight previously passed, reset outbox expiration #30; present audit notifies *both* verified guardian IDs. Physical Expo push receipt requires separate live test. |
| Creator chat/editorial content | Curated personas incorrectly child IDs, editorial likes forced to social IDs, initial stale creator chat proposal | Relational curated creators, source-aware engagement (#11–15), child-safe K2 niche creator chat accepted via clean PR #40; distinct from private child-child messaging. |
| UI/crash navigation | Story viewer React hook-order crash, Reel remount/quiz reset, Profile timeout, Discover search layout, safety status wrong, review image too visible | #20–24, #34–37; prior native Android check fixed actual Story crash; current CI screens/typecheck green, device screenshots still required. |
| Infrastructure/releases | Modal preflight temp-file collision, model staging, stale migrations, R2/Resend shared secret check, false Vercel status | #28–33 fixed source/workflow checks; Oct 6 Modal deploy validated model load and preflight; Oct 8 code has NOT been deployed. Repo checked in 45 dbmate versions, production recorded 45/45; use restore point for release. |

## Explicitly superseded branches/decisions
- **LittleNet-1 legacy Cloud Run/Flutter/WebView** → native Expo React Native canonical source; do not revive abandoned roots.
- **Face/liveness and Whisper/audio gates** → replaced with parent email OTP + DOB declaration + OS device authentication, child password; no face uploads or standalone audio required.
- **Old optional/off-by-default image OCR documentation** → source defaults ON; RapidOCR installed in core and Modal AI CPU image. Video-frame OCR intentionally off unless enabled; do not describe all video frames as OCR-checked.
- **Brain Break early wrong-answer unlock / varied 4–7 and 7–10 parent UI** → final compulsory correct-answer-only random 2–5 server latch (#19/#35); ignore earlier design.
- **Original LittleMuse PRs #1–4, #16, #17, #27 and #39** → closed unmerged, superseded by current main direct changes or merged #26/#28/#29/#40. Do not merge those branches.
- **CLIP false 18+ block first workaround** → final policy-preserving signal provenance in PR #25/#26; present audit closes legacy browser merger that still dropped deterministic OCR flags.
- **Moderation status ALLOWED vs processing status REVIEW** → newer feed filter from #41 applied now to all legacy public queries. Await the current audit PR merge/deploy before claiming it live.

## Neon read-only audit on 2026-10-08
- `neondb`, **45 migrations applied** (historically pre-#40 was 44); live release Oct 6 reported zero pending/unknown.
- `posts`: 363 fully safe/published; 39 historical stale UPLOADED with no recoverable media reference; 77 FAILED exhausted at 3 attempts; 3 REVIEW processing / ALLOWED moderation / safe flag anomalies; 4 OPEN REVIEW image events. No production rows modified during this audit.
- `followers`: 156 directed ACTIVE approved links, 1 pending REQUESTED, 0 currently in intermediate approval stages; `child_messages` 43 ALLOWED and 11 conversations; these counts demonstrate persistence, not live two-device UI quality.
- `parent_child_map` 38 approved links; currently zero separate `verified_parent_id <> parent_id`, so secondary-guardian notification fix remains regression-tested, not independently live-proven.
- Do not delete or republish failed/stale records automatically. The scheduled recovery fix can terminalize source-less old UPLOADED records on the NEXT deployed worker; changing old state to FAILED does not recover missing media.

## Current audit source changes (branch, pending CI/merge at document drafting)
1. Legacy browser `uploadPost/routes.py::_merge` delegates to canonical text+media signal merger, retaining OCR/contact/grooming flags; inserted ALLOW/REVIEW rows now have coherent `processing_status`.
2. `services/social.py` legacy Feed/Stories/Discover/profile and sharing require **both** final moderation and processing ALLOWED; owner-private REVIEW remains private.
3. `services/social.py::parent_notify` alerts primary *and* separately verified guardian.
4. `parent/routes.py::review` rechecks ACTIVE friendship before revealing pending chat approval.
5. Native Parent review video-poster-only fallback requires explicit Reveal; no unblurred quarantine preview.
6. Mobile Parent Child Summary adds a paginated, guardian-authenticated child upload-history view; only safe final published images get preview URL and REVIEW navigates to Parent Safety.
7. Added backend and mobile regressions and corrected stale OCR deployment documentation.

## Release gates (still not completed)
1. All latest-head GitHub CI jobs green, fix any regressions, merge reviewed PR without a live-release marker.
2. Create Neon restore point and run read-only migration check; use reviewed current migrations only, no manual schema_migrations tampering.
3. Deploy exact merged SHA to Modal AI/Web (no live deploy in this audit); verify OCR package, model CPU worker, R2 presign/download, mail & readiness.
4. Build a NEW APK/EAS release from that same SHA. The Oct 6 APK predates Oct 8 fixes.
5. Physical device: OTP/login, child A post→AI safe allow→child B's public feed, explicit BLOCK & review queue, two parents approve friend request then DM; revoke friendship and ensure chat blocked; chat images/reactions/typing, random Reel quiz wrong/correct, parent upload-history thumbnails and blurred review, safe OCR contact test, push delivery, video render, screen-time/quiet-hour gates.
6. Optional streaming benchmark/load and held-out classifier/OCR evaluation before any speed/accuracy claims.
7. Only after the checks may project be labeled **fully deployed and end-to-end verified**. Source CI passing alone is **not** that claim.

## October 9 follow-up audit: parent-lock and publication authorization

**Trigger:** A fresh source read of current `main` exposed authorization drift that earlier passing suites missed. This section records corrective work proposed by PR #43. The PR must pass current-head CI and merge before the fixes are considered part of `main`.

- **Child lock / R2 auth:** The direct `/api/mobile/v1/media` proxy and shared R2 media signer did not consistently re-evaluate parent pause, quiet hours and screen time for curated, avatars, or chat attachments. Canonical `services.social.child_surface_open` now includes the user's `parent_paused` database flag; `mobile.api._media_allowed` and `_media_allowed_many` fail closed before granting any CHILD media reference; the media proxy itself calls the child gate. Previously minted signed R2 URLs are not revocable immediately and naturally live until their short TTL.
- **Legacy web child entry points:** `decorators.role_required('CHILD')` checked account activation but not time/quiet/pause or the chat messaging toggle, allowing a child to bypass rules via old browser routes while the mobile app was locked. Now it applies canonical child-surface checks to normal browser routes. The technical heartbeat, remaining-time info and locked/quiet-hours information pages remain accessible.
- **Batched authorization parity:** The optimized `_media_allowed_many` child visibility SQL omitted final `p.processing_status='ALLOWED'`. It now requires both moderation and final publication state; this matches `post_visible_to`.
- **Profile counts:** `child.service.counts` counted moderation-ALLOWED but processing-REVIEW posts. A read-only production query found two affected non-story posts. Counts now require final processing ALLOWED; the underlying rows remain untouched.
- **Tests:** `tests/test_repeat_audit_media_gates.py` exercises paused parent, direct/batch media denial, locked legacy web read/write, preserved heartbeat/lock display, final processing-state checks and corrected counts. This is source/runtime test verification only, not a phone or live deployment test.

**Release status:** No Modal deployment, APK build, production SQL update or media deletion was performed as part of this follow-up audit. Do not label the fix production-live until that exact merged SHA has been deployed and exercised through real child and parent accounts.
