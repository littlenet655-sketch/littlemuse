-- migrate:up
CREATE TABLE IF NOT EXISTS creator_chat_messages (
  message_id BIGSERIAL PRIMARY KEY,
  child_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  creator_id BIGINT NOT NULL REFERENCES curated_creators(creator_id) ON DELETE CASCADE,
  sender VARCHAR(16) NOT NULL CHECK (sender IN ('CHILD','CREATOR')),
  message_text TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_creator_chat_child_creator
  ON creator_chat_messages(child_id, creator_id, message_id);

-- migrate:down
DROP INDEX IF EXISTS idx_creator_chat_child_creator;
DROP TABLE IF EXISTS creator_chat_messages;
