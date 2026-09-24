-- migrate:up
CREATE TABLE IF NOT EXISTS chat_upload_sessions (
  upload_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  child_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  peer_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  object_key VARCHAR(500) NOT NULL UNIQUE,
  media_type VARCHAR(20) NOT NULL CHECK (media_type IN ('IMAGE','VIDEO')),
  expected_size_bytes BIGINT NOT NULL,
  mime_type VARCHAR(100) NOT NULL,
  extension VARCHAR(20) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
    CHECK (status IN ('PENDING','REVIEW','CONSUMED','BLOCKED','EXPIRED','CANCELLED')),
  message_id BIGINT REFERENCES child_messages(child_message_id) ON DELETE SET NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  consumed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_chat_upload_sessions_child_status
  ON chat_upload_sessions(child_id,status,expires_at);

-- migrate:down
DROP INDEX IF EXISTS idx_chat_upload_sessions_child_status;
DROP TABLE IF EXISTS chat_upload_sessions;
