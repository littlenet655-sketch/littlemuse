"""Retired: database/upgrade.sql must not be applied outside the owned flow.

dbmate is the single migration owner for LittleNet. The legacy
``database/upgrade.sql`` file is applied ONLY as part of the blessed baseline
by ``tools/init_db.py`` (fresh databases), followed by ``dbmate up``.

Applying upgrade.sql directly — what this script used to do — bypasses dbmate
history and can silently diverge a database from the tracked migration state.
This shim fails loudly instead. It makes no database changes.

Owned flow:
    python tools/init_db.py
    dbmate --no-dump-schema --migrations-dir db/migrations up
"""
import sys

print(
    "ERROR: tools/upgrade_db.py is retired.\n"
    "dbmate is the single migration owner. Do not apply database/upgrade.sql directly.\n"
    "Use instead:\n"
    "    python tools/init_db.py\n"
    "    dbmate --no-dump-schema --migrations-dir db/migrations up\n"
    "See db/migrations/README.md and MODAL_DEPLOYMENT.md.",
    file=sys.stderr,
)
sys.exit(2)
