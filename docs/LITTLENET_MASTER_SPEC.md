# LittleNet Master Product Specification

Established 2026-09-15 from the user's final-orchestrator work order.
Baseline: PR #43, `feature/submission-readiness-fixes`, `f48aafa1bce0fb1344dfc8aec57f70770d8dfc0b`.

## Authority and evidence

This document defines required behavior, not a claim of completed implementation.
The explicit user requirements below govern product scope. Source and executed evidence determine implementation status; historical documents cannot establish current runtime success.
`ASTRA_RELEASE_LEDGER.md` is the only progress tracker. `LITTLENET_PIPELINE_MAP.md` maps implementation boundaries. Existing matrices remain reference evidence, not competing trackers.

Do not merge PR #43 without final approval. Production is read-only during testing; preserve the existing Flask backend, one Expo root, private R2, and server safety authority. No secrets in Expo beyond the public API base URL. No replacement Modal apps or public media bucket.

Evidence levels: IMPLEMENTED (source traced), AUTOMATED_TESTED (named command/result), LIVE_SERVICE_VERIFIED (dated environment-specific evidence), DEVICE_VERIFIED (actual APK/device journey), BLOCKED (named unmet prerequisite), MISSING (confirmed absent implementation). These levels are independent; automated success cannot imply device success.

## Reconciliation of historical evidence

The 2026-09-14 documents report no current-head APK and no device journeys. The user subsequently reports build `970b8614-50b6-4e7c-abe0-f40958926efb` from the baseline, installed on Android, reaching Adult Check with camera permission, preview and oval working. Capture fails with `undefined is not a function`. This supersedes the blanket no-APK claim, but does not prove the failing function or successful guardian verification.
Historical CI, Resend, R2, Modal and production content counts remain attributed historical observations until independently verified. No additional P0 is asserted from those counts alone. UI parity percentages are estimates. Group chat, advanced editing and accuracy claims cannot be inferred from mockups.

## A. PRODUCT IDENTITY

LittleNet is a child-safe social application inspired by the usability and
polish of Instagram, with:

KIDS MODE
PARENT MODE
ADMIN / MODERATOR MODE

It is a college project but the working demo should behave like a real product.

Primary Android app:
React Native + Expo

Backend:
Flask

Database:
PostgreSQL / Neon

AI:
Modal

Media:
private Cloudflare R2

Email:
Resend

## B. PARENT ENTRY PIPELINE

Expected:

Welcome
→ Parent sign-up
→ username/full name/email/password/DOB
→ adult guardian declaration
→ Resend OTP
→ 6-digit OTP verification
→ ACTIVE Parent
→ Android device auth (biometric/PIN) gates Parent Mode
→ Parent dashboard

OTP:
- real Resend sender
- verified littlenet.in domain
- fail closed
- resend supported
- expiration supported
- never fake delivery success

Parent identity/authentication:
- email OTP proves inbox ownership
- guardian 18+ declaration and consent are server-authoritative
- Android system authentication (biometric/PIN/device credential) gates Parent Mode
- no parent or child face-recognition/liveness pipeline is part of the locked product scope
- auth failures must be understandable and fail closed

Server remains authoritative.

## C. CURRENT RELEASE GATES

The historical guardian-camera P0 is retired because face/liveness authentication
was removed from the product scope on 2026-09-22.

Current release gates are evidence gates, not known missing features:

- source/security/mobile CI must pass on the exact release commit;
- live Modal web/AI identities and secrets must match the release workflow;
- retained Neon migration history must pass the guarded dbmate reconciliation check;
- a current-HEAD EAS APK must be built against the verified live HTTPS backend;
- one Android device must complete the sequential Parent → Child → Feed/Reels →
  Create → Moderation → Parent/Admin journeys in PHYSICAL_DEVICE_CHECKLIST.md;
- live R2/Resend/Modal and cross-user publication behavior must be exercised before
  claiming end-to-end verification.

