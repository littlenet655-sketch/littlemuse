# LittleNet — Release Identity (PARTIAL RELEASE CANDIDATE)

| Item | Value |
|---|---|
| Source repository | littlenet655-sketch/littlemuse (repo name is a development detail; product is **LittleNet**) |
| Branch | main |
| Upstream HEAD at clone | 7e15e2d — Fix false-positive image blocking in moderation merge |
| Local release commits (not pushed) | e70a0e6, cafb973, 11882c9 |
| Current local HEAD | 11882c9 |
| App name / slug | LittleNet / littlenet |
| Android package | com.littlenet.app |
| App version / versionCode | 1.0.2 / 3 |
| EAS preview profile | internal distribution, `android.buildType: apk` |
| EAS `appVersionSource` | remote |
| API base URL | read from `EXPO_PUBLIC_API_BASE_URL` (mobile_app/src/api/client.ts); not hardcoded. Historical value to verify at build time: https://netlittle2--littlemuse-web-web.modal.run |
| Cleartext traffic | disabled (`usesCleartextTraffic: false`); client rejects non-HTTPS and private-host URLs in production |

Compatibility: backend and mobile sources were tested together only through local test suites
(see TEST_RESULTS.md). The version actually deployed on Modal and the APK in circulation were **not** inspected
(no network access), so live source/backend/APK alignment is EXTERNAL VERIFICATION REQUIRED.
