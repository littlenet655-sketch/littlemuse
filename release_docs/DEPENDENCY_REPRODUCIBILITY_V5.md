# LittleNet V5 Dependency Reproducibility Report

**Date**: 2026-10-03
**Branch**: release-hardening-final-v5

---

## Python Dependencies

Managed via pip with pinned versions in `requirements.txt`. All packages installed in `.venv/`.

### Critical Package Analysis: transformers

During V5 hardening, `transformers==5.10.0` was investigated:

**Finding**: `transformers==5.10.0` was yanked on PyPI with the official note:
> "We pushed from a week old main branch and could not make the CI green in time."

**Resolution**: `transformers==5.10.1` was uploaded on 2026-06-03T15:37:00 UTC.
- Not yanked
- Functionally identical interface
- PyPI SHA-256 (wheel): `ccb919ea1b77338b44d0d45d23f7472081906b1bb6ed8e5f5cf4d692d1da03d4`
- Safe to pin to 5.10.1

**Recommendation**: Update `requirements.txt` to pin `transformers==5.10.1` for reproducible builds.

### Other Pinned Dependencies (Key)

| Package | Purpose |
|---------|---------|
| psycopg2-binary | PostgreSQL adapter (PG16 + PG18 compatible, tested) |
| flask | Web framework |
| boto3 | Cloudflare R2 (S3-compatible) client |
| resend / urllib | Parent email delivery |
| modal | Serverless AI deployment |

---

## JavaScript / React Native Dependencies

Managed via npm in `mobile_app/`. `package-lock.json` is committed.

| Package | Version | Purpose |
|---------|---------|---------|
| expo | ~57.0.26 | Expo SDK (doctor: 21/21 PASS) |
| react-native | 0.86 | Core RN |
| @tanstack/react-query | ^5.102.8 | Data fetching |
| @shopify/flash-list | 2.0.2 | Performant lists |

---

## Database Tooling

| Tool | Version | SHA-256 |
|------|---------|---------|
| dbmate | 2.34.1 | b002d5249d53d0c6c482ed761b5a806c6fb9a364fcc5f9db3e8763c1d9e40e1d |

dbmate binary is present at `./dbmate.exe`. Supply chain pin test (`tests/test_supply_chain_pins.py`) verifies every dbmate download script contains the expected SHA-256.

---

## Migration Count

| Environment | Applied Migrations |
|-------------|-------------------|
| Local PG16 (test) | 44 |
| Local PG18 (test) | 44 |
| Production Neon | 42 (2 V5 hardening migrations pending deployment) |

### V5 New Migrations

| # | File | Purpose |
|---|------|---------|
| 43 | 20261002120000_outbox_trigger_attempts_reset.sql | Bounded re-drive for outbox triggers |
| 44 | 20261003100000_password_reset_security_hardening.sql | Opaque tokens, rate limiting, reaper, outbox |

---

## Reproducibility Guarantee

All backend tests pass with `--no-header -q` on a disposable PG16 container (port 5433) and a disposable PG18 container (port 5434). Both were bootstrapped from scratch in this session:

```
python tools/init_db.py
dbmate --no-dump-schema --migrations-dir db/migrations up
# Status: Applied 44, Pending 0
```

Rollback and re-apply of migration 44 verified on both PG16 and PG18 without error.
