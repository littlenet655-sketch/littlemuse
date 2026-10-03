# LittleNet V5 Live Preflight Report

**Date**: 2026-10-03
**Branch**: release-hardening-final-v5
**HEAD**: 3aa105df21c9e50bb1d924fa0e25b1357dc1aaee

---

## PREFLIGHT CHECKS

| Check | Status |
|-------|--------|
| Python source parses | PASS |
| PREFLIGHT (audit_all.py) | PASS |
| ROUTES 128 ERRORS 0 | PASS |
| SCOPE_CHECK 33/33 | PASS |
| REACT NATIVE SOURCE | PASS |
| DYNAMIC SQL 2/2 APPROVED | PASS |

---

## Live Infrastructure Read-Only Probe

### Neon PostgreSQL (Production)

| Metric | Value |
|--------|-------|
| Postgres version | 18.6 (aarch64-unknown-linux-gnu) |
| pgvector | NOT INSTALLED (items_embeddings table also absent; recommendation system falls back gracefully) |
| Applied migrations | 42 |
| moderation_signal_cache | EXISTS |
| media_delete_outbox | EXISTS |
| Posts PROCESSING | 74 |
| Posts FAILED | 38 |
| Posts ALLOWED | 364 |
| Posts BLOCKED | 57 |
| Posts REVIEW | 4 |
| Upload sessions EXPIRED | 18 |
| Upload sessions CONSUMED | 74 |
| Upload sessions PENDING (all expired) | 160 |
| Open moderation_events | 22 |

**Notes**:
- 38 FAILED + 74 PROCESSING posts are historical data from pre-V4; the reconciliation tool (`tools/reconcile_operator_v5.py`) classifies and plans recovery
- 160 PENDING upload_sessions are all past their `expires_at`; dry-run plans MARK_EXPIRED_UPLOAD_SESSION for each
- Neon is at 42 migrations; local test DB (PG16) has all 44 applied (2 hardening migrations added in V5 are backend-only, not yet deployed to prod)

### Cloudflare R2 (Production)

| Metric | Value |
|--------|-------|
| Bucket | littlenet-media |
| HeadBucket | ACCESSIBLE (authenticated) |
| posts/ prefix | 5 objects |
| reels/ prefix | 3 objects |
| stories/ prefix | 1 object |
| curated/ prefix | 50+ objects |
| quarantine/ prefix | 4 objects |

### Modal (netlittle2 workspace)

| App | State |
|-----|-------|
| littlemuse-web (ap-5rJWY5aS85NmgMJ4Ps1tBb) | deployed |
| littlemuse-ai (ap-ypBjvuw0ZXZYKDAf6hKaJV) | deployed |
| littlenet-web (ap-0VTAOxUKeztjE9H37tNxx9) | deployed |
| littlenet-ai (ap-Blh94Ec2SPFf3y4nYHxsJz) | deployed |

| Volume | Age |
|--------|-----|
| littlemuse-uploads | 2026-09-23 |
| littlenet-uploads | 2026-09-12 |
| littlenet-model-cache | 2026-09-12 |

### Resend Email

Not configured in dev/local environment. Production RESEND_API_KEY required for live parent OTP delivery. The `validate_resend_production()` function and preflight check for RESEND_API_KEY, RESEND_FROM_EMAIL, RESEND_WEBHOOK_SECRET are all in place and tested.

---

## Actions Required Before Production Deployment

1. Apply migrations 43 and 44 to production Neon:
   - `20261002120000_outbox_trigger_attempts_reset.sql`
   - `20261003100000_password_reset_security_hardening.sql`
2. Configure RESEND_API_KEY, RESEND_FROM_EMAIL, RESEND_WEBHOOK_SECRET in Modal secrets
3. Run `tools/reconcile_operator_v5.py --apply` against production to recover stale PROCESSING posts and expire stale upload sessions
4. Confirm pgvector installation for Neon (optional: items_embeddings table + recommendation signals)

**LIVE PREFLIGHT STATUS**: READ-ONLY PROBE COMPLETE, NO MUTATIONS MADE
