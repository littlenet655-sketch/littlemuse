# LittleNet V5 Dependency Reproducibility Report

**Date**: 2026-10-03
**Branch**: release-hardening-final-v5

---

## Python Dependencies

Dependencies are segregated into role-specific requirements files to prevent monolithic dependency bloat.

### Critical Package Analysis: transformers

- **Exact Production Pin**: `transformers==5.10.0` in `requirements-text.txt` and `modal_ai.py`.
- **PyPI Status**: `5.10.0` was tagged as yanked on PyPI with the upstream HuggingFace release note:
  > *"We pushed from a week old main branch. It does include the latest model but uncertain its gonna be working properly and mostly it is missing a bunch of fixes!"*
- **Engineering Decision & Compatibility**:
  - The trained text safety weights artifact (`models/littlenet_text_safety`, 541,351,212 bytes) was calibrated and verified end-to-end against `transformers==5.10.0` (`config.json` declares `"transformers_version": "5.0.0"`).
  - An exact `==` pin (`transformers==5.10.0`) guarantees that pip/Modal will install this specific tested version deterministically without silent minor-version churn.
  - While `5.10.1` is un-yanked on PyPI, `transformers==5.10.0` is deliberately retained as the frozen, verified runtime baseline for V5 to prevent unintended text-safety calibration drift in production.
  - Supply-chain pin test `tests/test_supply_chain_pins.py` strictly enforces `transformers==5.10.0` across both `requirements-text.txt` and `modal_ai.py`.
  - Honest disclosure: LittleNet does not claim non-yanked status for `5.10.0`; it relies on an explicit exact pin to preserve calibrated text-moderation behavior.

### Production ML & Core Pins

| Component | Pinned Version | File |
|-----------|----------------|------|
| transformers | `5.10.0` | `requirements-text.txt`, `modal_ai.py` |
| torch | `2.13.0` | `requirements-text.txt` |
| numpy | `1.26.4` | `requirements-text.txt` |
| detoxify | `0.5.2` | `requirements-text.txt` |
| sentencepiece | `0.2.2` | `requirements-text.txt` |
| psycopg2-binary | `2.9.10` | `requirements-core.txt` |
| Flask | `3.1.3` | `requirements-core.txt` |
| boto3 | `1.40.17` | `requirements-core.txt` |
| modal | `1.6.0` | `requirements-modal.txt` |
| pyjwt | `>=2.15.0` (2.15.1) | `requirements-core.txt` (pip-audit clean) |
| pypdf | `>=6.19.0` (6.19.0) | `requirements-core.txt` (pip-audit clean) |

---

## JavaScript / React Native Dependencies

Managed via npm in `mobile_app/`. `package-lock.json` is committed and deterministically reproducible.

| Package | Version | Purpose |
|---------|---------|---------|
| expo | ~57.0.26 | Expo SDK (doctor: 21/21 PASS) |
| react-native | 0.86 | Core React Native framework |
| @tanstack/react-query | ^5.102.8 | Data fetching & server state cache |
| @shopify/flash-list | 2.0.2 | High-performance virtualized feed list |

---

## Database Tooling

| Tool | Version | SHA-256 |
|------|---------|---------|
| dbmate | 2.34.1 | b002d5249d53d0c6c482ed761b5a806c6fb9a364fcc5f9db3e8763c1d9e40e1d |

`tests/test_supply_chain_pins.py` verifies all Dockerfiles, Modal descriptors, and CI workflows enforce this checksum.

---

## Migration Count

- Total repository migrations: **44** in `db/migrations/`
- Local PG16: **44 Applied, 0 Pending**
- Local PG18: **44 Applied, 0 Pending**
- Production Neon: **42 Applied, 2 Pending** (#43 `outbox_trigger_attempts_reset` and #44 `password_reset_security_hardening`)
