# LittleMuse Final Product Architecture — 16-Task Release Program

Status: architecture baseline for the next implementation wave.
Source baseline: `main` at `09607c6a8bc830071b5670d151a0f1a93bd6586d`.
Open hotfix at time of writing: PR #9 (`fix/post-merge-release-blockers-20260924`).
This document defines the target architecture. Runtime fixes may exist on PR #9 before they are merged to `main`.

## 1. Product invariants

1. Kids Mode must feel Instagram-fast while remaining fail-closed for child safety.
2. UI never invents capabilities or identities the backend cannot represent.
3. Social child content and editorial curated content remain separate trust domains.
4. All user-generated media is private until moderation returns ALLOW.
5. Parent controls are server-authoritative and must remain meaningful offline.
6. Compulsory Reel Brain Breaks are server-authoritative, persisted, and non-skippable.
7. Feed/Reels pagination must distinguish "page ended" from "eligible inventory exhausted".
8. Release builds come from one exact Git SHA and the supported Expo/EAS identity.

## 2. System map

Mobile (Expo / React Native)
→ authenticated mobile API
→ PostgreSQL / Neon
→ Cloudflare R2 quarantine + published objects
→ background media worker
→ image/text/video safety services
→ publication
→ cursor-paginated Feed/Reels sessions.

Roles:
- CHILD: Feed, Reels, Stories, Create, Explore, Profiles, Quiz, Chat.
- PARENT: child creation, approvals, screen time, content controls, safety review.
- ADMIN: moderation, audit, content/account oversight.

## 3. Content identity architecture

Every rendered feed item keeps:
- `source_type`: SOCIAL | CURATED
- `source_id`: source-domain ID
- optional `post_id` only for SOCIAL
- optional `creator_id` for CURATED
- shared render fields: author_name, username, avatar_url, caption, category, media.

### 3.1 Curated creator model

Do not map editorial content to real child accounts.

Add an editorial creator domain:

`curated_creators`
- creator_id PK
- display_name
- username UNIQUE
- avatar_reference
- bio
- interest_vertical
- active
- created_at / updated_at

`curated_content.creator_id`
→ FK to `curated_creators.creator_id`.

The 14 product-owner personas (Ananya, Chef Aarav, Kabir, Maya, etc.) are editorial personas, not real children.

`services/curated_feed.py` must hydrate creator identity from the relation and must not hardcode "LittleNet Learning".

## 4. Source-aware engagement architecture

Do not treat `curated_content.content_id` as `posts.post_id`.

Use source-aware engagement:

`content_reactions`
- child_id
- source_type SOCIAL | CURATED
- source_id
- reaction_type LIKE
- created_at
- UNIQUE(child_id, source_type, source_id, reaction_type)

`content_saves`
- child_id
- source_type
- source_id
- created_at
- UNIQUE(child_id, source_type, source_id)

Comments:
- SOCIAL continues to use existing post comments.
- CURATED comments require a dedicated source-aware comment thread or an explicit product decision to disable curated comments.
- UI must not expose a Comment button for CURATED until a real backend thread exists.

Share:
- source-aware deep link payload: source_type + source_id.
- no fake post ID conversion.

## 5. Feed/Reels infinite-session architecture

Current pagination is cursor-based inside one materialized session. A child can reach a true end of that session even when the global catalog contains more eligible content.

Target behavior:

1. Client requests session page with `cursor`, `session_id`, `limit`.
2. Server returns:
   - items
   - next_cursor
   - has_more
   - session_id
   - total_in_session
   - exhaustion_reason
   - can_refill
3. When `has_more=false`:
   - if session exhausted but eligible catalog may contain more items, server/client rotates to a fresh session automatically;
   - recent-impression rules are relaxed only according to an explicit refill policy;
   - duplicate suppression remains bounded and deterministic;
   - if no additional eligible inventory exists, return `can_refill=false` and a true end-of-feed state.
4. Reels and Feed both prefetch before the last item.
5. Refresh may explicitly request a new session rather than silently reusing the old session.

Recommended API additions:
- `refresh=1` or `new_session=1`
- `exhaustion_reason`: SESSION_END | NO_ELIGIBLE_CONTENT | PARENT_FILTER | SAFETY_FILTER
- `can_refill`: bool

Recommended refill policy:
- first session: exclude recent impressions (2h)
- refill session: widen recent-impression window only if the remaining eligible pool is too small
- never bypass block/mute/age/parent/safety authorization.

This is the architectural fix for the physical-device symptom "6–9 items then nothing".

## 6. Story deep-link architecture

Stories tray opens the exact tapped story.

Route params:
- `initialStoryId`
- optional `initialChildId`

`StoriesScreen` loads the authoritative story list, finds the requested story, starts at that index, and falls back safely to index 0 only if the requested story is no longer available.

Empty list must always expose a close/back action.

## 7. Reels action architecture

Camera:
- navigates to Create with `initialKind='reel'`.

