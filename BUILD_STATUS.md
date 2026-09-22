# LittleNet Build Status

_Release close-out refreshed: 2026-09-22._

## Repository state

- Python/Flask backend is the server authority.
- React Native / Expo / TypeScript in `mobile_app/` is the sole mobile client.
- PostgreSQL/Neon is the authoritative relational store.
- Private R2 quarantine + asynchronous moderation is the required media publication flow.
- Modal hosts scale-to-zero web/CPU moderation and the heavy AI service.
- The trained image V2/V3 checkpoints and 13-label trained text classifier are Git-LFS managed and protected by exact size/SHA release gates.
- Bounded image OCR, YOLO dangerous-object detection, text/PII moderation, scene-aware video sampling and fail-closed ALLOW/REVIEW/BLOCK policy are wired into the safety pipeline.
- Parent-created child accounts, child face challenge, safety quiz, two-parent relationship approval, screen time, controls, Parent safety review, viewing insights, admin moderation, Feed/Reels/Stories and chat are implemented.
- Native post/story deletion uses the server safe-delete/outbox pipeline.
- Conversation lists and chats are paginated.
- Release packaging rejects missing/LFS-pointer/corrupt trained models.

## Required validation gates

- `python -m pytest tests/ -q`
- `python tools/audit_all.py`
- `python tools/audit_dynamic_sql.py`
- Gitleaks secret scan
- Python `pip-audit` + Bandit
- `cd mobile_app && npm ci && npm audit --omit=dev --audit-level=high`
- `npm run typecheck`
- `npm test`
- `npm run export:android`
- `npx expo install --check`
- release ZIP package + verification

## Deployment boundary

Cloud credentials, production API keys, live Modal/R2/Neon/Resend validation, final EAS APK generation, push delivery and physical-device acceptance are external release steps. They are deliberately not hard-coded into this repository.
