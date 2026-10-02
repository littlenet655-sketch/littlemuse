# LittleNet Remaining Work

_Last re-audited: 20 September 2026_

The old Agent A/B/C/D handoff list is retired. Those branches are behind current `main` and have no commits that should be merged wholesale into the React Native production line.

## Repository work completed

- Parent registration, OTP verification, guardian verification contracts.
- Child creation, face enrollment/login gates and quiz gate.
- Private R2 direct-upload -> moderation -> publication state machine.
- Image/Reel processing, private signed media delivery and R2 fallback.
- Reel player lifecycle, bounded adjacent loading, buffer policy, credential refresh and impression batching.
- Story view persistence and owner-viewer APIs.
- Server feed modes and recommendation ranker wiring.
- Parent/Admin authorization and review flows.
- Production OTP secrecy and Resend delivery-state webhook receiver.
- pgvector-capable database CI and dbmate migration validation.
- Android TypeScript/test/export pipeline.
- Security/secret scanning.
- Optional private Cloudflare Stream provider with R2 fallback.
- Current-HEAD EAS preview-APK workflow that waits for and retains the build artifact.

## Remaining work that cannot be honestly completed by source edits alone

1. Configure the live Resend webhook and its signing secret in Modal, then prove DELIVERED and controlled failure events.
2. Deploy current main to Modal and run strict preflight against live Neon/R2/Resend/AI.
3. Trigger the current EAS APK workflow with the real Expo credentials.
4. Install that APK on a physical Android phone.
5. Execute guardian live-face and child face enrollment/login on the device.
6. Upload a safe image and Reel, wait for ALLOW, and confirm playback.
7. Verify a second eligible child sees the newly allowed content.
8. Prove REVIEW/BLOCK content never reaches the second child's feed.
9. Verify Expo push delivery on a physical device.
10. If adaptive streaming is desired, configure Cloudflare Stream credentials/signing key, enable it, then prove real HLS/ABR playback before calling it live.
11. Run k6 only against an authorized staging environment and retain raw evidence before making load claims.

## Release rule

A green repository is not the same as a device-verified release. The final classification remains **production candidate** until the live/device gates above have evidence.
