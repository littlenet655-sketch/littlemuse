# LittleNet Academic Viva Presentation Guide

**Major Project Phase II (2025–2026)**  
**Department of Computer Science & Engineering (Data Science)**  
**Project:** LittleNet — Child-Centric Social Platform with AI-Based Content Filtering

## 1. One-line explanation

> LittleNet is a supervised child-focused social and learning platform where server-side moderation, approved relationships, Parent Mode controls, Child Face Login/liveness, and Admin/Moderator review work together to reduce unsafe content and interactions.

## 2. Screen → route → implementation map

| Feature | Main route / area | Main implementation | What to explain |
| --- | --- | --- | --- |
| Kids dashboard/feed | `/child/dashboard/`, `/feed/` | `child/routes.py`, `services/social.py` | Safe/eligible feed, controls and quiz gates |
| Create post | `/child/upload-post/` | `uploadPost/routes.py` | Image/video/text moderation before publication |
| Stories | story routes/viewer | `uploadPost/routes.py`, Stories templates/JS | Only allowed content is normally visible |
| Reels/Clips | `/reels/` | `uploadPost/routes.py` | Short-video feed + sampled visual moderation |
| Discover | `/discover/` | `child/service.py` / social rules | Restricted discovery rather than global strangers |
| Messages | `/messages/`, `/chat/<id>/` | `childMessage/routes.py`, `childMessage/service.py` | Current approved relationship is rechecked |
| Parent dashboard | `/parent/dashboard/` | `parent/routes.py` | Usage, presence, controls, safety and learning summaries |
| Parent safety review | `/parent/safety/` | `parent/routes.py`, `safety/moderation_service.py` | Explicit review of `REVIEW` decisions |
| Screen time | Parent time-limit/control routes | `services/usage.py` | Server-side usage sessions and lock state |
| Face Login/liveness | face-login/verification flows | `safety/face_service.py`, auth routes, MediaPipe assets | Face/liveness evidence before protected activation/login behavior |
| Learning/quizzes | `/learning/` and quiz routes | `quiz/` | Age-group quizzes/challenges and learning features |
| Admin/Moderator | `/admin/`, `/admin/moderation/` | `admin/routes.py` | Reports, moderation events, forced block and audit logs |
| Android app | `mobile_app/` | React Native + Expo + TypeScript | Native role-aware UI using the same HTTPS Flask backend |

## 3. Moderation scope you must state correctly

### Active in the current build

- image moderation
- sampled video-frame moderation
- text/caption/comment/message moderation
- PII/contact-sharing protection
- contextual chat safety with fail-safe fallback
- Parent Mode `REVIEW`
- Admin/Moderator auditing

### Intentionally not active

- standalone audio/voice uploads
- story music/audio uploads
- speech-to-text moderation

Video audio is stripped before persistence. Older Phase-I material may mention speech transcription, but it is not part of the locked final college demo.

## 4. Five-minute demo flow

### Step 1 — Kids Mode (about 1 minute)

1. Open the configured LittleNet deployment or the Android APK.
2. Log in with your prepared demo CHILD account. Do not hard-code or publish the credentials in project documents.
3. Show:
   - feed
   - Stories/Reels entry points
   - Discover restrictions
   - profile/learning access

Explain that authorization and safety decisions live on the Flask/PostgreSQL backend, so native screens cannot bypass server rules.

### Step 2 — Content moderation (about 1 minute)

Use pre-tested demo samples:

1. Safe image/text -> explain `ALLOW`.
2. Unsafe/toxic/contact-sharing content -> explain `BLOCK` or the corresponding safety result.
3. Ambiguous sample -> explain `REVIEW` and Parent Mode visibility.

Do not use untested extreme content in the live viva. Use controlled samples that already worked in rehearsal.

### Step 3 — Parent Mode (about 1 minute)

Log in with a prepared PARENT demo account and show:

- child dashboard summary
- safety review
- daily screen-time limit
- quiet hours
- feature/category controls
- notifications/usage information

Explain that parent access requires an ACTIVE parent account plus an approved parent-child mapping.

### Step 4 — Messaging authorization (about 45 seconds)

1. Show messaging between approved child accounts.
2. Explain that LittleNet checks the relationship even when a conversation already exists.
3. If you have prepared the demo data, revoke/block the relationship and show that the old conversation cannot be reused for continued access.

### Step 5 — Face/liveness + Admin + APK (about 1 minute)

- Explain that parent activation uses email OTP; Parent Mode is protected by Android system authentication, while child Face Login uses live-camera challenge evidence.
- Show the Admin/Moderator screen with moderation/audit evidence.
- Show the Android APK and explain that it was built from the same source and points to the HTTPS backend.

## 5. Core viva questions and strong answers

### Q1. Why is LittleNet needed?

Children use social-style platforms but ordinary platforms are not designed around guardian supervision. LittleNet combines social features with parent-controlled relationships, safety moderation, screen-time controls, learning features and auditable review.

### Q2. Why do you use multiple safety signals?

