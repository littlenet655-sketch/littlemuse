-- migrate:up
CREATE TABLE IF NOT EXISTS media_assets (
    media_id BIGSERIAL PRIMARY KEY,
    post_id BIGINT REFERENCES posts(post_id) ON DELETE CASCADE,
    media_kind VARCHAR(32) NOT NULL,
    source_r2_key TEXT NOT NULL,
    published_reference TEXT,
    provider VARCHAR(32) NOT NULL DEFAULT 'R2_SANITIZED_MP4',
    provider_asset_id VARCHAR(128),
    playback_id VARCHAR(128),
    poster_reference TEXT,
    duration_ms INT,
    width INT,
    height INT,
    aspect_ratio VARCHAR(16),
    status VARCHAR(32) NOT NULL DEFAULT 'PROCESSING',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_media_assets_post_id ON media_assets(post_id);
CREATE INDEX IF NOT EXISTS idx_media_assets_playback_id ON media_assets(playback_id);

CREATE TABLE IF NOT EXISTS story_views (
    story_view_id BIGSERIAL PRIMARY KEY,
    post_id BIGINT NOT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
    child_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(post_id, child_id)
);

ALTER TABLE story_views ADD COLUMN IF NOT EXISTS first_viewed_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE story_views ADD COLUMN IF NOT EXISTS last_viewed_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE story_views ADD COLUMN IF NOT EXISTS completion_ratio NUMERIC(4, 3) DEFAULT 1.000;

CREATE INDEX IF NOT EXISTS idx_story_views_post_child ON story_views(post_id, child_id);

CREATE TABLE IF NOT EXISTS user_device_tokens (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    platform VARCHAR(16) NOT NULL,
    push_token TEXT NOT NULL,
    device_identifier VARCHAR(128),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,
    CONSTRAINT uq_user_device_token UNIQUE(user_id, push_token)
);

CREATE INDEX IF NOT EXISTS idx_user_device_tokens_active ON user_device_tokens(user_id) WHERE revoked_at IS NULL;

-- migrate:down
DROP TABLE IF EXISTS user_device_tokens;
DROP TABLE IF EXISTS media_assets;

