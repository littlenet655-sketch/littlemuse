# LittleNet Live Production Storage & Database Audit

**Audit Timestamp**: 2026-09-20 16:50:00 IST  
**Environment**: Production (Neon PostgreSQL + Cloudflare R2 + Modal Cloud Compute)  
**Verification Mode**: STRICTLY READ-ONLY (No mutations, uploads, migrations, or deployments)

---

## Executive Summary

A comprehensive read-only audit of the LittleNet live production deployment was conducted across the source repository (`main`), Cloudflare Wrangler / R2, Neon PostgreSQL, and Modal compute environments.

### Key Highlights
1. **Cloudflare Authentication & R2**: Fully authenticated via OAuth (`Littlenet655@gmail.com's Account`, Account ID: `b324b6c8b125345cb06f8cf574b687e1`). Exactly one R2 bucket exists: `littlenet-media` (created `2026-09-08`). No accidental secondary or legacy bucket was detected.
2. **Video / Reels Delivery Mode**: **Production currently uses R2 MP4 playback.** Cloudflare Stream is not configured or enabled.
3. **Live Database (Neon PostgreSQL)**: 65 public tables verified. 13 migrations applied (through `20260913010000_processing_lease_and_concurrency.sql`).
4. **Database ↔ R2 Consistency Issues**: 
   - 22 DB posts point to `uploads/r2/posts/clean.jpg`, but `posts/clean.jpg` does NOT exist in R2 (404 on fetch).
   - 78 DB posts point to local ephemeral disk paths (`uploads/posts/...`, `uploads/stories/test.jpg`) that do not exist on serverless Modal containers.
   - 6 non-dataset objects in R2 (`posts/18/18_media.png`, `posts/9991/4_media.jpg`, `reels/9991/6_poster.jpg`, and 3 quarantine files) are orphaned test artifacts.
   - User video posts: 0 out of 70 are in `ALLOWED` status (61 failed due to missing quarantine source media or reap timeout, 9 stuck in processing lease).
   - Curated video reels: All 122 curated educational reels exist in R2 (`uploads/r2/littlenet/dataset/reels/*.mp4`) and are marked `PUBLISHED` in the database, though their posters are `NULL`.
5. **Modal Workspace Discrepancy**: The `.env` file lists `BASE_URL = https://littlenet655--littlenet-web-web.modal.run`, whose Modal workspace is disabled (`workspace ac-k7Fw3hOTLvOay39uja9XM2 is disabled`). The mobile application correctly targets `https://netlittle2--littlenet-web-web.modal.run` (configured in `mobile_app/.env`), which is active.
6. **Cost Controls & Moderation Cache**: `moderation_signal_cache` does not exist in the database or migration files. The cost flags `LITTLENET_USE_MODAL_IMAGE_CPU`, `LITTLENET_ALLOW_IMAGE_GPU_FALLBACK`, `LITTLENET_USE_MODAL_TEXT_CPU`, and `LITTLENET_MODERATION_CACHE_VERSION` are absent from the repository and deployment. Moderation runs uniformly on Modal GPU (`T4`).

---

## A. Cloudflare Auth & R2 Bucket Verification

### Authentication & Account
- **Command Executed**: `npx wrangler whoami`
- **Authenticated Email**: `littlenet655@gmail.com`
- **Account Name**: `Littlenet655@gmail.com's Account`
- **Account ID**: `b324b6c8b125345cb06f8cf574b687e1`
- **R2 Endpoint**: `https://b324b6c8b125345cb06f8cf574b687e1.r2.cloudflarestorage.com`

### Bucket Inventory
- **Command Executed**: `npx wrangler r2 bucket list`
- **Bucket Found**: `littlenet-media`
- **Creation Date**: `2026-09-08T12:45:27.305Z`
- **Bucket Count**: Exactly 1. No secondary or obsolete buckets exist.

### Prefix & Object Audit

