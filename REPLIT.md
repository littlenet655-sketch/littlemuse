# Replit Handoff

Replit should continue from the existing architecture, not redesign it.

## Work here
`mobile_app/` is the only mobile frontend. Build screens, navigation and interactions there.

## Preserve these systems
Do not rewrite `mobile/`, `auth/`, `child/`, `parent/`, `admin/`, `quiz/`, `safety/`, `services/`, `database/`, `modal_ai.py` or `modal_web.py` unless fixing a demonstrated backend defect.

## API preference
Use v2 for feed/reels/discover and all new media upload/processing flows. Use v1 only where no v2 endpoint exists.

## Media posting
Never send a large image/video through the synchronous AI request path from the phone. Request an upload session, upload directly to R2 quarantine, complete the session, then show processing state while the background worker moderates it.

## Secrets
Mobile code may receive `EXPO_PUBLIC_API_BASE_URL`. Backend secrets stay backend-only.

## Before changing backend code
Search for an existing service/route first. LittleNet already has async jobs, R2 storage, moderation, parent controls, usage limits, face flows, messaging and mobile APIs.

## Required checks
```bash
cd mobile_app
npm install
npm run typecheck
npm run export:android
cd ..
python tools/audit_all.py
```
