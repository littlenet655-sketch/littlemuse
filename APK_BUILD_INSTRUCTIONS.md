# APK build (derived from this repository; NOT executed in the sandbox)

Prerequisites: Node 20+, an Expo account with EAS CLI access, and a public HTTPS backend URL.

```bash
cd mobile_app
npm ci
npm run typecheck && npm test
export EXPO_PUBLIC_API_BASE_URL="https://<your-backend>.modal.run"   # must be public HTTPS; no localhost/LAN
npx expo-doctor
npx eas-cli login
npx eas-cli build --platform android --profile preview
```
The `preview` profile (eas.json) uses internal distribution with `buildType: apk`, so the artifact is an installable `.apk`.
Package `com.littlenet.app`, version 1.0.2 (versionCode 3; `appVersionSource: remote`).
Set `EXPO_PUBLIC_API_BASE_URL` in the EAS environment for the build, or the app will report it is not pointed at a backend.
