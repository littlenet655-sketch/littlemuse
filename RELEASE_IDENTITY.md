# LittleNet — Release Identity

**CURRENT FINAL RELEASE RESULT** for the local `release-candidate` package.
This file is the product/identity record for this source tree. It does not claim live production verification.

| Item | Value |
|---|---|
| Product | LittleNet |
| Source repository | littlenet655-sketch/littlemuse (development repo name; product is **LittleNet**) |
| Branch | `release-verification-final-v3` |
| Executable baseline (authoritative) | `086017491ff63214aca3b9ed6e4fe27a7e5835ed` |
| Previous verification HEAD | `826e633` (`826e6332e86197abb2dd555d6b363eead50278ff`) — **HISTORICAL, superseded** |
| Final HEAD | this freeze commit (`fix: close final outbox trigger verification gap`) plus the docs-only reconciliation commit |
| Pushed | **No.** These freeze commits have not been pushed. |
| App name / slug | LittleNet / `littlenet` |
| Android package | `com.littlenet.app` |
| Version | `1.0.2` |
| versionCode | `3` |
| EAS preview profile | internal distribution, `android.buildType: apk` |
| EAS `appVersionSource` | remote |
| Cleartext traffic | disabled (`usesCleartextTraffic=false` via `mobile_app/plugins/withCleartextDisabled.js`) |
| Public mobile env | `EXPO_PUBLIC_API_BASE_URL` only |
| Latest dbmate migration | `20261002120000_outbox_trigger_attempts_reset.sql` (migration 43 of 43) |

## Proven local regression (authoritative)

These numbers are the **CURRENT FINAL RELEASE RESULT**.

| Gate | Result |
|---|---|
| Full backend | **898 passed / 2 skipped / 0 failed** (58.24 s) |
| Mobile | **283 passed / 0 failed** |
| TypeScript | passed (`tsc --noEmit`) |
| Expo Doctor | 21/21 passed |
| Android Expo export | passed |
| Migrations from zero | **43/43** |
| PostgreSQL | 16.15 |
| pgvector | 0.8.7 |

## Deployment status

**DEPLOYMENT READY WITH EXTERNAL REQUIREMENTS**

Not fully production verified. See `release_docs/DEPLOYMENT_READINESS.md` and `release_docs/KNOWN_LIMITATIONS.md`.
