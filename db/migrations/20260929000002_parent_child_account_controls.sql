-- migrate:up

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS parent_paused BOOLEAN NOT NULL DEFAULT FALSE;

-- migrate:down

ALTER TABLE users DROP COLUMN IF EXISTS parent_paused;
