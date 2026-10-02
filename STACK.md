# LittleNet Locked Stack

## Mobile
- React Native 0.86.x
- Expo SDK 57
- React 19.2.x
- TypeScript
- App root: `mobile_app/`
- Android package: `com.littlenet.app`
- Mobile configuration: `EXPO_PUBLIC_API_BASE_URL` only for the public backend URL

## Backend
- Python 3.11
- Flask application already present in this repository
- PostgreSQL / Neon
- Cloudflare R2 private media storage
- Modal for AI workloads
- Modal Function.spawn() for production asynchronous media-processing dispatch (QStash retired)

## Safety architecture
- Text/PII checks remain server-side.
- Image/video moderation remains server-side.
- Existing scene-aware frame sampling augments uniform video sampling.
- Parent review and moderator decisions remain auditable server-side state.
- New media uses direct R2 quarantine upload plus asynchronous processing.

## Engineering rules
- One mobile root only: `mobile_app/`.
- No WebView application shell.
- No second backend framework.
- No client-side copy of safety or parent-control authority.
- No backend secrets in mobile environment files.
- Prefer existing APIs/services over new parallel implementations.
