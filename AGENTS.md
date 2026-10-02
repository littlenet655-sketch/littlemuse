# LittleNet Agent Contract

## Goal
LittleNet is a child-safe social and learning application. Preserve the working Python backend and build the mobile client in `mobile_app/` only.

## Source of truth
- Mobile: React Native + Expo + TypeScript in `mobile_app/`.
- Backend/API: existing Flask/Python modules. Do not rewrite the backend into another framework.
- Database: PostgreSQL/Neon through the existing `database/` layer.
- AI/moderation: existing `safety/`, `services/`, `modal_ai.py`, and async media worker paths.
- Media: private R2 storage. New mobile image/video posting must use `/api/mobile/v2/uploads/*` and processing status APIs.

## Non-negotiable rules
1. Do not create a second mobile app root.
2. Do not generate a WebView wrapper.
3. Do not move business rules into the client. Parent controls, moderation, screen time, relationship approval and safety remain server-enforced.
4. Do not replace working backend modules unless a concrete bug requires it.
5. Never put backend secrets in Expo. The only expected mobile environment variable is `EXPO_PUBLIC_API_BASE_URL` unless a new public value is explicitly required.
6. Prefer `/api/mobile/v2` where a v2 route exists. Keep v1 only for endpoints that have no v2 equivalent.
7. Direct media upload goes to R2 quarantine, then background moderation, then status polling. Do not reintroduce synchronous upload-through-AI behavior.
8. Keep package identity `com.littlenet.app`.
9. Before finishing a change, run `npm run typecheck` and `npm run export:android` in `mobile_app/`, plus the relevant Python tests for backend changes.

## UI direction
Use the provided LittleNet/Stitch visual references when they exist, with a polished Instagram-familiar layout adapted for children. Reuse a small set of shared primitives and tokens; do not add multiple UI systems.

## Definition of done
A changed user path is wired to the real API, has loading/error/empty states, passes type checking, and does not weaken server-side safety controls.
