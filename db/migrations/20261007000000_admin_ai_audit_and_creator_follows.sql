-- migrate:up
-- Migration 46: AI Creator Follow, Parent Control Setting, and Admin AI Audit tables

CREATE TABLE IF NOT EXISTS child_creator_follows (
    follow_id BIGSERIAL PRIMARY KEY,
    child_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    creator_id BIGINT NOT NULL REFERENCES curated_creators(creator_id) ON DELETE CASCADE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_child_creator_follow UNIQUE (child_id, creator_id)
);

CREATE INDEX IF NOT EXISTS idx_child_creator_follows_child
    ON child_creator_follows(child_id) WHERE active = TRUE;
CREATE INDEX IF NOT EXISTS idx_child_creator_follows_creator
    ON child_creator_follows(creator_id) WHERE active = TRUE;

ALTER TABLE parent_control_settings
    ADD COLUMN IF NOT EXISTS allow_ai_creator_chat BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS admin_ai_audit_logs (
    audit_id BIGSERIAL PRIMARY KEY,
    admin_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    question_category VARCHAR(64) NOT NULL,
    tool_invoked VARCHAR(64) NOT NULL,
    row_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_ai_audit_admin
    ON admin_ai_audit_logs(admin_id, created_at DESC);

-- migrate:down
DROP TABLE IF EXISTS admin_ai_audit_logs;
ALTER TABLE parent_control_settings DROP COLUMN IF EXISTS allow_ai_creator_chat;
DROP TABLE IF EXISTS child_creator_follows;
