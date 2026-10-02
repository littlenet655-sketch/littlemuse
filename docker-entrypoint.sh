#!/bin/sh
set -eu
mkdir -p /data/uploads /data/models /data/cache
rm -rf /app/uploads
ln -s /data/uploads /app/uploads
export HF_HOME="${HF_HOME:-/data/models/huggingface}"
export DEEPFACE_HOME="${DEEPFACE_HOME:-/data/models/deepface}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-/data/cache}"

# Single migration owner: dbmate. The legacy baseline bootstrap
# (tools/init_db.py) is idempotent; all post-adoption changes are tracked by
# dbmate. A missing dbmate binary is a hard error, never a silent skip — a
# container starting without migrations applied would serve a broken schema.
python tools/init_db.py
if ! command -v dbmate >/dev/null 2>&1; then
  echo "ERROR: dbmate is not installed; refusing to start without migrations." >&2
  exit 1
fi
dbmate --no-dump-schema --migrations-dir "${DBMATE_MIGRATIONS_DIR:-db/migrations}" up

# Deterministic local quiz fallback. The seeder is idempotent (unique
# question+age-group constraint / ON CONFLICT DO NOTHING), so every deploy
# repairs a missing or partially seeded bank without duplicating rows.
python tools/seed_quizzes.py

exec gunicorn app:app --bind "0.0.0.0:${PORT:-8080}" --workers 1 --threads 4 --timeout 240 --graceful-timeout 45 --access-logfile - --error-logfile -
