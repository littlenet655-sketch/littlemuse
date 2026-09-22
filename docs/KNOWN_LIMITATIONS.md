# LittleNet Known Limitations

_Last re-audited: 22 September 2026_

This file records only limitations that are still real on the current React Native/Flask architecture. Historical audit notes are not release evidence.

## Requires live configuration or physical-device evidence

- **Fresh Android APK install:** the repository can build/export Android and the EAS workflow now waits for a current-HEAD preview APK, but a successful physical install/launch still has to be recorded.
- **Current authentication on device:** parent email-OTP and Android biometric/PIN Parent Mode gating, plus child password login and quiz gating, are implemented; the complete current APK journey still requires physical-device evidence.
- **Cross-user publication:** publication invalidation and feed eligibility are tested in source, but Child A upload -> ALLOW -> Child B visibility still needs a two-device/two-account run.
- **Physical Reel playback:** one-active-player logic, buffering policy, JIT playback credentials and telemetry are implemented; TTFF/rebuffer/background-resume claims still require current-device measurements.
- **Push delivery:** Expo push integration is implemented, but physical device-token delivery remains unverified.
- **Resend delivery webhook:** backend verification and delivery-state handling are implemented. The Resend account must have an enabled webhook pointed at `/webhooks/resend`, and the webhook signing secret must be present in the Modal email secret.
- **Adaptive Cloudflare Stream:** the provider now supports private direct upload, processing-state polling, signed HLS and R2 fallback, but it remains opt-in and must not be enabled until real Cloudflare Stream credentials/subdomain are configured and live ingestion/playback is verified.

## Moderation evidence

The fail-closed moderation path is implemented. Do not claim a production accuracy percentage until the benchmark protocol is run on a labelled held-out dataset and the evidence is retained.

## Load and scale evidence

The repository contains an in-process regression profiler and a staging-only k6 script. Neither is evidence of Instagram/YouTube-scale capacity. Production-capacity claims require a controlled staging deployment, real network load, raw k6 output, database connection measurements and API error/latency results tied to a commit.

## Features intentionally outside the locked Monday path

Advanced story/reel editing, unrestricted user-generated audio, group chat, and a full media-message product remain outside the Monday demo claim unless separately verified.

## Implemented items that are no longer limitations

The following older limitations are now implemented in source and automated tests:

- story view persistence / seen state;
- server-side For You / Friends / Learn feed modes;
- Reel impression batching;
- signed playback TTL consistency and refresh;
- production OTP dev-code lockout;
- Resend accepted/delivered/bounced/suppressed state separation;
- pgvector-capable CI bootstrap;
- push payload privacy filtering;
- stable feed sessions with recommendation ranking;
- private R2 sanitized-MP4 Reel fallback.
