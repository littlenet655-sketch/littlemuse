# LittleNet V5 Historical Data Reconciliation Report

**Date**: 2026-10-03
**Tool**: tools/reconcile_operator_v5.py
**Mode**: DRY-RUN (no mutations to live data)

---

## Summary

| Category | Count |
|----------|-------|
| ACTIVE_VALID (leases active or UPLOADED) | 11 |
| RECOVERABLE (stale lease or failed < max_retries) | 14 |
| EXPIRED (upload sessions past expires_at) | 1 (local test DB) / 160 (production) |
| TERMINAL_HISTORY (ALLOWED, BLOCKED, max retries) | 29 |
| FAILED_OPERATOR_REVIEW (stale lease + max attempts) | 2 |
| OPEN_REVIEW (moderation_events OPEN) | 2 (test) / 22 (prod) |

---

## Processing State Classification

The operator reconciliation tool classifies `posts.processing_status` as:

### ACTIVE_VALID
Posts in UPLOADED or PROCESSING state with a valid unexpired lease (`processing_lease_expires_at > NOW()`). These are in-flight and must not be touched.

### RECOVERABLE
Posts in PROCESSING with a stale lease (`processing_lease_expires_at < NOW()`) but with `processing_attempts < max_processing_attempts`. Planned action: `RELEASE_STALE_LEASE` — reset to UPLOADED with NULL lease so the worker can re-acquire.

Posts in FAILED state with `processing_attempts < max_processing_attempts`. Planned action: `REDIVE_FAILED_POST` — reset to UPLOADED.

### TERMINAL_HISTORY
Posts in ALLOWED or BLOCKED (final states). Posts in FAILED with `attempts >= max_processing_attempts`. These are closed.

### FAILED_OPERATOR_REVIEW
Posts in PROCESSING with a stale lease AND `attempts >= max_processing_attempts`. These require operator review; planned action: `EXPIRE_PROCESSING_TO_FAILED` with an explicit error message.

### OPEN_REVIEW
Posts in REVIEW state (pending parent/operator decision). moderation_events rows with `status = 'OPEN'`. These are legitimate pending reviews — no automated action, human decision required.

---

## Upload Session Classification

All upload_sessions in PENDING state with `expires_at < NOW()` are classified EXPIRED.

Production observation: 160 PENDING sessions are all past their expires_at. The tool plans `MARK_EXPIRED_UPLOAD_SESSION` for each.

Sessions in CONSUMED or CANCELLED are TERMINAL_HISTORY.

---

## Media Reference Classification

The tool scans `posts.media_path`, `posts.source_media_path`, and `posts.poster_path` for:

| Category | Description |
|----------|-------------|
| VALID | R2 path starting with a valid prefix |
| LEGACY_LOCAL_PATH | Paths starting with `uploads/` or containing localhost — pre-V4 local disk paths |
| POSTER_MISSING | VIDEO posts missing poster_path |

### Local Test DB Results
- VALID: 1
- LEGACY_LOCAL_PATH: 25 (historical seed/test data with `uploads/r2/...` relative paths)
- POSTER_MISSING: 5 (VIDEO posts without poster thumbnails)

**Note**: Legacy local paths in the test DB are seed/fixture data from development. In production, posts that were published correctly have R2 absolute URLs. The reconciliation tool flags them for operator awareness but makes no automated decisions about content.

---

## Actions Planned (Dry-Run — Not Applied)

1. **RELEASE_STALE_LEASE**: Reset PROCESSING posts with stale leases (attempts < max) back to UPLOADED
2. **EXPIRE_PROCESSING_TO_FAILED**: Mark PROCESSING posts with stale lease + max attempts reached as FAILED with explicit error
3. **REDIVE_FAILED_POST**: Reset FAILED posts with attempts remaining back to UPLOADED
4. **MARK_EXPIRED_UPLOAD_SESSION**: Mark PENDING upload sessions past expires_at as EXPIRED

### Applying to Production
```bash
python tools/reconcile_operator_v5.py --apply
```

This requires explicit `--apply` flag. All actions are idempotent and transaction-safe. No content is auto-approved.

---

## Safety Guarantees

- No content is automatically published or approved
- OPEN_REVIEW and FAILED_OPERATOR_REVIEW items require human decision
- TERMINAL_HISTORY items are never modified
- Active leases (expires_at > now) are never touched
- No R2 objects are deleted by this tool
