# LittleNet Private R2 Media Contract

LittleNet child media is stored in a **private Cloudflare R2 bucket** and is never served by a public bucket URL.

## Upload

- Child media is moderated first.
- Accepted/review media is persisted to R2.
- Video audio is stripped before persistence because standalone speech/audio moderation is intentionally retired.
- R2 objects are stored with `Cache-Control: private, no-store, max-age=0`.
- Neon/PostgreSQL stores only an `uploads/r2/<key>` reference.

## Read

- Clients request `/uploads/r2/<key>` from LittleNet, not R2 directly.
- LittleNet checks the logged-in role, content moderation status, ownership/relationship rules, blocks, and parent-child relationship before issuing access.
- Only after authorization does LittleNet create a presigned R2 GET URL.
- Default signed URL lifetime is 180 seconds; the implementation clamps any override to 60–600 seconds.
- `/uploads/*` responses are marked `private, no-store`.
- CSP permits only the configured account-specific R2 origin for image/media redirects.

## Delete

- On successful child post/story deletion, LittleNet removes the referenced R2 object after the database route succeeds.
- If R2 deletion itself fails, the bucket remains private and the database reference has already been removed, so the object is unreachable through LittleNet. The server logs the orphan cleanup failure for operator action.

This contract deliberately prioritizes authorization and child-media privacy over public CDN caching.
