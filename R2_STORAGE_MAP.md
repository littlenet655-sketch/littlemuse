# R2 Storage Map

Private Cloudflare R2. PostgreSQL stores `uploads/r2/<key>` references, never public object URLs.
`services/object_storage.py` is the only boto3 adapter (`upload_file`, `head_object`, `download_file`, `copy_object`, `delete_reference`, `signed_download_url`, `signed_upload_url`).

Deployment writes are namespaced by `LITTLENET_R2_WRITE_PREFIX` (`_write_key` / `new_reference`). Deletes of references outside that prefix are refused so a deployment cannot remove another deployment's objects in a shared bucket. Objects are uploaded with `Cache-Control: private, no-store, max-age=0`. Signed GET TTL is clamped in `get_playback_ttl` (default from `R2_SIGNED_URL_TTL`).

Production R2 was not contacted. This map is from source.

## Object types

| Type | Writer | Key | DB field | Reader | Authorization | Lifecycle | Missing object |
|---|---|---|---|---|---|---|---|
| Post/Reel/Story original | `mobile.api` upload-session route | `uploads/r2/[prefix/]quarantine/{child_id}/{upload_id}/source.{ext}` | `upload_sessions.object_key`, then `posts.source_media_path` | Worker `download_file` in `services/media_processor.py`; parent preview via `_media_allowed` | Presign only for the authenticated child who created the session. Preview: owning parent or admin while `moderation_status` is REVIEW. Children cannot read quarantine. | Quarantine until ALLOW/BLOCK/REVIEW resolution, then `block_and_cleanup_quarantine` | `head_object` None sets `processing_error=quarantine_object_unavailable` and returns retryable. Attempts are capped by `posts.max_processing_attempts` (default 3) plus backoff in `retry_processing_job`. |
| Published post | `sanitize_and_promote_media` / worker ALLOW branch | `uploads/r2/[prefix/]posts/{child_id}/{post_id}_media.jpg` | `posts.media_path` | `resolve_media_delivery` → signed URL or `/api/mobile/v1/media` | `_media_allowed`: BLOCKED denied; ALLOWED uses `post_visible_to`; parent must `owns()` | Kept while the post is visible. Delete enqueues `media_delete_outbox`. | Delivery denies unknown refs. Playback does not invent bytes. |
| Published reel | same, `kind=reel` | `.../reels/{child_id}/{post_id}_media.mp4` | `posts.media_path` | `/api/mobile/v2` reel playback and generic playback (quiz latch when the target is a reel) | Same as posts, plus reel quiz latch on playback routes | Same | Same |
| Reel poster | same | `.../reels/{child_id}/{post_id}_poster.jpg` | `posts.poster_path` | Feed/reel card via `_asset_url` | Same visibility as the post | Deleted with the post | Missing poster is a null URL, not a crash |
| Story media | same, `kind=story` | `.../stories/{child_id}/{post_id}_media.{jpg\|mp4}` | `posts.media_path` | Story viewer APIs | Owner and allowed viewers; REVIEW bytes stay owner/parent only | Story expiry is a DB visibility rule; bytes follow post delete | Same as posts |
| Story music | story create path | reference stored as uploaded | `posts.story_music_path` | `_media_allowed` treats it like post media | Same as the story post | Included in `enqueue_post_media_deletes` | Denied if the row is gone |
| Chat original | chat upload session in `mobile/api.py` | `uploads/r2/[prefix/]chat_quarantine/{child_id}/{upload_id}/source.{ext}` | `chat_upload_sessions.object_key`, then `child_messages.media_path` while REVIEW | Sender; owning parent while REVIEW | Receiver sees it only after promotion to ALLOWED and `can_interact` | REVIEW keeps quarantine. Approve calls `promote_reviewed_chat_media`. Block calls `block_reviewed_chat_media`. Abandoned PENDING/EXPIRED sessions are swept by `reconcile_abandoned_chat_upload_sessions` (REVIEW excluded). | Empty download raises `chat_media_missing_or_empty` / `quarantine_media_missing_or_empty` and fails closed |
| Chat published | `promote_reviewed_chat_media` → `sanitize_and_promote_media` kind `chat` | `.../chat/{sender_id}/{message_id}_media.{jpg\|mp4}` | `child_messages.media_path` | Message thread | Sender and receiver while connected and ALLOWED | Quarantine deleted after promotion | Fail closed; approval converts to BLOCK |
| Curated reel/image | `tools/dataset_ingest.py` `upload_file` | `uploads/r2/[prefix/]curated/{version}/{category}/{sha256[:2]}/{sha256}/original|delivery|poster` | `curated_media_assets.original_object_key`, `delivery_object_key`, `poster_object_key`, `thumbnail_object_key` | Curated playback `/api/mobile/v2/curated/media/<id>` and `/api/mobile/v2/kids/reels/curated/<id>/playback` | Published + ALLOWED + safe + age + parent category. Parents/admins can read for supervision. | Catalog row is the lifecycle. Ingest is offline. | Unknown key is not a curated row, so user-upload policy applies and then denies |
| Profile avatar | local `child/routes.py` save under `uploads/profile_pictures/` (not the R2 quarantine pipeline) | `uploads/profile_pictures/profile_{user}_{uuid}.jpg` or seeded webp | `child_profiles.profile_picture` | `_asset_url` | Parent `owns`, or `can_discover_child`. Default `uploads/profile_pictures/download.webp` is allowed to signed-in roles. | Replaced on new upload | Fallback URL is null when unauthorized |
| Parent-review preview | no separate copy | the quarantine reference already on the post or message | not duplicated | Web `parent/routes.py` `review_preview` (60s signed redirect) and mobile safety list `_asset_url` | `owns()` plus OPEN REVIEW. Storage keys are stripped from the JSON. | Preview dies when the event is resolved and quarantine is deleted | `review_preview` returns 404 |
| Moderation evidence | not a separate public object | decisions live in `moderation_events` / `moderation_reviews` | those tables | parent/admin review APIs | same ownership rules | event row stays after RESOLVED; bytes do not | n/a |
| Delete outbox | DB triggers and `enqueue_delete` / `enqueue_post_media_deletes` | the reference being deleted | `media_delete_outbox.reference` | `reconcile_pending_deletes` | server-side only | `completed_at` set after `delete_reference`. Rows with `attempts >= 8` are left for an operator. | `delete_object` on an already-gone key is success; other errors increment `attempts` |

## Checks

- Keys are built on the server from child id and a UUID. The client extension is allowlisted. The original filename is not interpolated into the key.
- `../` is not accepted as a client object key. Presigned PUT targets the server key.
- Cross-user reads go through `_media_allowed` / `resolve_media_delivery`. Unauthorized viewers get `DENIED` and no signed URL.
- Bucket policy in this repo does not grant public read. `resolve_media_delivery` returns an already-absolute `http(s)` reference unchanged; application writers do not store absolute R2 URLs.
- Live object existence in the production bucket was not checked: EXTERNAL VERIFICATION REQUIRED.