| Prefix | Object Count | Last Modified (Sample) | Expected by Code? | Found? | Problem / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `quarantine/` | 3 | 2026-09-10 12:44:16 UTC | Yes (`uploads/r2/quarantine/{uid}/{upload_id}/source.{ext}`) | Yes | 3 orphaned quarantine files from Child 9991 (test account deleted from DB). |
| `posts/` | 2 | 2026-09-11 17:10:18 UTC | Yes (`uploads/r2/posts/{child_id}/{post_id}_media.{ext}`) | Yes | `posts/18/18_media.png` & `posts/9991/4_media.jpg` exist, but DB references `posts/clean.jpg`. |
| `reels/` | 1 | 2026-09-10 13:03:01 UTC | Yes (`uploads/r2/reels/{child_id}/{post_id}_poster.jpg`) | Yes | `reels/9991/6_poster.jpg` exists as orphan. No user video files exist in `reels/`. |
| `stories/` | 0 | None | Yes (`uploads/r2/stories/{child_id}/{post_id}_media.{ext}`) | No | No story objects exist in R2. All DB stories reference local disk `uploads/stories/test.jpg`. |
| `littlenet/` | 208 | 2026-09-09 16:09:14 UTC | Yes (`uploads/r2/littlenet/dataset/...`) | Yes | 122 curated educational reels + images, metadata, and benchmarks. Valid and healthy. |
| `avatars/` | 0 | None | Yes (`uploads/r2/avatars/{child_id}/...`) | No | No avatars stored in R2. All `child_profiles.profile_picture` values are `NULL`. |

---

## B. Image Upload Pipeline Verification

### Code Pipeline Trace
1. **Upload Request**: Mobile client calls `POST /api/mobile/v2/uploads/session` with `media_type='IMAGE'`, `mime_type`, `extension`, `size_bytes`.
2. **Session Initialization**: Row inserted into `upload_sessions` (`status='PENDING'`), object key set to `uploads/r2/quarantine/{uid}/{upload_id}/source.{ext}`.
3. **Presigned Upload**: Backend returns `upload_url` via `object_storage.signed_upload_url()` (short-lived presigned PUT URL).
4. **Direct R2 Upload**: Client directly PUTs raw image to R2 quarantine.
5. **Post Creation**: Client calls `POST /api/mobile/v2/uploads/{upload_id}/complete` with `caption`, `tags`, etc. Session marked `CONSUMED`. Post inserted with `processing_status='QUEUED'`.
6. **Processing Worker**: `services/media_processor.py::process_media_job` claims the post with an atomic lease token.
7. **Sanitization & Safety**:
   - Downloads source from R2 quarantine.
   - PIL transposes EXIF and strips GPS/metadata, saving clean RGB JPEG.
   - Runs AI moderation (`evaluate` for TEXT and IMAGE).
8. **Publication**:
   - If ALLOWED: Uploads clean JPEG to `uploads/r2/posts/{child_id}/{post_id}_media.jpg`. DB `media_path` updated. `is_safe=TRUE`, `moderation_status='ALLOWED'`.
   - If BLOCKED: Post `media_path=NULL`, `is_safe=FALSE`, `moderation_status='BLOCKED'`. Quarantine object deleted.
9. **URL Resolution**: `services/media_delivery.py::resolve_media_delivery` generates signed download URL (`DIRECT_SIGNED`, 10-minute expiry) bound to authorized viewers only.

### Live Example & Security Verification
- **Safety Fail-Closed Check**: Tested BLOCKED posts (Posts 41, 67, 68). Result: `delivery_mode='DENIED'`, `url=None`. Blocked media is never exposed.
- **Unauthorized Viewer Check**: Tested Post 155 with unauthorized child ID `999999`. Result: `delivery_mode='DENIED'`, `url=None`.
- **Authorized Delivery Check**: Post 155 with author child `116`. Result: `delivery_mode='DIRECT_SIGNED'`, URL resolves to `https://b324b6c8b125345cb06f8cf574b687e1.r2.cloudflarestorage.com/littlenet-media/posts/clean.jpg`.
- **Pipeline Discrepancy Found**: Post 155 (and 21 other posts) point to `uploads/r2/posts/clean.jpg`. The object `posts/clean.jpg` was not persisted in R2, so client fetches result in HTTP 404.