## D. CHILD ONBOARDING PIPELINE

Expected:

Parent
→ Create child
→ child profile
→ required age quiz
→ Kids Mode

Later login:

Choose Kids
→ username/account selection where required
→ child password login
→ quiz gate if required
→ Kids Mode

(2026-09-22: face capture / anti-spoof / Facenet512 steps removed by product
decision. Child password login is the only child auth method.)

## E. QUIZ PIPELINE

Quiz is server-authoritative.

Expected:

fetch quiz requirement
→ show questions
→ child answers
→ backend scores/submits
→ refresh authoritative /me/gate
→ if cleared enter destination
→ otherwise remain gated

Must support:
- onboarding quiz
- recurring quiz gate
- persistence after restart
- destination restoration
- quiz bank
- result/progress state

Never allow client-only bypass.

## F. KIDS APP INITIAL HYDRATION

Immediately after gates clear:

KidsTabs
→ bounded parallel prefetch:

Home
Feed page 1
Reels page 1
Stories/home state
Explore
Own profile
Notifications

The child should see a populated product quickly rather than empty tabs.

Use real backend/database content.

No hardcoded final demo arrays.

## G. HOME FEED

Expected tabs:

For You
Friends
Learn where supported

Real database content.

Eligibility filtering BEFORE ranking:

ALLOW
safe
processing complete
age eligible
Parent category allowed
feature allowed
not blocked
not muted
relationship/privacy eligible

Actions:

like/unlike
comments
save/unsave
share/send
profile
report
hide/not interested where supported

Must support:

pagination
dedupe
refresh
loading
empty
error
offline

REVIEW/BLOCKED content must never leak publicly.

## H. RECOMMENDATION ENGINE

Recommendation behavior should use safe eligible candidates only.

Signals include:

INTEREST
REEL_COMPLETION
REEL_REPLAY
LIKE
SAVE
COMMENT
SHARE
FOLLOW
SEARCH_CLICK
NOT_INTERESTED
HIDE
MUTE
BLOCK
REPORT

Negative safety/preference signals should outweigh weak engagement.

Recommendations must NEVER override:

age restrictions
Parent controls
privacy
block/mute
moderation
publication state

## I. REELS

Expected:

vertical full-screen paging
one active Reel at a time
previous Reel pauses
bounded adjacent preload
poster/loading
retry
foreground/background behavior

Actions:

like
comment
share
save
creator profile
Not Interested
report

Real DB media URLs.

Recommendation signals should capture relevant watch/replay behavior where
implemented.

## J. STORIES

Expected core demo:

Story rings
Story viewer
progress
next/back
pause/resume
creator
report
reply only when authorized
safe upload/moderation

Do not pretend advanced editor features exist unless implemented.

Advanced:
stickers
drawing
rich Story editing

may remain documented limitations for submission.

The production audit previously found 0 active renderable Stories.
Audit the current state honestly.

## K. EXPLORE / DISCOVER

Explore should be populated BEFORE search where eligible content exists.

Expected:

visual discovery surface
safe posts
safe Reels
eligible creators
educational content where available

All filters:

age
Parent categories
feature controls
block
mute
privacy/relationship
moderation
processing state

The final UI should use media cards/grid where the API provides media, not
merely caption text rows.

## L. SEARCH

Expected categories:

People
Posts
Reels
Learn where supported

Support:

name/people search
caption search
exact hashtag semantics
case-insensitive behavior
recent searches
safe search warnings

Exact hashtag requirement:

#science matches #science

It must not incorrectly treat:

#sciences

as the same exact hashtag.

Safety/privacy filtering remains mandatory.

## M. CREATE / UPLOAD

Image and video/Reel posting:

media picker/camera
→ upload session
→ private R2 quarantine
→ completion validation
→ async media processing
→ moderation
→ terminal state

ALLOW:
sanitize/promote
→ published
→ visible where eligible

