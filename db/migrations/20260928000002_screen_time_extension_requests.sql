-- migrate:up
-- Screen-time extension request flow (defect follow-up): a child can ask a
-- parent for more time, the parent approves/rejects from their Screen Time
-- surface, and an approval writes a TODAY-ONLY bonus grant that the
-- enforcement check (services/usage.py lock_state) reads at check time.
--
-- bonus_minutes/bonus_date on child_time_limits: same-day bonus minutes
-- granted via approved extension requests. The date column lets the
-- enforcement check ignore stale bonuses without a midnight cron.

CREATE TABLE IF NOT EXISTS screen_time_extension_requests(
  request_id SERIAL PRIMARY KEY,
  child_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  requested_minutes INTEGER NOT NULL CHECK (requested_minutes BETWEEN 5 AND 180),
  status TEXT NOT NULL DEFAULT 'PENDING'
    CHECK (status IN ('PENDING','APPROVED','REJECTED','EXPIRED')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  decided_at TIMESTAMPTZ,
  decided_by INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
  granted_minutes INTEGER CHECK (granted_minutes BETWEEN 1 AND 720)
);
CREATE INDEX IF NOT EXISTS idx_ster_child_status
  ON screen_time_extension_requests(child_id, status);

ALTER TABLE child_time_limits
  ADD COLUMN IF NOT EXISTS bonus_minutes INTEGER NOT NULL DEFAULT 0;
ALTER TABLE child_time_limits
  ADD COLUMN IF NOT EXISTS bonus_date DATE;

-- migrate:down
DROP TABLE IF EXISTS screen_time_extension_requests;
ALTER TABLE child_time_limits DROP COLUMN IF EXISTS bonus_minutes;
ALTER TABLE child_time_limits DROP COLUMN IF EXISTS bonus_date;