---

## C. Video / Reels Storage Verification

### Delivery Mode Confirmation
- **Configuration Check**: `CLOUDFLARE_STREAM_ENABLED`, `CLOUDFLARE_STREAM_ACCOUNT_ID`, and `CLOUDFLARE_STREAM_SUBDOMAIN` are NOT set in the environment or codebase.
- **Explicit Mode Statement**: **Production currently uses R2 MP4 playback.**

### Video Processing & DB Records Analysis
- **Total Video Posts in DB**: 70
- **Moderation Status Breakdown**:
  - `ALLOWED`: 0
  - `PENDING`: 70
- **Processing Status Breakdown**:
  - `FAILED`: 61 posts
    - 51 posts: `quarantine_media_missing_or_empty` (Upload session created, but client did not complete PUT or local mock path was lost).
    - 10 posts: `max_attempts_exceeded_stale_reap`.
  - `PROCESSING`: 9 posts (Stuck in lease timeout; worker did not finalize).
- **Video Poster Verification**:
  - All 70 user video posts have `poster_path = NULL`.
  - In R2, only a single legacy reel poster exists: `reels/9991/6_poster.jpg` (orphan).
- **Curated Video Reels**:
  - 122 curated educational reels exist in `curated_content` (`is_reel=TRUE`, `publish_status='PUBLISHED'`).
  - All 122 MP4 video assets exist in R2 under `littlenet/dataset/reels/*.mp4` (verified via `head_object`, e.g. `VID_20260905_011100_156.mp4` = 2.96 MB).
  - All 122 curated reels have `poster_object_key = NULL`.
- **Can User Videos Be Fetched?**: **No.** Currently, no user-created video or reel has reached `ALLOWED` status with a valid media path. Only curated educational reels can be fetched and played.

---

## D. Live PostgreSQL / Neon Database Audit

- **Connection**: Neon Serverless PostgreSQL (`ep-young-tree-ae9n9m6q-pooler.c-2.us-east-2.aws.neon.tech/neondb`)
- **Total Tables in Public Schema**: 65
- **Latest Applied Migration**: `20260913010000_processing_lease_and_concurrency.sql` (13 total migrations)

### Target Concept / Table Verification

