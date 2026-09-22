# LittleNet — Remaining External Verification

_Updated for the final release close-out branch on 2026-09-22._

The previously listed native product gaps have been closed in source: conversation pagination, like/comment/friend notifications, bearer-native post/story deletion, story viewer normalization, Parent viewing insights, private Parent Review video playback, role entry, six-cell OTP, Story composer routing, and production OCR wiring.

## External configuration still required

1. **Production credentials/secrets** — Neon/PostgreSQL, Modal, R2, Resend, AI shared secret, Expo/EAS and push credentials must be supplied outside source control.
2. **Live deployment preflight** — run the manual deployment workflow after secrets are configured; it validates database migrations, R2, email, AI model staging, readiness endpoints, and the public mobile API.
3. **Current-head APK build** — build the final merged commit through EAS/local Android packaging after the account-owned Expo identifiers are configured.
4. **Physical-device acceptance** — run the documented Android device flow for camera/liveness, device-auth Parent Mode, push delivery, Feed/Reels scrolling, video buffering, and the full Parent → Child → moderation → social/chat journey.

These are deployment/device verification steps, not missing source-code features.

## Intentional product constraints

- Children do not self-register; a verified Parent creates child accounts.
- New child accounts are limited to ages **6–16**. Existing older test/demo records remain readable for migration compatibility.
- Parent registration ends with email OTP; Parent Mode is protected locally by Android system authentication. Parent face/liveness is not part of the active mobile registration flow.
- Standalone audio/voice messages are disabled.
- Media remains private until moderation reaches ALLOW; REVIEW/BLOCK content is not public.
- OCR is enabled in the production Modal AI image runtime and fails closed as partial evidence if unavailable.
- Cloudflare Stream remains optional; private R2 delivery is the supported fallback.
