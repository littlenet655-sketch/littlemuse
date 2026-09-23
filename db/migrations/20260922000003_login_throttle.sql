-- migrate:up
-- Migration: per-account failed-login throttling for T1-007
-- One row per canonical user_id; username/email aliases share the same budget
-- because login_user keys state by the resolved user_id, never the identifier.
CREATE TABLE IF NOT EXISTS login_throttle (
    user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    failed_attempts INTEGER NOT NULL DEFAULT 0 CHECK (failed_attempts >= 0),
    first_failed_at TIMESTAMPTZ,
    last_failed_at TIMESTAMPTZ,
    locked_until TIMESTAMPTZ
);

-- migrate:down
DROP TABLE IF EXISTS login_throttle;