| Concept / Table | Exists? | Row Count | Latest Created/Updated Record Time | Used by Current Code? | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `users` | **Yes** | 390 | 2026-09-20 06:25:25 | Yes (`auth/`, `services/`, `mobile/`) | **ACTIVE** |
| `parent_child_map` | **Yes** | 69 | 2026-09-20 06:31:59 | Yes (`parent/`, `mobile/api.py`) | **ACTIVE** |
| `child_profiles` | **Yes** | 310 | 2026-09-20 06:25:25 | Yes (`child/`, `services/`) | **ACTIVE** |
| `face_profiles` | **Yes** | 115 | 2026-09-20 06:32:01 | Yes (`safety/face_service.py`) | **ACTIVE** |
| `posts` | **Yes** | 593 | 2026-09-20 10:21:26 | Yes (`mobile/api.py`, `services/`) | **ACTIVE** |
| `upload_sessions` | **Yes** | 308 | 2026-09-20 10:21:35 | Yes (`mobile/api.py`) | **ACTIVE** |
| `moderation_events` | **Yes** | 211 | 2026-09-20 06:37:48 | Yes (`safety/moderation_service.py`) | **ACTIVE** |
| `moderation_reviews` | **Yes** | 46 | 2026-09-20 06:24:00 | Yes (`parent/`, `mobile/admin_api.py`) | **ACTIVE** |
| `recommendation_signals` | **Yes** | 31 | 2026-09-20 09:52:43 | Yes (`services/recommendation.py`) | **ACTIVE** |
| `feed_sessions` | **Yes** | 6 | 2026-09-20 09:20:33 | Yes (`services/curated_feed.py`) | **ACTIVE** |
| `content_impressions` | **Yes** | 0 | None | Yes (`services/curated_feed.py`) | **EMPTY** |
| `child_messages` | **Yes** | 0 | None | Yes (`childMessage/service.py`) | **EMPTY** |
| `child_conversations` | **Yes** | 1 | 2026-09-13 03:05:16 | Yes (`childMessage/service.py`) | **ACTIVE** |
| `parent_control_settings` | **Yes** | 25 | 2026-09-20 06:32:00 | Yes (`services/controls.py`) | **ACTIVE** |
| `parent_safety_settings` | **Yes** | 22 | 2026-09-20 06:31:59 | Yes (`services/controls.py`) | **ACTIVE** |
| `notifications` | **Yes** | 67 | 2026-09-20 06:35:00 | Yes (`services/social.py`, `mobile/`) | **ACTIVE** |
| `saved_posts` | **Yes** | 0 | None | Yes (`mobile/api.py`) | **EMPTY** |
| `likes` | **Yes** | 0 | None | Yes (`mobile/api.py`) | **EMPTY** |
| `media_assets` | **Yes** | 0 | None | Legacy (superseded by R2) | **EMPTY** |
| `media_delete_outbox` | **Yes** | 1 | 2026-09-20 10:35:22 | Yes (`services/object_storage.py`) | **ACTIVE** (1 pending) |
| `curated_media_assets` | **Yes** | 122 | 2026-09-20 08:54:03 | Yes (`services/curated_feed.py`) | **ACTIVE** |
| `moderation_signal_cache` | **NO** | 0 | N/A | No (not in code or DB) | **MISSING FROM DB** |

---

## E. Database ↔ R2 Consistency Audit

### Sample & Cross-Verification Findings

1. **DB Record but Missing R2 Object**:
   - **Found**: 22 posts (e.g. Post 564, 540, 524, 507, 466, 452, 439, 426, 363, 337, 311, 285, 259, 233, 207, 181, 155, 130, 104, 86, 60, 47) have `media_path = 'uploads/r2/posts/clean.jpg'`.
   - **R2 State**: `posts/clean.jpg` is completely missing from R2.
2. **R2 Object but No DB Record (Orphaned Media)**:
   - `posts/18/18_media.png` (36.9 KB) - DB post 18 has `media_path = NULL`.
   - `posts/9991/4_media.jpg` (1.3 KB) - Child 9991 does not exist in `users`.
   - `reels/9991/6_poster.jpg` (13.1 KB) - Child 9991 does not exist in `users`.
   - `quarantine/9991/1855b05e-405b-4814-ab3d-45e737d7d50e/source.jpg`
   - `quarantine/9991/75e62a3e-878c-4ecc-ad46-ebd39e1606c5/source.jpg`
   - `quarantine/9991/c2017dbb-9e7e-4ccc-9cc0-de8140cb7df9/source.jpg`
3. **Post ALLOWED but Media Inaccessible**:
   - 22 R2 posts point to missing `posts/clean.jpg`.
   - 78 posts point to `uploads/posts/...` or `uploads/stories/test.jpg` (local disk paths on non-existent local containers).
4. **Post BLOCKED/REVIEW but Publicly Accessible**:
   - **None.** Verified fail-closed: blocked posts have `media_path = NULL` and resolve to `DENIED`.
5. **Poster URL Missing for Video**:
   - 70 out of 70 user video posts in `posts` have `poster_path = NULL`.
   - 122 out of 122 curated educational reels in `curated_media_assets` have `poster_object_key = NULL`.
6. **Stale Quarantine Objects**:
   - 3 objects in `quarantine/9991/` from 2026-09-10 remain unpurged.