Follow:
- SOCIAL Reel → current parent-mediated child follow flow.
- CURATED Reel → only enabled after a curated-creator follow/subscription product model exists.
- do not bind editorial personas to child follow endpoints.

Audio:
- Reel player owns `muted` state.
- one explicit UI control toggles audio without restarting pagination or playback position.

## 8. Profile counts

Do not use `posts.length` as authoritative profile totals.

Backend profile response should expose:
`counts: { posts, followers, following, likes? }`.

The visible posts array remains independently paginated/limited.

Own and Other profile screens render server counts.

## 9. Create category + prevalidation architecture

Parent controls remain authoritative.

Create flow:
1. fetch allowed/available categories;
2. child selects category;
3. client prevalidates category before R2 upload;
4. backend revalidates at upload-session creation and completion;
5. media upload begins only after prevalidation passes.

Client prevalidation saves bandwidth but is never a security boundary.

## 10. Quiz pacing architecture

Existing persisted random Reel threshold remains authoritative.

Replace the legacy exact integer parent frequency with a policy profile:

- FREQUENT: random range 2–5
- BALANCED: random range 4–7
- LIGHT: random range 7–10

The exact ranges are product-configurable constants.

Store:
- parent policy
- current persisted next_quiz_threshold
- posts_seen
- viewed IDs
- quiz_required latch

Changing policy does not bypass an already-latched quiz.
A new threshold is rolled after completion using the active policy range.

Voluntary Quiz Zone remains independent.

## 11. Parent DOB architecture

Use a proper date picker UX but preserve server-side DOB/age validation.
No native dependency should be introduced without Expo compatibility verification.

## 12. Offline screen-time architecture

Do not lock merely because network is absent for 90 seconds.

Persist last authoritative screen-time state locally:
- daily_limit_minutes
- minutes_used / remaining
- strict_mode
- quiet-hours schedule
- last_server_sync

Offline enforcement:
- continue local countdown;
- enforce quiet-hours locally;
- lock when local authoritative allowance is exhausted;
- fail closed only after a deliberately defined long stale-policy window;
- resync immediately on reconnect.

Server remains authoritative when online.

## 13. Explore architecture

Explore owns one vertical scroll target at a time.
On focus/category switch/search mode switch:
- reset the active vertical list to offset 0.

"Learn more" opens a child-safe privacy/safety explainer describing:
- parent controls
- curated content
- AI moderation
- privacy
- reporting.

## 14. Navigation architecture

Full-screen child routes must have:
- normal stack `goBack()` when available;
- explicit KidsTabs→Feed fallback when no history exists;
- Android hardware BackHandler where the screen captures full-screen flow;
- draft confirmation for Create.

## 15. Release architecture

Supported release:
1. merge reviewed source
2. exact release SHA
3. Neon restore point
4. migration history check
5. reviewed migrations
6. zero pending
7. model artifact verification
8. Modal AI
9. Modal Web
10. zero-GPU preflight
11. health/R2/Resend
12. EAS build from exact SHA
13. ONE physical tester
14. expand only after acceptance.

Do not replace the reproducible EAS release pipeline with an ad-hoc local Gradle release as the canonical build path.

## 16. Implementation ownership

### OpenAI wave — 8 tasks
5. Story exact-ring selection.
6. Curated creator data model + mapping.
7. Source-aware curated Like/Save/Share backend and UI contract (comments only after real thread model).
9. Authoritative profile counts.
10. Dynamic category selector.
11. Pre-upload parent-category validation.
13. Parent random-range quiz pacing.
15. Offline screen-time enforcement.

### AntiGravity wave — 8 tasks
1. Re-verify/finalize Create/Stories/Conversations navigation fallbacks.
2. Re-verify/finalize single LittleNet Feed header.
3. Explore reset-to-top behavior.
4. Reels camera → Create Reel.
8. Reel Follow + audio controls, respecting SOCIAL vs CURATED identity.
12. Explore child-safe "Learn more" explainer.
14. Parent DOB date picker.
16. Clean reproducible APK/build validation from the agreed release SHA; no production deployment without approval.

### Shared prerequisite
Feed/Reels session refill architecture is a cross-cutting release task and must be implemented/tested before final physical-device acceptance. It is not counted as one of the 16 because it is a root-cause correction for the observed scrolling defect.

## 17. Acceptance criteria

No task is considered complete by source-string tests alone.

Required behavioral contracts include:
- Feed/Reels can continue through multiple pages and rotate/refill sessions until true eligible inventory exhaustion.
- tapped story ring opens the selected story.
- R2 upload → moderation → published reference → signed playback resolves the same object.
- curated identities come from DB relations, never random/hardcoded client labels.
- curated actions hit source-aware endpoints.
- profile totals come from server counts.
- restricted category is rejected before media transfer and again server-side.
- Parent quiz pacing preserves a persisted non-skippable server latch.
- offline screen-time cannot be bypassed by disabling networking.
- release APK is built from the exact audited SHA.
