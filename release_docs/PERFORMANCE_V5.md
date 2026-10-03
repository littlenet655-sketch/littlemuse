# LittleNet V5 Performance Report

**Date**: 2026-10-03
**Branch**: release-hardening-final-v5

---

## Backend Performance Improvements

### Discover N+1 Elimination (Group 2)

**Before**: Each post/profile in the discover feed triggered an individual `is_following`/`is_blocked` SQL query per profile. For a page of 30 results, this was 30+ sequential queries.

**After**: `batch_relationship_states(viewer_id, target_ids)` executes a single parameterized query with `ANY($1::integer[])` to fetch all relationship states for the entire page in one round trip.

**Measured query counts** (test: `tests/test_discover_n_plus_one.py`):

| Cohort Size | Queries Before | Queries After |
|-------------|---------------|--------------|
| 1 | 2+ | 1 |
| 5 | 6+ | 1 |
| 15 | 16+ | 1 |
| 30 | 31+ | 1 |

---

## Database Index Coverage

All V5 security migrations include appropriate indexes:

| Index | Purpose |
|-------|---------|
| idx_password_reset_otps_token | Fast token lookup for reset verification |
| idx_password_reset_otps_user_expires | Reaper query performance |
| idx_password_reset_rate_limits_ip | IP rate-limit enforcement |
| idx_posts_lease_expiry | Efficient stale lease detection |
| idx_posts_source_media_path_uniq | Dedup upload idempotency |
| idx_posts_upload_id_uniq | Upload session binding |

---

## Upload Session Lease Performance

The `processing_lease_expires_at` column allows the background worker to find stale leases efficiently:

```sql
SELECT post_id FROM posts
WHERE processing_status IN ('UPLOADED', 'PROCESSING')
  AND processing_lease_expires_at < NOW()
```

This query uses `idx_posts_lease_expiry` (partial index on processing_status IN ('UPLOADED', 'PROCESSING')) and is O(stale leases), not O(all posts).

---

## Moderation Cache Performance

`services/moderation_cache.py` caches AI moderation signals per content fingerprint:
- Fail-closed: `total_safety_failure=True` signals are never stored (prevents false cache hits)
- Cache hit eliminates Modal GPU invocation for previously-seen content
- Cache miss falls through to `modal_ai.py` GPU worker

---

## Mobile Performance

| Metric | Value |
|--------|-------|
| Android bundle size | 3.7 MB (Hermes bytecode, AppEntry-59b820e106ff3aae46c7ae7108339ce7.hbc) |
| Total assets | 37 assets bundled |
| Test suite duration | 1507ms for 283 tests |
| TypeScript check | 0 errors |
| Expo Doctor | 21/21 checks PASS |

---

## Async Media Processing Architecture

1. Client uploads direct to R2 quarantine via presigned PUT (15m TTL)
2. Client polls `/api/mobile/v2/uploads/{session_id}/status` — no blocking
3. Background worker acquires lease, runs AI moderation via Modal GPU
4. Worker updates `posts.processing_status` to ALLOWED or BLOCKED
5. Client gets final state on next status poll

This architecture eliminates synchronous AI inference on the API path. P99 upload response time is bounded by presigned URL generation, not AI processing time.

---

## Concurrency Safety

Verified on PG16 with a real multi-threaded barrier test (`tests/test_real_pg_concurrency_races.py`):
- 5 concurrent threads attempting to resolve the same parent review
- Only one TERMINAL state ever set (APPROVED or REJECTED)
- No double-resolution possible with the advisory-lock + UPDATE WHERE status = 'OPEN' pattern

Tested identically on PG18 with DISPOSABLE_DATABASE_URL pointing to port 5434.