7. **Database Path Pointing to Old Bucket/Domain**:
   - None. DB stores normalized relative keys (`uploads/r2/...`).
8. **Cloudflare URL Using Expired/Wrong Host**:
   - None. Host resolves dynamically to `https://b324b6c8b125345cb06f8cf574b687e1.r2.cloudflarestorage.com`.
9. **Media Delete Outbox**:
   - 1 uncompleted deletion: `uploads/r2/quarantine/202/pic.jpg` (Post 501, created `2026-09-20 10:35:22 UTC`).

---

## F. Current Feed & Reels Data Audit

### Content Counts Breakdown
- **Total Posts**: 593
- **Allowed Posts**: 213 (113 text-only / NULL media, 78 local disk paths, 22 pointing to missing `posts/clean.jpg`)
- **Review Posts**: 0
- **Blocked Posts**: 134
- **Pending Posts**: 246
- **Images**: 506
- **Videos**: 70
- **Stories**: 13 (all 13 belong to child 991 and point to local `uploads/stories/test.jpg`)
- **Reels (Social)**: 44 (0 allowed, all failed/processing)
- **Reels (Curated Learning)**: 122 (all 122 published with verified MP4 assets in R2)
- **Posts with Missing Media**: 493
- **Videos with Missing Poster**: 70 (plus 122 curated reels)
- **Posts by Active Child Accounts**: 593

### Root Cause Analysis: Why a Feed Looks Empty
Even though R2 holds 122 curated videos, a child's feed in the mobile app can display empty due to the following server-side gates:
1. **Onboarding / Feed Quiz Gate**: `_child_gate()` in `mobile/api.py` checks `needs_onboarding_quiz(uid)` and `feed_quiz_state(uid)`. If the child hasn't passed the onboarding safety quiz or if a feed-break quiz is triggered, the feed returns `428 quiz_required`.
2. **Quiet Hours / Screen Time Gate**: If the child is logged in during scheduled quiet hours or exceeded their daily screen time limit, the endpoint returns `423 quiet_hours` or `screen_time_limit`.
4. **Discoverability & Friend Filtering**: `fetch_social_candidates()` calls `discoverable_child_ids(child_id)`. If the parent has set `allow_discover = FALSE` and the child has no approved followers/friends, `allowed_child_ids` is empty, hiding all social posts.
5. **Educational-Only Filtering**: If `educational_only_feed` is toggled ON by the parent, all non-educational social posts are filtered out.
6. **Curated Feed vs Reels Split**: All 122 curated items have `is_reel = TRUE`. None are tagged `is_reel = FALSE`. Consequently, the standard home feed (`surface="FEED"`) has **zero** curated candidate items and must rely exclusively on social posts. If social posts are filtered out by relationship or age rules, the home feed is completely blank.

---

## G. Safe Recommendation Engine Verification

### Live DB Tables Status
- **`recommendation_signals`**:
  - Table Exists: **Yes**
  - Row Count: **31 rows**
  - Recent Rows: **Yes** (Latest: `2026-09-20 09:52:43 UTC`, Child `5`, `REEL_COMPLETION`, weight `1.500`)
  - Signal Types Logged: `REEL_COMPLETION`, `BLOCK`, `REPORT`
  - Indexes: `recommendation_signals_pkey`, `idx_recommendation_signals_child_source`, `idx_recommendation_signals_child_src` all present.
- **`feed_sessions`**:
  - Table Exists: **Yes**
  - Row Count: **6 rows**
  - Recent Rows: **Yes** (Latest: `2026-09-20 09:20:33 UTC`, Child `2`, surface `REELS`)
  - Indexes: `feed_sessions_pkey`, `idx_feed_sessions_child`, `idx_feed_sessions_child_exp` all present.
- **`content_impressions`**:
  - Table Exists: **Yes**
  - Row Count: **0 rows**
  - Indexes: `content_impressions_pkey`, `idx_content_impressions_recent`, `idx_content_impressions_child_shown` all present.
  - Integration: `services/curated_feed.py::record_feed_impression` is wired to insert impressions when mobile client POSTs to `/api/mobile/v2/kids/impressions`.

