-- migrate:up
CREATE TABLE IF NOT EXISTS story_reactions (
  reaction_id BIGSERIAL PRIMARY KEY,
  story_id BIGINT NOT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
  child_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  emoji VARCHAR(8) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(story_id, child_id)
);

CREATE INDEX IF NOT EXISTS idx_story_reactions_story
  ON story_reactions(story_id, updated_at DESC);

-- migrate:down
DROP INDEX IF EXISTS idx_story_reactions_story;
DROP TABLE IF EXISTS story_reactions;
