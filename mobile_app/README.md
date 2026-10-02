# LittleNet Mobile

This directory is the only mobile application root.

```bash
cp .env.example .env
npm install
npm run typecheck
npm test
npm run export:android
npx expo install --check
npm run start
```

Use `EXPO_PUBLIC_API_BASE_URL` for the public LittleNet backend URL. Never copy backend secrets into this directory.

The app contains role-aware Child, Parent, and Admin navigation. Keep API paths centralized in `src/api/client.ts`; image/video creation must use the v2 direct-upload and background-processing contracts.

## Build profiles

- `development`: local development client.
- `preview`: internal Android APK through EAS.
- `production`: store-oriented Android build with an auto-incremented build number.

EAS requires the repository owner/project identifiers and `EXPO_TOKEN` in the authorized build environment. The public backend URL is supplied as `EXPO_PUBLIC_API_BASE_URL`; no backend secrets belong in the Expo environment.