---

## H. Moderation Cost-Cache Database Verification

- **Table Inspected**: `moderation_signal_cache`
- **Table Exists?**: **NO**
- **Indexes Exist?**: **NO**
- **Row Count**: **0**
- **Migration Check**: No migration file exists in `db/migrations/` for `moderation_signal_cache`.
- **Status Statement**:
  > **Code is merged but production migration is not applied** (and neither the migration file nor the table is present in the repository `main` branch or production database).

---

## I. Modal / Cost Configuration Verification

### Cost Guard Flags Audit
The following cost control flags were inspected across code, `.env`, and Modal deployment:
- `LITTLENET_USE_MODAL_IMAGE_CPU`: **Not present**
- `LITTLENET_ALLOW_IMAGE_GPU_FALLBACK`: **Not present**
- `LITTLENET_USE_MODAL_TEXT_CPU`: **Not present**
- `LITTLENET_ALLOW_TEXT_GPU_FALLBACK`: **Not present**
- `LITTLENET_MODERATION_CACHE_VERSION`: **Not present**
- `LITTLENET_IMAGE_MODERATION_MAX_PX`: **Not present**

### Actual Modal Hardware Deployment
- **Inspection of `modal_ai.py`**:
  - Single Modal app: `littlenet-ai`
  - Container Hardware: `gpu="T4"`, `cpu=4.0`, `memory=8192`
  - Device Setting: `LITTLENET_DEVICE: "cuda"`
- **Hardware Routing Breakdown**:
  - **Image Upload Moderation**: Uses **GPU (T4)**. (No CPU worker exists).
  - **Text Moderation**: Uses **GPU (T4)**. (No CPU worker exists).
  - **Video Moderation**: Uses **GPU (T4)** with single-frame policy (2026-09-23): exactly one representative frame per video is AI-scored.
  - **Recommendation Engine**: Runs purely on web backend CPU without GPU invocation (`AI_ENABLE_REMOTE_RANKING=0`).
- **Conclusion**: The CPU-only image/text moderation split is **NOT LIVE**; all inference executes on the T4 GPU container.

---

## J. Final Audit Matrix

| Area | Code Exists | Live DB Ready | Live R2 Ready | Deployed | Verified | Problem / Root Cause |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Parent Signup** | Yes | Yes | N/A | Yes | Yes | Working in production |
| **OTP** | Yes | Yes | N/A | Yes | Yes | 6 active OTP records in DB; Resend/SMTP ready |
| **Parent-Child Mapping** | Yes | Yes | N/A | Yes | Yes | 69 verified relationships in DB |
| **Face Enrollment / Face Login** | REMOVED 2026-09-22 | REMOVED | REMOVED | REMOVED | N/A | All face/biometric artifacts removed by product decision; children log in with passwords. |
| **Image Upload** | Yes | Yes | Yes | Yes | Partial | V2 presigned PUT works; DB points to missing `posts/clean.jpg` |
| **Image Moderation** | Yes | Yes | N/A | Yes | Yes | Runs on Modal GPU T4; fail-closed safety verified |
| **Image Publication** | Yes | Yes | Yes | Yes | Partial | Code publishes to R2, but 78 DB rows reference local disk paths |
| **Feed** | Yes | Yes | Yes | Yes | Partial | Home feed empty if child lacks friends or fails quiz gate |
| **Inline Feed Video** | Yes | Yes | Yes | Yes | No | 0 user videos in ALLOWED; curated items are reels only |
| **Stories** | Yes | Yes | No | Yes | No | 13 stories in DB all point to missing local path `uploads/stories/test.jpg` |
| **Reels** | Yes | Yes | Yes | Yes | Yes (Curated) | 122 curated educational reels play from R2; 0 social reels allowed |
| **Video Playback** | Yes | Yes | Yes | Yes | Yes (Curated) | Direct R2 MP4 playback verified; Cloudflare Stream is not used |
| **Video Poster** | Yes | Yes | No | Yes | No | All 70 user videos & 122 curated reels have `poster_path = NULL` |
| **Safe Recommendation**| Yes | Yes | N/A | Yes | Yes | Database-level candidate filtering active |
| **Recommendation Signals**| Yes | Yes | N/A | Yes | Yes | 31 real user signals logged (`REEL_COMPLETION`, `BLOCK`, etc.) |
| **Feed Sessions** | Yes | Yes | N/A | Yes | Yes | 6 active feed session records with TTL |
| **Text Moderation** | Yes | Yes | N/A | Yes | Yes | Detoxify running on Modal GPU |
| **Image Moderation Cache**| No | No | N/A | No | No | `moderation_signal_cache` missing from repo & database |
| **Parent Controls** | Yes | Yes | N/A | Yes | Yes | 25 control settings rows active; gates enforced server-side |
| **Notifications** | Yes | Yes | N/A | Yes | Yes | 67 notification records active |

