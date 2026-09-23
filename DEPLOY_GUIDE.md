# LittleNet Deployment Guide

> **Canonical guide:** [MODAL_DEPLOYMENT.md](./MODAL_DEPLOYMENT.md)

Current target identities are `littlemuse-web` and `littlemuse-ai`.
Do not use historical `netlittle2/littlenet-web/littlenet-ai` commands from old
reports as release instructions.

Retained database releases must pass the guarded reconciliation procedure in
`docs/DATABASE_RELEASE_RECONCILIATION.md`; do not blindly run the legacy
bootstrap on a data-bearing database.

The release workflow is `.github/workflows/deploy-modal.yml`. After a green
live deployment, build a fresh EAS APK from the verified `mobile_app/app.json`
identity and execute `docs/PHYSICAL_DEVICE_CHECKLIST.md` with one tester first.
