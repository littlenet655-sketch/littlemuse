# Cloudflare Stream Integration Status (Backend Audit)

**Date:** 2026-09-21
**Scope:** backend audit only — documenting current state. Nothing was enabled,
no credentials were added, nothing was deployed.

## Verdict: real integration code, disabled by default

`services/video_delivery.py` contains a complete, functional
`CloudflareStreamDeliveryProvider` — this is **not** stub code. It is gated
behind an explicit opt-in flag and currently **disabled** (`CLOUDFLARE_STREAM_ENABLED`
defaults to `"0"`; `.env.example` ships `CLOUDFLARE_STREAM_ENABLED=0`).
`MODAL_DEPLOYMENT.md` explicitly instructs operators to leave it unset/`0`
until real Stream credentials exist. When disabled or misconfigured, every
path fails over to the sanitized private R2 MP4 provider.

Existing tests prove the gating is real, not decorative:
- `tests/test_release_blocker_fixes.py::test_cloudflare_stream_requires_complete_opt_in`
- `tests/test_release_blocker_fixes.py::test_historical_stream_asset_falls_back_to_private_r2`
- `tests/test_video_push_feed_modes.py` (opt-in gating, private direct-upload,
  fallback behavior)

## Checklist

| Item | State |
|---|---|
| Real provider UID | ✅ Yes — provisioned via `POST /direct_upload`; UID persisted as `provider_asset_id`/`playback_id` in `media_assets` |
| Processing state | ✅ Yes — `_status_from_details`: `readyToStream` → `READY`; `status.state == "error"` → `FAILED`; else `ENCODING` |
| READY state | ✅ Yes — playback only served at `READY`; `_refresh_stream_status` re-polls once on playback request |
| Signed playback | ✅ Yes — provisioned with `requireSignedURLs: true`; tokens minted locally via RS256 JWT (`sub`, `kid`, `exp`, `nbf`) when a signing key is configured, otherwise via `POST /{uid}/token` |
| Credential expiry | ⚠️ Partial — playback tokens carry `exp` from the authoritative TTL (60–600 s). The Cloudflare API token itself has no rotation/expiry handling in code; rotation is a manual ops task |
| Retry | ⚠️ Partial — no retry loop around Stream upload/status polling. Any ingest failure falls back to private R2 MP4; orphaned provisioned UIDs are best-effort deleted on failure; idempotency reuses an in-flight `ENCODING`/`READY` UID instead of creating a second billable asset |
| R2 fallback | ✅ Yes — confirmed. `SanitizedMP4DeliveryProvider` (private R2 + signed download URLs) is the default provider, the Stream failure fallback, and the not-yet-`READY` fallback. `resolve_video_playback` also refuses to build HLS URLs from historical placeholder Stream asset IDs |

## How the pieces fit

- `get_video_provider()` returns the Stream provider only when `is_configured()`
  (flag `1` + account ID + API token + subdomain); otherwise R2 MP4.
- `ingest_post_video()` is called from the media worker ALLOW path with the
  **already audio-stripped** local file (`_make_video_derivatives` output), so
  Option A (all published video bytes silent) holds on the Stream path too.
  Files over 190 MB skip Stream and stay on R2 MP4.
- `resolve_video_playback()` enforces per-viewer authorization
  (`is_authorized_viewer`) before any URL is minted; unauthorized viewers get
  `DENIED`, never a signed URL.
- `video_delivery_healthcheck()` reports mode without exposing credentials.

## What's missing before safe enablement

1. Real Cloudflare Stream account credentials (API token, account ID,
   Stream subdomain, signing key pair) provisioned through the secret manager —
   **env var names only, no values, and never in code or chat.**
2. An ops runbook for API-token rotation (no in-code expiry handling).
3. Monitoring/alerting on `media_assets.status` stuck in `ENCODING`.
4. A decision on Stream-side retention/billing for orphaned assets (code does
   best-effort DELETE on ingest failure, but there is no periodic audit).

## Safe enablement steps (env var names only)

1. Add to the server secret store (e.g. the `littlenet-r2` Modal secret):
   `CLOUDFLARE_STREAM_ACCOUNT_ID`, `CLOUDFLARE_STREAM_API_TOKEN`,
   `CLOUDFLARE_STREAM_SUBDOMAIN`, `CLOUDFLARE_STREAM_SIGNING_KEY_ID`,
   `CLOUDFLARE_STREAM_SIGNING_PRIVATE_KEY_B64`; optionally
   `CLOUDFLARE_STREAM_API_TIMEOUT_SECONDS`.
2. Set `CLOUDFLARE_STREAM_ENABLED=1` in the deployment environment only after
   step 1 is verified.
3. Verify with `video_delivery_healthcheck()` (expect `mode: "api_verified"`)
   and a test upload; confirm `media_assets` reaches `READY` and playback
   falls back to R2 MP4 while `ENCODING`.
4. Keep the private R2 sanitized MP4 as the permanent fallback — do not remove
   it; Stream remains an enhancement, not a dependency.

## Non-functional / misleading code

None found. The only Stream-adjacent rows that could mislead are historical
`media_assets` rows with placeholder provider asset IDs from before real
Stream ingestion existed — `resolve_video_playback` explicitly detects these
and serves the sanitized private R2 reference instead of constructing a fake
HLS URL.
