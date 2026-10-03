# LittleNet — Final Verification Evidence

**Purpose:** single authoritative record of the final LittleNet submission
evidence. This document reconciles **documentation and evidence only**. It does
not change executable application logic, and it does not claim any run that did
not happen.

## EXECUTABLE BASELINE

| Item | Value |
|---|---|
| Repository | `littlenet655-sketch/littlemuse` |
| Branch | `release-verification-final-v3` |
| Executable baseline | `086017491ff63214aca3b9ed6e4fe27a7e5835ed` |
| Baseline commit subject | `fix: close final outbox trigger verification gap` |
| Documentation HEAD | docs-only commit(s) on top of the baseline (see `release_docs/FILES_CHANGED.md`) |

GitHub `main` is intentionally older than this baseline. Do not use `main` as
the release reference.

## CURRENT FINAL RESULTS

| Gate | Result |
|---|---|
| Backend (`python -m pytest tests/ -q`) | **898 passed / 2 skipped / 0 failed** |
| Mobile (`cd mobile_app && npm test`) | **283 passed / 0 failed** |
| TypeScript (`npx tsc --noEmit`) | **PASS** |
| Expo Doctor | **21/21 PASS** |
| Android local export (`npm run export:android`) | **PASS** |
| PostgreSQL | **16.15** (+ pgvector 0.8.7) |
| Migrations | **43 applied / 0 pending** |
| Migration 43 rollback / re-apply | **PASS** |
| `compileall` | **PASS** |
| `audit_all` | **PASS** |
| `audit_dynamic_sql` | **2/2 approved** |
| `npm ci --dry-run` | **PASS** |

Latest migration: `db/migrations/20261002120000_outbox_trigger_attempts_reset.sql`
(migration 43 of 43).

### Final locally-proven database trigger behaviour

| Trigger | Observed result |
|---|---|
| POST media-delete trigger | `attempts` 8 → 0; `attempts` 4 → 4 (unchanged); completed row → 0 |
| MESSAGE media-delete trigger | `attempts` 8 → 0; `attempts` 4 → 4 (unchanged); completed row → 0 |
| Retry worker bound | only `attempts < 8` rows are retried |

## MODELS

These are the real trained payloads. Their SHA-256 values are **frozen — do not
modify**.

| Model | Path | SHA-256 | Bytes |
|---|---|---|---|
| Core Safety V2 | `models/littlenet_core_safety_v2.pth` | `8a9ccfbfd5f59b65143bb90131750db75ff54b895e82d31af04b1e2ccafd431c` | 16,335,485 |
| Weapons / Violence V3 | `models/littlenet_weapons_violence_v3.pth` | `f028ddfa0264ad9570ec6411666143eb57ec9f9159ca218dd6e27f2c413591e8` | 16,327,011 |
| Text Safety | `models/littlenet_text_safety/model.safetensors` | `7eb1f37efdd95a1f363ed76377e65e512c2f986140a50fea404cdcd5598fe875` | 541,351,212 |

All three are tracked through **Git LFS**. A fresh clone contains the LFS
*pointer* files, not the binaries — run `git lfs pull` before any AI inference
deployment or before packaging a distribution ZIP. The pointer OIDs equal the
SHA-256 values above.

## SUPERSEDED BASELINES — NOT CURRENT

| Superseded baseline | Old figures | Status |
|---|---|---|
| `f4be262` | 885 backend / 1 skipped / 281 mobile / 42 migrations | **HISTORICAL — SUPERSEDED** |
| `826e633` | named as "freeze"/"parent" in several release docs | **HISTORICAL — SUPERSEDED** |

Neither may be presented as current. Where these values still appear in the
documentation they are explicitly labelled as historical.

## INDEPENDENT REVIEW SUMMARY

**Claude** — performed multiple independent release and source audits and found
no broad final executable regression. Some checks were environment-limited.

**MiniMax** — independently verified:

- V3 source identity
- V3 ZIP identity
- ZIP portability / hygiene
- model hashes and structure
- mobile 283/283
- TypeScript and static checks
- legacy feature coverage
- **no executable regression**

MiniMax **could not** execute the backend suite or PostgreSQL in its sandbox.

**Consequence, stated plainly:** the backend and PostgreSQL final values
(898 passed / 2 skipped / 0 failed, and 43 applied / 0 pending with the trigger
behaviour above) come from the **successful final local execution** recorded
elsewhere in the release docs. They are *not* an independent MiniMax re-run. Any
session that does not itself rerun backend/PostgreSQL must present them as
**SUPPORTED BY FINAL LOCAL EXECUTION EVIDENCE**, not as independently
reproduced results.

**Never claim an independent run that did not happen.** Environment limitations
are not application regressions.

## NOT EXECUTED

Live Neon / Cloudflare R2 / Resend / Modal; EAS cloud APK build; APK install and
physical-device smoke tests; CI-only scanners (`pip-audit`, `bandit`,
`gitleaks`); a live production scan of any kind.
