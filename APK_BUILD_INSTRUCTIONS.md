# APK build instructions

Derived from this repository. **No EAS cloud build was run from this exact
final source.** Local Expo Doctor (21/21) and `npm run export:android` passed
on technical baseline `f4be262`.

## Identity

| Item | Value |
|---|---|
| Product | LittleNet |
| Android package | `com.littlenet.app` |
| version | `1.0.2` |
| versionCode | `3` |
| EAS preview | internal, `android.buildType: apk` |
| Cleartext | `usesCleartextTraffic=false` (`mobile_app/plugins/withCleartextDisabled.js`) |

## Local gates (already proven on `f4be262`)

```powershell
cd mobile_app
npm ci
npm run typecheck
npm test
npx expo-doctor
$env:EXPO_PUBLIC_API_BASE_URL = "https://your-public-backend.example"
npm run export:android
```

## EAS preview APK (external — not executed here)

Production/preview builds must use a **public HTTPS** backend. Localhost,
private IPs, and cleartext HTTP are rejected by the production API URL check.

```powershell
cd mobile_app
$env:EXPO_PUBLIC_API_BASE_URL = "https://your-public-backend.example"
npx eas-cli login
npx eas-cli build --platform android --profile preview
```

Set `EXPO_PUBLIC_API_BASE_URL` in the EAS environment for the build, or the
app will report it is not pointed at a backend. Do not put database, R2,
Resend, Modal, or Flask secrets into Expo.

After the cloud build: install the APK on a physical Android device and run
`PHYSICAL_DEVICE_CHECKLIST.md`.
