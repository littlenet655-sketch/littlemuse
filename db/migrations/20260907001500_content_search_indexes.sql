-- migrate:up
-- Keep LittleNet search inside Neon/PostgreSQL. pg_trgm accelerates the
-- contains-style ILIKE lookups used for captions, hashtags and approved
-- comments without introducing a second search server.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_posts_caption_trgm
  ON posts USING GIN (caption gin_trgm_ops)
  WHERE moderation_status='ALLOWED' AND is_safe=TRUE AND is_story=FALSE;

CREATE INDEX IF NOT EXISTS idx_comments_text_trgm
  ON comments USING GIN (comment_text gin_trgm_ops)
  WHERE moderation_status='ALLOWED';

-- Creator-name searches are small today, but full trigram indexes avoid the
-- planner having to prove extra role/status predicates before using them.
CREATE INDEX IF NOT EXISTS idx_users_username_trgm
  ON users USING GIN (username gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_users_full_name_trgm
  ON users USING GIN (full_name gin_trgm_ops);

-- Comment FTS exactly matches the expression used by matching_comments.
CREATE INDEX IF NOT EXISTS idx_comments_text_fts
  ON comments USING GIN (to_tsvector('simple',COALESCE(comment_text,'')))
  WHERE moderation_status='ALLOWED';

-- migrate:down
DROP INDEX IF EXISTS idx_comments_text_fts;
DROP INDEX IF EXISTS idx_users_full_name_trgm;
DROP INDEX IF EXISTS idx_users_username_trgm;
DROP INDEX IF EXISTS idx_comments_text_trgm;
DROP INDEX IF EXISTS idx_posts_caption_trgm;
-- pg_trgm is intentionally retained because other database features may use it.
