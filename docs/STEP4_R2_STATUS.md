# Step 4 — R2 media delivery/privacy

Scope is intentionally limited to private R2 media handling.

Implemented:

- authorized `/uploads/r2/...` delivery through short-lived signed URLs
- account-specific R2 origin in CSP for redirected image/video loads
- `private, no-store, max-age=0` on child upload responses and stored R2 metadata
- signed URL TTL default 180 seconds, clamped to 60–600 seconds
- child post/story R2 cleanup after successful DB deletion
- regression coverage for signing, TTL clamp, exact delete key, no-store caching, authorization-before-signing, and deletion hooks

Not included in this step: friendship approval, discovery privacy, quiz persistence, blink/liveness redesign (superseded: face artifacts removed 2026-09-22), Android cleanup, or deployment credential work.