Different harms appear differently. Visual content can contain adult imagery or dangerous objects, while text can contain toxicity, grooming/secrecy patterns or contact-sharing attempts. LittleNet combines the relevant evidence before making one policy decision.

### Q3. What are `ALLOW`, `REVIEW` and `BLOCK`?

- `ALLOW`: normal visibility is permitted.
- `REVIEW`: content is held for Parent Mode review.
- `BLOCK`: a hard safety rule rejects or hides the item.

This gives a middle state for uncertain content instead of forcing every decision into safe/unsafe only.

### Q4. What does “fail closed” mean here?

If required safety evidence is completely unavailable or malformed, LittleNet does not silently convert that into a safe score. Total safety failures use a hard safe outcome; partial failures route to review. This is important because a broken safety service must not become a bypass.

### Q5. How did you fix the AI-response safety issue?

The normalization layer now validates the signal envelope and score types/ranges. An empty or malformed result is marked as a safety failure instead of becoming zeros. Regression tests cover this behavior.

### Q6. How does video moderation work?

The current college implementation samples frames across a short uploaded video, runs visual safety checks and aggregates the results. If a sampled frame fails to be evaluated, that failure is preserved and can force review. It is sampling-based and does not claim perfect inspection of every video frame.

### Q7. Does the current project moderate audio using speech-to-text?

No. Standalone audio/voice and story-music uploads are intentionally disabled in the locked current build, and video audio is stripped before persistence. Earlier designs mentioned speech transcription, but we removed that dependency to keep the final project stable and demonstrable.

### Q8. How do you prevent proxy/unauthorized child messaging?

Messaging requires an approved current relationship. LittleNet rechecks that relationship before returning or creating a conversation and before reading messages. Therefore an old conversation ID cannot be used after the connection is revoked or blocked.

### Q9. How does Parent Mode authorization work?

Sensitive child access uses a canonical ownership check that requires an approved parent-child mapping and an ACTIVE parent account. Private media access uses the same ownership rule.

### Q10. How is screen time enforced?

The backend stores usage sessions and calculates current daily usage. Missing/stale sessions are recreated before the lock decision. Time is accumulated in seconds before conversion to display minutes so repeated short sessions are not lost. Daily limits and quiet hours are enforced server-side.

### Q11. What is special about the face/liveness hardening?

The system never uses image dimensions as identity proof. Child Face Login requires live-camera challenge evidence and a replay-resistant server nonce. Parent activation is email-OTP based and Parent Mode uses Android system authentication; no parent age-estimation/selfie gate is part of the final flow.

### Q12. Why Flask + PostgreSQL?

Flask keeps the college backend understandable and modular, while PostgreSQL gives reliable persistent relational state for users, parent-child mappings, social relationships, posts, messages, moderation events, usage logs and learning data.

### Q13. Why React Native instead of an Android WebView?

React Native provides a real native mobile navigation, camera, secure session, list and media experience while reusing the tested Flask business rules through JSON APIs. This keeps one server authority without wrapping web pages as the application.

### Q14. What proof do you have that the project is working?

Use only the counts and artifacts recorded for the current commit in `docs/FINAL_E2E_MATRIX.md`. Typechecking or source presence is not device E2E evidence, and an Expo Android export is not an installed APK.

### Q15. Is the latest commit already deployed to Modal?

Not yet. The automated deploy workflow is ready, but the repository currently has no `MODAL_TOKEN_ID` or `MODAL_TOKEN_SECRET` GitHub Actions secrets. The latest deployment run stopped before any deploy command. This is an external credential configuration step, not an application test failure.

## 6. Architecture answer in simple words

> The child, parent, admin dashboard and Android app all talk to the Flask backend. Flask checks the user role, parent-child/child-child relationships, Parent Mode controls and moderation policy. PostgreSQL stores the system state. Safety services produce evidence, and the policy converts that evidence into ALLOW, REVIEW or BLOCK. This means the frontend cannot simply bypass the important safety decisions.

## 7. What not to claim in the viva

Do not say:

- “LittleNet is 100% production ready.”
- “Every video frame is scanned.”
- “Speech transcription is active.”
- “The latest commit is already live on Modal” until the deployment workflow passes.
- “We support millions of users.”
- “AI is always correct.”
- “Aadhaar verification is implemented” unless you have separately added and verified such a real feature.

Prefer:

- “This is a verified college submission candidate.”
- “We use sampled video-frame moderation.”
- “Uncertain/partial failures go to parent review.”
- “The current source/export is CI-verified; I only call an APK verified after the current EAS build and physical smoke pass.”
- “The final hosted redeploy needs the Modal GitHub Actions credentials restored.”

## 8. Current evidence snapshot

Baseline commit: `304f35052e033726b00e9b7e229141b42d32fd6c`

Current APK artifact:

- name: `littlenet-current-main-apk` after the EAS release workflow completes
- package: `com.littlenet.app`
- digest: `sha256:f38cc4e79a14bcf7de405e2d735a5869f11716cf6aab853809ebbfb2c0c43f65`

Use the regenerated submission ZIP after the documentation-consistency fix rather than an older package that still contains outdated speech/audio claims.
