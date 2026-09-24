-- migrate:up
ALTER TABLE upload_sessions
  ADD COLUMN IF NOT EXISTS target_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE;

ALTER TABLE upload_sessions
  DROP CONSTRAINT IF EXISTS upload_sessions_kind_check;

ALTER TABLE upload_sessions
  ADD CONSTRAINT upload_sessions_kind_check
  CHECK (kind IN ('POST','REEL','STORY','MESSAGE'));

ALTER TABLE child_messages
  ADD COLUMN IF NOT EXISTS upload_id UUID REFERENCES upload_sessions(upload_id) ON DELETE SET NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_child_messages_upload_id_uniq
  ON child_messages(upload_id)
  WHERE upload_id IS NOT NULL;

-- migrate:down
DROP INDEX IF EXISTS idx_child_messages_upload_id_uniq;
ALTER TABLE child_messages DROP COLUMN IF EXISTS upload_id;
ALTER TABLE upload_sessions DROP COLUMN IF EXISTS target_id;
ALTER TABLE upload_sessions DROP CONSTRAINT IF EXISTS upload_sessions_kind_check;
ALTER TABLE upload_sessions
  ADD CONSTRAINT upload_sessions_kind_check
  CHECK (kind IN ('POST','REEL','STORY'));
