# 07 — Cloudflare R2 & Media Lifecycle Audit Report

**Audited Date:** 2026-09-08  
**Audit Scope:** Object storage configuration, private bucket enforcement, signed URL generation, TTL, upload-before-DB transactions, rollback semantics, fast-start reels, and media privacy.  

---

## 1. Storage Architecture & Privacy Contracts

Cloudflare R2 object storage is implemented in [`services/object_storage.py`](file:///d:/aitprojects/LittleNet-1/services/object_storage.py) and governed by [`docs/R2_MEDIA_PRIVACY_CONTRACT.md`](file:///d:/aitprojects/LittleNet-1/docs/R2_MEDIA_PRIVACY_CONTRACT.md):

- **Private Bucket Invariant**: The production R2 bucket is strictly private. Direct public object URLs (`https://<bucket>.r2.dev/...`) are disabled.
- **Pre-signed URL Access**: All media delivery is performed using pre-signed S3 URLs with short-lived expiration (TTL default: 15–30 minutes).
- **Authorization Before Delivery**: Signed URLs are generated only after the requesting child user's session, parent category controls, and child age suitability have been validated by the backend.
- **Zero Leakage for Blocked Content**: Any media asset with `moderation_status IN ('BLOCKED', 'REVIEW', 'PENDING')` or `is_safe = FALSE` is blocked from pre-signed URL generation. The API returns HTTP 403 / 404 for unauthorized media requests.

---

## 2. Transaction Integrity: Upload-Before-DB & Rollback

```
1. Client uploads media payload -> Local ephemeral temp file
2. Full AI safety & moderation pipeline executes
   ├── If Safety FAILS (BLOCKED):
   │     • Ephemeral temp file deleted immediately
   │     • Moderation event logged to audit ledger
   │     • API returns HTTP 400 with safety explanation
   │     • Zero files written to R2 storage
   └── If Safety PASSES (ALLOWED):
         • Object uploaded to Cloudflare R2 (`services/object_storage.py`)
         • Fast-start derivative (moov atom prepended) generated
         • PostgreSQL transaction begins -> INSERT into `posts` / `curated_media_assets`
         • Transaction commits
         • If DB transaction fails -> R2 object deletion is triggered in rollback handler
```

---

## 3. Fast-Start & Video Scope

1. **Fast-Start Derivatives**: Vertical reels undergo MP4 normalization placing the `moov` atom at the start of the file. This allows mobile ExoPlayer and web video tags to begin playback immediately without downloading the full video.
2. **Audio Stripping**: In accordance with the retired audio scope, video processing pipelines strip standalone audio tracks or neutralize audio dependencies, preventing unexpected audio playback.
