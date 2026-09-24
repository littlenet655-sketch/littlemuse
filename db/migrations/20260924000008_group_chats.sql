-- migrate:up
ALTER TABLE parent_control_settings
  ADD COLUMN IF NOT EXISTS allow_group_chats BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS child_groups (
  group_id BIGSERIAL PRIMARY KEY,
  owner_child_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  title VARCHAR(60) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
    CHECK (status IN ('PENDING','ACTIVE','ARCHIVED')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS child_group_members (
  group_id BIGINT NOT NULL REFERENCES child_groups(group_id) ON DELETE CASCADE,
  child_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  role VARCHAR(20) NOT NULL DEFAULT 'MEMBER'
    CHECK (role IN ('OWNER','MEMBER')),
  status VARCHAR(24) NOT NULL DEFAULT 'INVITED'
    CHECK (status IN ('INVITED','PARENT_PENDING','ACTIVE','DECLINED','LEFT','REMOVED')),
  invited_by INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  child_accepted_at TIMESTAMPTZ,
  parent_approved_at TIMESTAMPTZ,
  parent_approved_by INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
  last_read_message_id BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY(group_id,child_id)
);

CREATE TABLE IF NOT EXISTS child_group_messages (
  group_message_id BIGSERIAL PRIMARY KEY,
  group_id BIGINT NOT NULL REFERENCES child_groups(group_id) ON DELETE CASCADE,
  sender_child_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  message_text TEXT NOT NULL,
  reply_to_group_message_id BIGINT REFERENCES child_group_messages(group_message_id) ON DELETE SET NULL,
  moderation_status VARCHAR(20) NOT NULL DEFAULT 'ALLOWED'
    CHECK (moderation_status IN ('PENDING','ALLOWED','REVIEW','BLOCKED')),
  is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
  sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS group_message_reactions (
  reaction_id BIGSERIAL PRIMARY KEY,
  group_message_id BIGINT NOT NULL REFERENCES child_group_messages(group_message_id) ON DELETE CASCADE,
  child_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  emoji VARCHAR(8) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(group_message_id,child_id)
);

CREATE INDEX IF NOT EXISTS idx_child_group_members_child_status
  ON child_group_members(child_id,status,updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_child_group_members_group_status
  ON child_group_members(group_id,status,updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_child_group_messages_group_recent
  ON child_group_messages(group_id,group_message_id DESC)
  WHERE is_deleted=FALSE;
CREATE INDEX IF NOT EXISTS idx_group_message_reactions_message
  ON group_message_reactions(group_message_id,updated_at DESC);

-- migrate:down
DROP INDEX IF EXISTS idx_group_message_reactions_message;
DROP INDEX IF EXISTS idx_child_group_messages_group_recent;
DROP INDEX IF EXISTS idx_child_group_members_group_status;
DROP INDEX IF EXISTS idx_child_group_members_child_status;
DROP TABLE IF EXISTS group_message_reactions;
DROP TABLE IF EXISTS child_group_messages;
DROP TABLE IF EXISTS child_group_members;
DROP TABLE IF EXISTS child_groups;
ALTER TABLE parent_control_settings DROP COLUMN IF EXISTS allow_group_chats;