REVIEW:
private
→ author sees under review
→ Parent/Admin authorized review

BLOCK:
never public
→ appropriate cleanup/invalidation

After ALLOW invalidate/refetch:

own profile
Home
Feed
Explore
Search
Reels where applicable

## N. MODERATION / 18+ SAFETY

Existing AI stack may include:

NudeNet
FalconsAI NSFW
CLIP
YOLO
Detoxify
scene-aware video sampling

Never claim unsupported accuracy.

Video moderation uses bounded PySceneDetect + uniformly distributed frame
sampling. Runtime targets at least 3 and at most 8 frames. Under the default
12-second temporal-gap contract, videos up to 84 seconds can satisfy complete
coverage with the 8-frame cap. Longer videos intentionally remain private for
REVIEW unless a future benchmarked release policy raises the frame budget or
changes the coverage contract; they must never be auto-allowed from sparse evidence.

Policy outcomes:

ALLOW
REVIEW
BLOCK

Total AI failure:
fail closed according to established policy.

Partial uncertainty:
REVIEW where appropriate.

Accuracy claims require benchmark evidence.

## O. CHAT

Submission scope:

real 1-to-1 text chat
approved relationship authorization
conversation list
pagination
send
read/unread
shared-post DM
mute
block
report
Parent messaging disable

Do not fabricate:

full group chat
media-message moderation

unless they are actually implemented and proven.

## P. CHILD PROFILE / SOCIAL

Own profile:
published eligible posts/reels
saved content where supported
edit profile

Other profile:
privacy/relationship checks
follow/request state
block/mute/report

Relationships require authoritative approval logic.

## Q. PARENT MODE

Expected:

dashboard
child summaries
activity
safety queue
review detail
approve/block
screen-time limit
quiet hours
feature controls
category controls
messaging control
follow approvals
notifications
settings/logout

These controls must be server-enforced, not cosmetic client switches.

## R. ADMIN MODE

Expected:

dashboard
moderation queue
review detail/evidence
approve
block
escalate
user search/status where supported
audit history
logout

All privileged actions must be server-authorized and audited.

## S. MEDIA STORAGE

Cloudflare R2 remains private.

Expected lifecycle:

quarantine upload
→ processing
→ private REVIEW
→ sanitized ALLOW promotion
or
→ BLOCK cleanup

Use signed/authorized delivery.

Do not make the bucket public.

## T. DATABASE

Neon project:
little

Production:
READ ONLY during testing unless explicit release approval is given.

Disposable testing:
disposable-test-agent-a-v2

Repository migration chain must remain consistent.

Never use heliumdb as LittleNet product evidence.

## U. MODAL

Canonical release app identities:

littlemuse-web
littlemuse-ai

Shared retained resources may keep existing names (for example
littlenet-model-cache, littlenet-r2 and littlenet-email) and are referenced
through environment-configurable names.

Maintain scale-to-zero. Routine health should not unnecessarily wake expensive
GPU workloads. App/secret/volume identities must be asserted by CI so a merge
cannot silently point web code at a different Modal app.

## V. UI TARGET

Stitch ZIP / existing UI parity matrix is visual authority.

Goal:
Instagram-quality familiarity while remaining LittleNet branded and child-safe.

Prioritize exact polish for demo-critical screens:

Welcome
Parent signup
OTP
Parent device authentication
Child onboarding
Feed
Reels
Explore
Search
Create
Processing
Profiles
Chat
Quiz
Parent
Admin

Do not spend release time building unsupported advanced screens before core
flows work physically.

## W. RELEASE REQUIREMENT

A feature is not "DONE" merely because:

route exists
unit test exists
source exists
JS export passes

Use states:

IMPLEMENTED
AUTOMATED_TESTED
LIVE_SERVICE_VERIFIED
DEVICE_VERIFIED
BLOCKED
MISSING

Physical Android evidence is required for native/camera/video/user-flow claims.
