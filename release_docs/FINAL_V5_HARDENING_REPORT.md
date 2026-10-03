# LittleNet V5 Final Hardening Report

**Branch**: release-hardening-final-v5
**Base V4 frozen commit**: 448802b8e894e6ab5392f9a8198b2c3ecf582e76
**Release HEAD**: 3aa105df21c9e50bb1d924fa0e25b1357dc1aaee
**Date**: 2026-10-03

---

## Regression Matrix Results

| Suite | Count | Failed | Skipped |
|-------|-------|--------|---------|
| Backend pytest (Python 3.11, PG16) | 916 | 0 | 2 |
| Mobile Jest (Node.js) | 283 | 0 | 0 |
| TypeScript typecheck (tsc --noEmit) | -- | 0 | -- |
| Expo Doctor (21 checks) | 21/21 | 0 | -- |
| Android export | SUCCESS | -- | -- |

PREFLIGHT: PASS | ROUTES 128 ERRORS 0 | SCOPE_CHECK 33/33 | REACT NATIVE SOURCE: PASS | DYNAMIC SQL 2/2 APPROVED

---

## Group Commits (V5 Hardening)

| Group | Commit | Description |
|-------|--------|-------------|
| 1 | bf28bff | Password reset security hardening (migration 44) |
| 2 | b6d767f | Parent resend 503 contract fix + Discover N+1 elimination |
| 3 | 085c731 | Moderation merge deduplication + cache fail-closed + routing |
| 4 | 3d9b632 | Demo boost automatic background restore |
| 5 | 6757452 | R2 upload credential hardening |
| 6+7 | fed659f | PG16 concurrency race prevention + dependency analysis |
| 8 | ca5fecb | Operator reconciliation tooling |
| 9 | 522554b | Migration isolation hardening PG16+PG18 |

---

## Model Binary SHA-256 Hashes (Frozen)

| Model | SHA-256 |
|-------|---------|
| models/littlenet_core_safety_v2.pth | 8a9ccfbfd5f59b65143bb90131750db75ff54b895e82d31af04b1e2ccafd431c |
| models/littlenet_weapons_violence_v3.pth | f028ddfa0264ad9570ec6411666143eb57ec9f9159ca218dd6e27f2c413591e8 |
| models/littlenet_text_safety/model.safetensors | 7eb1f37efdd95a1f363ed76377e65e512c2f986140a50fea404cdcd5598fe875 |

---

## Infrastructure Status (READ-ONLY, No Mutations)

| Service | Status |
|---------|--------|
| Neon Postgres 18.6 | Connected, 42 migrations applied |
| Cloudflare R2 (littlenet-media) | HeadBucket ACCESSIBLE |
| Modal (netlittle2) | 2 deployed apps, 3 volumes active |

---

## Non-Negotiable Rules Compliance

- main branch: UNTOUCHED
- No force pushes
- No live infrastructure mutations
- Model binary hashes: UNCHANGED from V4 baseline
- Package identity: com.littlenet.app
