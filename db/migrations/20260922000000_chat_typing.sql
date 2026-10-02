-- migrate:up
-- Ephemeral typing indicators for kid-to-kid chat. Rows are heartbeats, not
-- durable state: a row is only "typing" if updated_at is within the TTL the
-- API applies at read time. Stale rows are cleaned opportunistically.
CREATE TABLE IF NOT EXISTS chat_typing (
  conversation_id BIGINT NOT NULL REFERENCES child_conversations(conversation_id) ON DELETE CASCADE,
  user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (conversation_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_chat_typing_updated_at ON chat_typing(updated_at);

-- migrate:down
DROP TABLE IF EXISTS chat_typing;
