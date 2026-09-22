# LittleNet Final Architecture

## Runtime boundaries

LittleNet has one native client: React Native + Expo in `mobile_app/`. It calls the existing Flask backend through bearer-authenticated `/api/mobile/v1` and `/api/mobile/v2` routes. PostgreSQL stores identity, relationships, controls, quizzes, content state, activity, and audit records. Cloudflare R2 stores private media. Modal runs heavy face/image/video inference through the existing durable media job path.

No parent control or safety decision is trusted from the client. Flask remains authoritative for role access, parent ownership, onboarding gates, friendship approval, screen time, quiet hours, feature/category controls, moderation, and publication.

## Role flows

### Child

1. A restored session is checked against the live user record.
2. Face enrollment/login and quiz requirements gate entry.
3. Feed, reels, stories, discover, posting, and messaging re-check server controls.
4. Social interaction requires an active, two-parent-approved relationship.
5. The client can render a restriction, but it cannot grant access.

### Parent

1. Registration requires email OTP; Android device auth (biometric/PIN) gates Parent Mode.
2. Parent routes require an ACTIVE Parent role and an approved parent-child mapping.
3. Dashboard summaries expose only owned children.
4. Controls, screen time, follow approvals, activity, and notifications are persisted by the backend.
5. REVIEW previews use short-lived signed delivery or the authenticated media proxy. BLOCKED content is never delivered.

### Admin

1. Admin routes require a live ACTIVE Admin account.
2. The native queue is bounded to open REVIEW events.
3. Detail previews pass through the same authorized media delivery boundary.
4. APPROVE/BLOCK uses the shared authoritative moderation transition; ESCALATE appends review history and leaves the event open.
5. Account and moderation actions write the dedicated admin audit log.

## Media upload and moderation state machine

```text
mobile session request
  -> private R2 quarantine upload
  -> upload completion verifies object size and MIME
  -> durable processing dispatch / lease
  -> sanitize + moderate
       ALLOWED -> promote sanitized bytes -> eligible feeds/profile
       REVIEW  -> remain private -> Parent/Admin authorized review
       BLOCKED -> delete/invalidate quarantine -> never public
       retryable failure -> bounded redrive/reaper
```

The client never promotes or publishes media. A review approval calls the backend transition that sanitizes/promotes the bytes and updates publication state while failing closed on processing errors.

## Data and secret boundaries

- Expo receives only `EXPO_PUBLIC_API_BASE_URL`.
- PostgreSQL, R2, mail, Modal, and signing credentials remain backend-only.
- The mobile API never returns password hashes, bearer tokens from other sessions, face embeddings, storage credentials, or raw internal model prompts.
- Tests that mutate PostgreSQL must use a verified disposable database.

## Performance boundaries

- Feed/reels/chat and Parent/Admin queues are paginated or hard-bounded and rendered with virtualized lists where volume warrants it.
- Only one reel/video is active at a time.
- Processing polling is foreground-only, backoff-bounded, and stops at terminal states or its attempt budget.
- Parent/Admin data refreshes on navigation, invalidation, reconnect, or user pull-to-refresh; it does not continuously poll.
- Routine health checks do not call heavy AI inference.
