# LittleNet — Historical External Evidence

**Purpose:** record two *different* historical live/preflight observations that
were reported during earlier operator sessions, and to state unambiguously that
**neither is current production state**.

## Why this file exists

The final offline audits and source reviews did **not** re-query production. The
figures below were observed at earlier points in time by operator sessions. They
are preserved because they are useful evidence about operational history — but
they are **not** a statement about the database as it stands now, and they must
not be merged, averaged, or reconciled into a single "current" number.

## Checkpoint A — later operator-reported read-only live preflight

A later operator session ran a **read-only live preflight** and reported:

| Observation | Value |
|---|---|
| Posts in `PROCESSING` | 74 |
| Posts in `FAILED` | 38 |
| Posts in `UPLOADED` | 4 |
| Expired `PENDING` upload sessions | 160 |
| Open `REVIEW` events | 4 |
| R2 / media inconsistencies | historical inconsistencies present |
| Modal deployments | older deployments present |

## Checkpoint B — separate, older repository / live audit

A **separate, older** repository and live audit reported different values,
approximately:

| Observation | Value |
|---|---|
| Posts in `PROCESSING` | 9 |
| Posts in `FAILED` | 61 |
| Migrations applied | 13 |

## Reconciliation — read this before citing either set

1. **These are two different historical checkpoints**, taken at different times
   against different states. Checkpoint A and Checkpoint B are not
   contradictory; they are not measuring the same moment.
2. **Neither is current production state.** Do not quote either set as "the"
   LittleNet production position.
3. **Do not try to reconcile them into one number.** Any single merged figure
   would be fabricated.
4. **The final offline audits did not re-query production.** The documentation
   reconciliation and final verification evidence in this release were produced
   from source review and local test execution only.
5. **Current values require a new authorized live query** by someone with
   production credentials and explicit authorization to inspect live data.
6. **Fixing source recurrence does not automatically clean historical data.**
   The source changes that closed the recurrence paths (bounded retry worker,
   delete-outbox attempt reset, upload-session expiry handling) prevent new rows
   from accumulating in those states. They do **not** retroactively repair the
   rows counted in Checkpoint A or Checkpoint B. Cleaning those rows is a
   separate, authorized data-maintenance task and is **NOT EXECUTED**.

## Status

- Live production query in this release: **NOT EXECUTED**
- Live Neon / R2 / Resend / Modal contact in this release: **NOT EXECUTED**
- Historical data remediation: **NOT EXECUTED** (requires separate authorization)
