# LittleNet Video & Recommendation Production Audit

**Re-audit date:** 20 September 2026

## Video implementation

### Mobile player

Current React Native Reel playback includes:

- exactly one active Reel;
- bounded adjacent loading;
- native `expo-video` player;
- short-form buffer policy;
- poster until actual first-frame render;
- debounced buffering UI;
- background/focus pause;
- JIT playback credentials for social Reels;
- pre-expiry credential refresh using the refreshed expiry value;
- bounded retry;
- impression batching;
- corrected completion/replay and initial-load/rebuffer telemetry semantics.

Physical TTFF/rebuffer numbers remain **UNVERIFIED** until captured from a current Android APK.

### Private R2 fallback

The sanitized private R2 MP4 remains the always-available fallback. Raw quarantine media is not used as public playback.

### Cloudflare Stream adaptive path

The repository now contains a real opt-in provider implementation:

1. LittleNet first moderates/sanitizes the video.
2. Backend provisions a one-time Stream direct-upload URL with `requireSignedURLs=true`.
3. The sanitized MP4 is uploaded to that URL.
4. The real Cloudflare UID and processing state are stored in `media_assets`.
5. Playback polls provider readiness when needed.
6. READY assets receive a short-lived signed token.
7. Mobile receives the signed HLS manifest URL.
8. If Stream is not ready/configured/reachable, playback falls back to private R2 MP4.

For higher token volume, the provider supports a Stream signing key stored only in backend secrets; the token API remains a lower-volume fallback.

**Live Cloudflare Stream ingestion/HLS remains UNVERIFIED until credentials are configured and a real asset is exercised.**

## Recommendation implementation

The active v2 feed/Reels session path applies:

```text
hard eligibility
 -> social + curated candidate retrieval
 -> feedback/profile ranking
 -> diversity rerank
 -> stable feed session
 -> page hydration
```

Safety, parent controls, age, block/mute and publication state remain before ranking. Mobile batches watch/completion/replay/like/save impression signals.

The current system is a safe hybrid ranking baseline; it is not represented as Instagram/YouTube proprietary ranking.

## Scale changes

- Social Reel list pages no longer mint a video playback credential for every item. Playback is requested only by the nearby player window.
- Feed sessions prevent full reranking on every pagination request.
- Remote GPU ranking remains opt-in so feed requests do not wake Modal T4 by default.
- k6 requires an explicit staging URL/token and has an optional 10 -> 1000 VU profile.
- The Python benchmark is explicitly labelled an in-process regression profiler and exposes its actual worker-thread cap.

## Performance evidence

| Measurement | Current evidence |
|---|---|
| Backend/RN regression | automated CI evidence |
| Android TTFF | UNVERIFIED |
| Android rebuffer ratio | UNVERIFIED |
| Adaptive HLS/ABR | source implemented; LIVE UNVERIFIED |
| 10/50/100/250/500/1000 VU staging | UNVERIFIED |
| Production DB pool under load | UNVERIFIED |

No exact throughput/latency number should be quoted until raw output is retained with environment and commit SHA.
