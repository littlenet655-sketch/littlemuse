-- migrate:up

-- Curated/system content is intentionally separate from child-generated posts.
-- This keeps dataset provenance, publication state and moderation invariants out
-- of the social graph while still allowing the feed service to merge candidates.
CREATE TABLE content_categories (
  category_id SMALLSERIAL PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL UNIQUE,
  is_educational BOOLEAN NOT NULL DEFAULT FALSE,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO content_categories(slug,display_name,is_educational)
VALUES
  ('family','Family & Community',FALSE),
  ('animals','Nature & Animals',TRUE),
  ('crafts','Art & Creative Hobbies',TRUE),
  ('gardening','Science & Gardening',TRUE),
  ('cooking','Culinary Arts & Food',TRUE)
ON CONFLICT(slug) DO NOTHING;

CREATE TABLE curated_media_assets (
  asset_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_version TEXT NOT NULL,
  source_row_id TEXT NOT NULL,
  archive_file TEXT NOT NULL,
  original_filename TEXT NOT NULL,
  sha256 CHAR(64) NOT NULL UNIQUE,
  media_type TEXT NOT NULL CHECK(media_type IN ('IMAGE','VIDEO')),
  original_object_key TEXT NOT NULL UNIQUE,
  delivery_object_key TEXT NOT NULL UNIQUE,
  poster_object_key TEXT,
  thumbnail_object_key TEXT,
  mime_type TEXT NOT NULL,
  width INTEGER NOT NULL CHECK(width > 0),
  height INTEGER NOT NULL CHECK(height > 0),
  duration_seconds NUMERIC(8,2) CHECK(duration_seconds IS NULL OR duration_seconds >= 0),
  file_size_bytes BIGINT NOT NULL CHECK(file_size_bytes > 0),
  moderation_status TEXT NOT NULL CHECK(moderation_status IN ('PENDING','ALLOWED','REVIEW','BLOCKED')),
  is_safe BOOLEAN NOT NULL DEFAULT FALSE,
  safety_score NUMERIC(6,4) CHECK(safety_score IS NULL OR (safety_score >= 0 AND safety_score <= 1)),
  adult_score NUMERIC(6,4) CHECK(adult_score IS NULL OR (adult_score >= 0 AND adult_score <= 1)),
  violence_score NUMERIC(6,4) CHECK(violence_score IS NULL OR (violence_score >= 0 AND violence_score <= 1)),
  weapon_score NUMERIC(6,4) CHECK(weapon_score IS NULL OR (weapon_score >= 0 AND weapon_score <= 1)),
  toxicity_score NUMERIC(6,4) CHECK(toxicity_score IS NULL OR (toxicity_score >= 0 AND toxicity_score <= 1)),
  moderation_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(dataset_version,source_row_id),
  CHECK(moderation_status <> 'ALLOWED' OR is_safe=TRUE),
  CHECK(moderation_status <> 'BLOCKED' OR is_safe=FALSE)
);

CREATE TABLE curated_content (
  content_id BIGSERIAL PRIMARY KEY,
  asset_id UUID NOT NULL UNIQUE REFERENCES curated_media_assets(asset_id) ON DELETE RESTRICT,
  category_id SMALLINT NOT NULL REFERENCES content_categories(category_id) ON DELETE RESTRICT,
  title TEXT NOT NULL,
  caption TEXT NOT NULL,
  audience_age_group TEXT NOT NULL CHECK(audience_age_group IN ('ALL','6-8','9-11','12-13','14-18')),
  min_age SMALLINT NOT NULL CHECK(min_age BETWEEN 4 AND 18),
  max_age SMALLINT NOT NULL CHECK(max_age BETWEEN 4 AND 18),
  is_reel BOOLEAN NOT NULL DEFAULT FALSE,
  is_story BOOLEAN NOT NULL DEFAULT FALSE,
  destination_tab TEXT NOT NULL,
  publish_status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(publish_status IN ('DRAFT','PUBLISHED','ARCHIVED')),
  editorial_weight NUMERIC(6,4) NOT NULL DEFAULT 1.0 CHECK(editorial_weight >= 0),
  published_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK(min_age <= max_age),
  CHECK(NOT is_story OR NOT is_reel)
);

CREATE TABLE hashtags (
  hashtag_id BIGSERIAL PRIMARY KEY,
  tag TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX ux_hashtags_lower ON hashtags((LOWER(tag)));

CREATE TABLE curated_content_hashtags (
  content_id BIGINT NOT NULL REFERENCES curated_content(content_id) ON DELETE CASCADE,
  hashtag_id BIGINT NOT NULL REFERENCES hashtags(hashtag_id) ON DELETE CASCADE,
  PRIMARY KEY(content_id,hashtag_id)
);

-- Child-facing history used for no-repeat windows and later recommendation
-- tuning. source_id is a social post_id or curated_content.content_id depending
-- on source_type.
CREATE TABLE content_impressions (
  impression_id BIGSERIAL PRIMARY KEY,
  child_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  source_type TEXT NOT NULL CHECK(source_type IN ('SOCIAL','CURATED')),
  source_id BIGINT NOT NULL,
  surface TEXT NOT NULL CHECK(surface IN ('FEED','REELS')),
  shown_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  watched_ms INTEGER CHECK(watched_ms IS NULL OR watched_ms >= 0),
  completed BOOLEAN NOT NULL DEFAULT FALSE,
  liked BOOLEAN NOT NULL DEFAULT FALSE,
  saved BOOLEAN NOT NULL DEFAULT FALSE
);

-- Stable candidate ordering across cursor pages. A feed/reels request can build
-- one short session and subsequent cursor requests consume positions from it.
CREATE TABLE feed_sessions (
  session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  child_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  surface TEXT NOT NULL CHECK(surface IN ('FEED','REELS')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '30 minutes')
);

CREATE TABLE feed_session_items (
  session_id UUID NOT NULL REFERENCES feed_sessions(session_id) ON DELETE CASCADE,
  position INTEGER NOT NULL CHECK(position >= 0),
  source_type TEXT NOT NULL CHECK(source_type IN ('SOCIAL','CURATED')),
  source_id BIGINT NOT NULL,
  category_slug TEXT,
  rank_score NUMERIC(12,6),
  PRIMARY KEY(session_id,position),
  UNIQUE(session_id,source_type,source_id)
);

CREATE INDEX idx_curated_assets_allowed
  ON curated_media_assets(asset_id)
  WHERE moderation_status='ALLOWED' AND is_safe=TRUE;

CREATE INDEX idx_curated_content_feed
  ON curated_content(is_reel,category_id,min_age,max_age,published_at DESC,content_id DESC)
  WHERE publish_status='PUBLISHED';

CREATE INDEX idx_curated_hashtag_lookup
  ON curated_content_hashtags(hashtag_id,content_id);

CREATE INDEX idx_content_impressions_recent
  ON content_impressions(child_id,source_type,source_id,shown_at DESC);

CREATE INDEX idx_feed_sessions_child
  ON feed_sessions(child_id,surface,expires_at DESC);

CREATE INDEX idx_feed_session_items_source
  ON feed_session_items(session_id,source_type,source_id);

-- Database-level publication gate: even a buggy admin script cannot publish an
-- asset which did not pass the moderation boundary.
CREATE OR REPLACE FUNCTION littlenet_validate_curated_publish() RETURNS trigger AS $$
DECLARE
  asset_status TEXT;
  asset_safe BOOLEAN;
BEGIN
  IF NEW.publish_status='PUBLISHED' THEN
    SELECT moderation_status,is_safe INTO asset_status,asset_safe
      FROM curated_media_assets WHERE asset_id=NEW.asset_id;
    IF asset_status IS DISTINCT FROM 'ALLOWED' OR asset_safe IS DISTINCT FROM TRUE THEN
      RAISE EXCEPTION 'Curated content cannot be published unless its media asset is ALLOWED and safe';
    END IF;
    IF NEW.published_at IS NULL THEN NEW.published_at=NOW(); END IF;
  END IF;
  NEW.updated_at=NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_validate_curated_publish
  BEFORE INSERT OR UPDATE OF asset_id,publish_status ON curated_content
  FOR EACH ROW EXECUTE FUNCTION littlenet_validate_curated_publish();

-- migrate:down
DROP TRIGGER IF EXISTS trg_validate_curated_publish ON curated_content;
DROP FUNCTION IF EXISTS littlenet_validate_curated_publish();
DROP TABLE IF EXISTS feed_session_items;
DROP TABLE IF EXISTS feed_sessions;
DROP TABLE IF EXISTS content_impressions;
DROP TABLE IF EXISTS curated_content_hashtags;
DROP TABLE IF EXISTS hashtags;
DROP TABLE IF EXISTS curated_content;
DROP TABLE IF EXISTS curated_media_assets;
DROP TABLE IF EXISTS content_categories;
