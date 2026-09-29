-- migrate:up

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS demo_unlimited BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_users_demo_unlimited
  ON users(user_id)
  WHERE demo_unlimited=TRUE;

-- migrate:down

DROP INDEX IF EXISTS idx_users_demo_unlimited;
ALTER TABLE users DROP COLUMN IF EXISTS demo_unlimited;
