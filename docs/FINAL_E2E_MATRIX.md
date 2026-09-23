# LittleNet Final E2E Matrix

_Last re-audited: 22 September 2026_

Status values:

- **PASS** — the named journey was executed end-to-end with current evidence.
- **FAIL** — it was executed and failed.
- **UNVERIFIED** — implementation/tests may exist, but the complete current-release journey has not been executed.

Automated unit/integration tests are recorded separately from live/device journey status.

## Repository validation

| Validation | State |
|---|---|
| PostgreSQL/pgvector bootstrap + migrations | AUTOMATED_TESTED |
| Backend regression | AUTOMATED_TESTED on current main |
| Python security | AUTOMATED_TESTED on current main |
| Gitleaks | AUTOMATED_TESTED on current main |
| Role PostgreSQL E2E | AUTOMATED_TESTED |
| React Native typecheck/tests/export | AUTOMATED_TESTED on current main |
| Expo dependency check | AUTOMATED_TESTED on current main |
| R2 private media contracts | AUTOMATED_TESTED |
| Recommendation/feed contracts | AUTOMATED_TESTED |
| Reel player/JIT credential contracts | AUTOMATED_TESTED on current main |
| Cloudflare Stream private adapter | implemented in current re-audit branch; LIVE UNVERIFIED |

## Monday critical journey

| Journey | Current release status | Repository evidence | Required final evidence |
|---|---|---|---|
| Fresh APK install/launch | UNVERIFIED | EAS workflow now waits for/downloads preview APK | build + Android install |
| Parent registration | UNVERIFIED CURRENT DEPLOY | API/contracts implemented | unique clean live account |
| Resend OTP delivered + verified | UNVERIFIED CURRENT DEPLOY | secure OTP + delivery lifecycle implemented | live webhook + real inbox |
| Parent creates child account | UNVERIFIED LIVE/DEVICE | ownership/creation contracts | current deployment + APK |
| Child password login | UNVERIFIED LIVE/DEVICE | authentication contracts | current deployment + APK |
| Quiz gate | UNVERIFIED DEVICE | backend/mobile contracts | current APK |
| Feed renders | UNVERIFIED DEVICE | feed/session/recommendation tests | current APK |
| Reels render/play | UNVERIFIED DEVICE | bounded player/JIT/buffer tests | physical decoder/network |
| Safe image upload -> ALLOW | UNVERIFIED LIVE/DEVICE | upload concurrency/state tests | R2 + AI + APK |
| Safe Reel upload -> ALLOW/play | UNVERIFIED LIVE/DEVICE | media processing/video tests | R2 + AI + APK |
| Child B sees Child A ALLOW content | UNVERIFIED DEVICE | publication invalidation/feed tests | two eligible children |
| REVIEW remains private | UNVERIFIED DEVICE | fail-closed policy tests | controlled device journey |
| BLOCK remains private | UNVERIFIED DEVICE | fail-closed policy tests | controlled device journey |

## Supporting journeys

| Journey | Current release status |
|---|---|
| Stories view persistence | AUTOMATED_TESTED; DEVICE UNVERIFIED |
| For You/Friends/Learn modes | AUTOMATED_TESTED; DEVICE UNVERIFIED |
| Like/save/comments | AUTOMATED_TESTED; DEVICE UNVERIFIED |
| Follow/privacy/block/mute | AUTOMATED_TESTED; DEVICE UNVERIFIED |
| Text/shared-post chat | AUTOMATED_TESTED; DEVICE UNVERIFIED |
| Parent controls | AUTOMATED_TESTED; DEVICE UNVERIFIED |
| Parent safety review | AUTOMATED_TESTED; DEVICE UNVERIFIED |
| Admin moderation | AUTOMATED_TESTED |
| Push registration/payload | AUTOMATED_TESTED; PHYSICAL DELIVERY UNVERIFIED |
| Adaptive HLS | SOURCE IMPLEMENTED; LIVE/DEVICE UNVERIFIED |

## External-service gate

Before the final device run require:

- exact current release commit deployed to the canonical LittleMuse Modal apps;
- strict Modal preflight PASS;
- Neon migrations current;
- R2 private storage health PASS;
- AI shared-secret/protected endpoint PASS;
- Resend domain/sender PASS;
- enabled Resend webhook with signing secret mounted;
- EAS preview APK artifact built from the exact release commit;
- optional Cloudflare Stream preflight PASS if adaptive delivery is enabled.

## Submission decision

Do not convert an **UNVERIFIED** device/live row into PASS from source presence alone. The current repository is a production candidate; the physical parent -> child -> upload -> second-child path remains the final release truth.