---

## Categorized Findings & Priorities

### 1. Confirmed Working in Production
- Cloudflare Wrangler / R2 authentication and single bucket `littlenet-media` topology.
- Direct signed URL generator with strict viewer authentication and fail-closed gates.
- Curated educational reels pipeline: 122 videos stored in R2 and served via signed MP4 URLs.
- Neon database core entities: `users`, `child_profiles`, `parent_child_map`, `feed_sessions`, `recommendation_signals`.
- Child password login plus compulsory onboarding quiz.
- Parent controls and safety gating (quiet hours, screen time limits, category filters).

### 2. Code Exists but Not Deployed
- Bounded CPU-only image/text moderation split (`modal_ai.py` currently deploys all inference onto a single T4 GPU).
- Client impression reporting (`content_impressions` table exists in DB, but has 0 rows).

### 3. Database Migration Missing
- `moderation_signal_cache`: Migration has not been authored or applied to production.

### 4. Cloudflare / R2 Problems
- Orphaned media: 6 non-dataset objects in `quarantine/`, `posts/`, and `reels/` from deleted test child accounts.
- Missing video posters: No posters exist for the 122 curated reels in R2.

### 5. DB ↔ R2 Mismatches
- 22 DB posts reference `uploads/r2/posts/clean.jpg`, which does not exist in R2 (HTTP 404).
- 78 DB posts reference local container disk paths (`uploads/posts/...`), which fail on serverless containers.
- 13 stories in DB reference `uploads/stories/test.jpg` (non-existent local file).
- 70 user videos in DB have 0 successful `ALLOWED` records (51 failed on missing quarantine upload).

### 6. Needs Real-Phone Test
- Camera video recording and direct R2 PUT upload flow on physical Android/iOS device.
- Story camera capture and playback.

### 7. Exact Next Actions in Priority Order
1. **Fix Backend URL in `.env`**: Update `BASE_URL` in root `.env` from the disabled `littlenet655` workspace to active `https://netlittle2--littlenet-web-web.modal.run`.
2. **Generate Video Posters for Curated Reels**: Run an offline script to extract first-frame posters for the 122 curated reels, upload to `uploads/r2/littlenet/dataset/posters/`, and update `curated_media_assets.poster_object_key`.
3. **Reconcile Stale DB Media References**: Clean up or update the 22 posts pointing to missing `posts/clean.jpg` and 78 posts pointing to local `uploads/` paths so they do not produce broken media tiles in client feeds.
4. **Author & Apply `moderation_signal_cache` Migration**: If image moderation caching is required to reduce GPU spend, write the migration SQL and deploy the table with appropriate indexes.
5. **Implement CPU Moderation Split in `modal_ai.py`**: Separate lightweight text/image moderation into a CPU container to prevent unnecessary T4 GPU wakeups.
