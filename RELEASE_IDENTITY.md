# LittleNet — Release Identity

**CURRENT FINAL RELEASE RESULT** for the local `release-candidate` package.
This file is the product/identity record for this source tree. It does not claim live production verification.

| Item | Value |
|---|---|
| Product | LittleNet |
| Source repository | littlenet655-sketch/littlemuse (development repo name; product is **LittleNet**) |
| Branch | `release-candidate` |
| Initial local baseline | `ac9be32` |
| Technical baseline (proven local regression) | `f4be262` (`f4be262d90af724877437c5b06334ff3f01d633d`) |
| Release commits (in order) | `3c13988`, `9afb91f`, `f8b40e1`, `0f425af`, `768b5f7`, `e55a628`, `715a594`, `09466c9`, `f4be262`, then this documentation commit |
| Final HEAD | this documentation commit (`docs: finalize LittleNet release candidate`) |
| Pushed | **No.** Nothing from this candidate has been pushed. |
| App name / slug | LittleNet / `littlenet` |
| Android package | `com.littlenet.app` |
| Version | `1.0.2` |
| versionCode | `3` |
| EAS preview profile | internal distribution, `android.buildType: apk` |
| EAS `appVersionSource` | remote |
| Cleartext traffic | disabled (`usesCleartextTraffic=false` via `mobile_app/plugins/withCleartextDisabled.js`) |
| Public mobile env | `EXPO_PUBLIC_API_BASE_URL` only |

## Proven local regression (authoritative)

These numbers are the **CURRENT FINAL RELEASE RESULT**. They were recorded on the technical baseline `f4be262` and are not reinterpreted here.

| Gate | Result |
|---|---|
| Database-backed focused tests | 31 passed / 0 failed |
| Full backend | **885 passed / 1 skipped / 0 failed** (53.60 s) |
| Skipped | `tests/test_agent_c_notifications_read.py` — requires a non-localhost hostname |
| Mobile | **281 passed / 0 failed** |
| TypeScript | passed |
| Expo Doctor | 21/21 passed |
| Android Expo export | passed |
| Migrations from zero | **42/42** |
| PostgreSQL | 16.15 |
| pgvector | 0.8.7 |

## Deployment status

**DEPLOYMENT READY WITH EXTERNAL REQUIREMENTS**

Not fully production verified. Not blocked solely because external infrastructure, Git LFS model payloads, or device testing remain. See `release_docs/DEPLOYMENT_READINESS.md` and `release_docs/KNOWN_LIMITATIONS.md`.
