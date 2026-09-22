-- Idempotent upgrades for LittleNet databases created by earlier project stages.
ALTER TABLE posts ADD COLUMN IF NOT EXISTS audience_age_group VARCHAR(10) NOT NULL DEFAULT 'ALL';
DO $$ BEGIN
  ALTER TABLE posts ADD CONSTRAINT posts_audience_age_group_check CHECK(audience_age_group IN ('ALL','6-8','9-11','12-13','14-18'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS parent_control_settings (
 child_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
 parent_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
 allow_reels BOOLEAN NOT NULL DEFAULT TRUE,
 allow_stories BOOLEAN NOT NULL DEFAULT TRUE,
 allow_messaging BOOLEAN NOT NULL DEFAULT TRUE,
 allow_posting BOOLEAN NOT NULL DEFAULT TRUE,
 allow_discover BOOLEAN NOT NULL DEFAULT TRUE,
 quiet_hours_enabled BOOLEAN NOT NULL DEFAULT FALSE,
 quiet_start TIME NOT NULL DEFAULT '21:00',
 quiet_end TIME NOT NULL DEFAULT '07:00',
 educational_only_feed BOOLEAN NOT NULL DEFAULT FALSE,
 allowed_categories JSONB NOT NULL DEFAULT '["Other","Science","Math","Art","Sports","Music","Technology","Education","Nature","Books","Coding","General Knowledge"]'::jsonb,
 updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE parent_control_settings ADD COLUMN IF NOT EXISTS quiet_hours_enabled BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE parent_control_settings ADD COLUMN IF NOT EXISTS quiet_start TIME NOT NULL DEFAULT '21:00';
ALTER TABLE parent_control_settings ADD COLUMN IF NOT EXISTS quiet_end TIME NOT NULL DEFAULT '07:00';
CREATE TABLE IF NOT EXISTS user_preferences (
 user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
 preferred_language VARCHAR(5) NOT NULL DEFAULT 'EN' CHECK(preferred_language IN ('EN','KN','HI')),
 updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS learning_challenges (
 challenge_id SERIAL PRIMARY KEY, title VARCHAR(150) NOT NULL, description TEXT NOT NULL,
 challenge_type VARCHAR(20) NOT NULL CHECK(challenge_type IN ('PUZZLE','ACTIVITY','CYBER_SAFETY')),
 prompt TEXT, expected_answer VARCHAR(255), age_group VARCHAR(10) NOT NULL CHECK(age_group IN ('6-8','9-11','12-13','14-18')),
 points INTEGER NOT NULL DEFAULT 10 CHECK(points BETWEEN 1 AND 100), active BOOLEAN NOT NULL DEFAULT TRUE,
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS learning_challenge_attempts (
 attempt_id BIGSERIAL PRIMARY KEY, child_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
 challenge_id INTEGER NOT NULL REFERENCES learning_challenges(challenge_id) ON DELETE CASCADE,
 response TEXT, completed BOOLEAN NOT NULL DEFAULT TRUE, points_awarded INTEGER NOT NULL DEFAULT 0,
 completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(child_id,challenge_id)
);

-- XP table for quiz rewards
CREATE TABLE IF NOT EXISTS child_xp (
  child_id  INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
  xp        INTEGER NOT NULL DEFAULT 0 CHECK(xp >= 0),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- Track quiz source (AI-generated vs curated)
ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS source VARCHAR(10) NOT NULL DEFAULT 'SEED';

-- Server-persistent compulsory feed/reel brain-break state. These columns make
-- the obligation survive refresh, tab changes, login/session renewal, and JS
-- counter resets. viewed_post_ids is reset only after a required answer is
-- accepted by the server.
ALTER TABLE child_quiz_progress ADD COLUMN IF NOT EXISTS quiz_required BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE child_quiz_progress ADD COLUMN IF NOT EXISTS required_quiz_id INTEGER REFERENCES quizzes(quiz_id) ON DELETE SET NULL;
ALTER TABLE child_quiz_progress ADD COLUMN IF NOT EXISTS required_at TIMESTAMP;
ALTER TABLE child_quiz_progress ADD COLUMN IF NOT EXISTS viewed_post_ids JSONB NOT NULL DEFAULT '[]'::jsonb;
CREATE INDEX IF NOT EXISTS idx_child_quiz_required ON child_quiz_progress(child_id) WHERE quiz_required=TRUE;

-- Parent verification and approval extensions
ALTER TABLE parent_child_map ADD COLUMN IF NOT EXISTS verification_token VARCHAR(255);
ALTER TABLE parent_child_map ADD COLUMN IF NOT EXISTS approval_status VARCHAR(64) DEFAULT 'PENDING_APPROVAL';
ALTER TABLE parent_child_map ADD COLUMN IF NOT EXISTS is_token_used BOOLEAN DEFAULT FALSE;
ALTER TABLE parent_child_map ADD COLUMN IF NOT EXISTS parent_verified BOOLEAN DEFAULT FALSE;
ALTER TABLE parent_child_map ADD COLUMN IF NOT EXISTS parent_masked_id VARCHAR(64);
ALTER TABLE parent_child_map ADD COLUMN IF NOT EXISTS parent_id_type VARCHAR(64);
ALTER TABLE parent_child_map ADD COLUMN IF NOT EXISTS verified_parent_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL;
ALTER TABLE parent_child_map ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP;
ALTER TABLE parent_child_map ADD COLUMN IF NOT EXISTS approval_token_expires_at TIMESTAMP;


CREATE TABLE IF NOT EXISTS parent_verifications (
    verification_id SERIAL PRIMARY KEY,
    parent_user_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    child_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
    verification_provider VARCHAR(64) DEFAULT 'MOCK_CIVIC_ID',
    verification_status VARCHAR(64) DEFAULT 'PENDING',
    document_type VARCHAR(64),
    masked_id VARCHAR(64),
    consent_given BOOLEAN DEFAULT FALSE,
    consent_timestamp TIMESTAMP,
    verification_meta JSONB DEFAULT '{}'::jsonb,
    verified_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE parent_verifications ADD COLUMN IF NOT EXISTS child_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE;
ALTER TABLE parent_verifications ADD COLUMN IF NOT EXISTS verification_provider VARCHAR(64) DEFAULT 'MOCK_CIVIC_ID';
ALTER TABLE parent_verifications ADD COLUMN IF NOT EXISTS document_type VARCHAR(64);
ALTER TABLE parent_verifications ADD COLUMN IF NOT EXISTS consent_given BOOLEAN DEFAULT FALSE;
ALTER TABLE parent_verifications ADD COLUMN IF NOT EXISTS consent_timestamp TIMESTAMP;
ALTER TABLE parent_verifications ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP;




-- Missing column that process_child_decision() writes to when a parent
-- declines a pending child registration.
ALTER TABLE parent_child_map ADD COLUMN IF NOT EXISTS rejection_reason TEXT;

-- Feed-performance indexes: visible_posts()/active_stories() run several
-- correlated subqueries per row (like/comment counts, follow/block/mute
-- checks, skill/interest/ambition matches). These are needed once real
-- content (~1000+ posts) is loaded, not just for the current empty/demo DB.
CREATE INDEX IF NOT EXISTS idx_likes_post ON likes(post_id);
CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id) WHERE moderation_status='ALLOWED';
CREATE INDEX IF NOT EXISTS idx_followers_child_approved ON followers(child_id,following_child_id) WHERE approved=TRUE;
CREATE INDEX IF NOT EXISTS idx_blocked_blocker ON blocked_users(blocker_id);
CREATE INDEX IF NOT EXISTS idx_blocked_blocked ON blocked_users(blocked_id);
CREATE INDEX IF NOT EXISTS idx_muted_muter ON muted_users(muter_id);
CREATE INDEX IF NOT EXISTS idx_child_skills_child_approved ON child_skills(child_id) WHERE approved=TRUE;
CREATE INDEX IF NOT EXISTS idx_child_interests_child_approved ON child_interests(child_id) WHERE approved=TRUE;
CREATE INDEX IF NOT EXISTS idx_child_ambitions_child_approved ON child_ambitions(child_id) WHERE approved=TRUE;
CREATE INDEX IF NOT EXISTS idx_saved_posts_child ON saved_posts(child_id);
CREATE INDEX IF NOT EXISTS idx_story_views_post_child ON story_views(post_id,child_id);

CREATE TABLE IF NOT EXISTS recommendation_signals (
  signal_id BIGSERIAL PRIMARY KEY,
  child_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  source_type VARCHAR(20) NOT NULL CHECK(source_type IN ('SOCIAL','CURATED','CREATOR')),
  source_id BIGINT NOT NULL,
  signal VARCHAR(30) NOT NULL CHECK(signal IN (
    'INTEREST','REEL_COMPLETION','REEL_REPLAY','LIKE','SAVE','COMMENT',
    'SHARE','FOLLOW','SEARCH_CLICK','NOT_INTERESTED','HIDE','MUTE','BLOCK','REPORT'
  )),
  weight NUMERIC(8,3) NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_recommendation_signals_child_source
  ON recommendation_signals(child_id,source_type,source_id,created_at DESC);

-- AI & Safety Intelligence Extensions (K2-Horizon & Enhanced Learning)
ALTER TABLE moderation_events ADD COLUMN IF NOT EXISTS pii_detected BOOLEAN DEFAULT FALSE;
ALTER TABLE moderation_events ADD COLUMN IF NOT EXISTS grooming_risk_score NUMERIC(6,2) DEFAULT 0.0;
ALTER TABLE moderation_events ADD COLUMN IF NOT EXISTS ai_model VARCHAR(50);

ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS question_type VARCHAR(30) DEFAULT 'MULTIPLE_CHOICE';
ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS difficulty_level VARCHAR(20) DEFAULT 'MEDIUM';
ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS sub_topic VARCHAR(100);
ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS explanation TEXT;
ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS language VARCHAR(10) DEFAULT 'en';
ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS vocabulary_word VARCHAR(100);
ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS native_script VARCHAR(100);
ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS pronunciation_hint VARCHAR(100);

ALTER TABLE child_profiles ADD COLUMN IF NOT EXISTS grade_level VARCHAR(30) DEFAULT 'Grade 4';
ALTER TABLE child_profiles ADD COLUMN IF NOT EXISTS preferred_language VARCHAR(20) DEFAULT 'en';
ALTER TABLE child_profiles ADD COLUMN IF NOT EXISTS learning_languages TEXT[] DEFAULT ARRAY['kn', 'hi'];

CREATE TABLE IF NOT EXISTS child_personalized_quiz_pool (
  pool_id SERIAL PRIMARY KEY,
  child_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  quiz_id INTEGER NOT NULL REFERENCES quizzes(quiz_id) ON DELETE CASCADE,
  reason_for_selection VARCHAR(100),
  served BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(child_id, quiz_id)
);
CREATE INDEX IF NOT EXISTS idx_child_pool_unserved ON child_personalized_quiz_pool(child_id) WHERE served=FALSE;

CREATE TABLE IF NOT EXISTS child_vocabulary_progress (
  progress_id SERIAL PRIMARY KEY,
  child_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  word VARCHAR(100) NOT NULL,
  language VARCHAR(20) NOT NULL,
  times_seen INTEGER DEFAULT 1,
  times_correct INTEGER DEFAULT 0,
  last_tested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  next_review_due TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  mastery_level VARCHAR(20) DEFAULT 'LEARNING',
  UNIQUE(child_id, word, language)
);

CREATE TABLE IF NOT EXISTS parent_weekly_digests (
  digest_id SERIAL PRIMARY KEY,
  child_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  parent_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
  week_start_date DATE NOT NULL,
  headline VARCHAR(255),
  digest_data JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_parent_digests_child ON parent_weekly_digests(child_id, week_start_date DESC);

-- Phase 2: Direct Upload, Async Processing, and Manual Hashtags
ALTER TABLE posts ADD COLUMN IF NOT EXISTS processing_status VARCHAR(20) NOT NULL DEFAULT 'ALLOWED';
DO $$ BEGIN
  ALTER TABLE posts ADD CONSTRAINT posts_processing_status_check
    CHECK (processing_status IN ('UPLOADING','UPLOADED','PROCESSING','REVIEW','ALLOWED','BLOCKED','FAILED'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE posts ADD COLUMN IF NOT EXISTS source_media_path VARCHAR(500);
ALTER TABLE posts ADD COLUMN IF NOT EXISTS poster_path VARCHAR(500);
ALTER TABLE posts ADD COLUMN IF NOT EXISTS processing_error TEXT;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMP;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS processing_completed_at TIMESTAMP;
CREATE INDEX IF NOT EXISTS idx_posts_processing ON posts(processing_status,created_at DESC);

CREATE TABLE IF NOT EXISTS post_tags (
  tag_id BIGSERIAL PRIMARY KEY,
  post_id BIGINT NOT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
  tag VARCHAR(50) NOT NULL,
  normalized_tag VARCHAR(50) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(post_id, normalized_tag)
);
CREATE INDEX IF NOT EXISTS idx_post_tags_post ON post_tags(post_id);
CREATE INDEX IF NOT EXISTS idx_post_tags_normalized ON post_tags(normalized_tag);

CREATE TABLE IF NOT EXISTS upload_sessions (
  upload_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  child_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  object_key VARCHAR(500) NOT NULL UNIQUE,
  media_type VARCHAR(20) NOT NULL CHECK (media_type IN ('IMAGE','VIDEO','AUDIO')),
  kind VARCHAR(20) NOT NULL CHECK (kind IN ('POST','REEL','STORY')),
  expected_size_bytes BIGINT NOT NULL,
  mime_type VARCHAR(100) NOT NULL,
  extension VARCHAR(20) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','UPLOADED','CONSUMED','EXPIRED','CANCELLED')),
  expires_at TIMESTAMP NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  consumed_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_upload_sessions_child ON upload_sessions(child_id, status, created_at DESC);

-- Master Final Release: Post Location, Replay Protection & Curated Music
ALTER TABLE posts ADD COLUMN IF NOT EXISTS location_name VARCHAR(120);


CREATE TABLE IF NOT EXISTS curated_music (
  music_id SERIAL PRIMARY KEY,
  title VARCHAR(120) NOT NULL,
  artist VARCHAR(120) NOT NULL,
  category VARCHAR(60) NOT NULL DEFAULT 'Happy',
  audio_url TEXT NOT NULL,
  duration_seconds INTEGER NOT NULL DEFAULT 30,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO curated_music (title, artist, category, audio_url, duration_seconds)
VALUES
  ('Sunshine Whistle', 'LittleNet Studio', 'Happy', 'https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3?filename=sunshine-113069.mp3', 30),
  ('Playful Ukulele', 'FunKids Media', 'Acoustic', 'https://cdn.pixabay.com/download/audio/2022/03/15/audio_c8c8a73467.mp3?filename=ukulele-trip-version-60s-9893.mp3', 30),
  ('Lofi Study Beats', 'SafeChill', 'Learning', 'https://cdn.pixabay.com/download/audio/2022/01/18/audio_d0a13f69d2.mp3?filename=lofi-study-112191.mp3', 45),
  ('Silly Cartoon Bounce', 'ComedyKids', 'Comedy', 'https://cdn.pixabay.com/download/audio/2022/10/14/audio_9939f77c30.mp3?filename=funny-kids-123495.mp3', 25),
  ('Space Adventure', 'AstroSound', 'Sci-Fi', 'https://cdn.pixabay.com/download/audio/2021/08/04/audio_12b0c7443c.mp3?filename=space-adventure-6681.mp3', 35)
ON CONFLICT DO NOTHING;

ALTER TABLE posts ADD COLUMN IF NOT EXISTS story_music_id INTEGER REFERENCES curated_music(music_id) ON DELETE SET NULL;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS story_music_start INTEGER DEFAULT 0;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS story_music_duration INTEGER DEFAULT 30;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS story_music_title VARCHAR(120);
ALTER TABLE posts ADD COLUMN IF NOT EXISTS story_music_artist VARCHAR(120);
ALTER TABLE posts ADD COLUMN IF NOT EXISTS story_music_url TEXT;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS upload_id UUID REFERENCES upload_sessions(upload_id) ON DELETE SET NULL;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS processing_attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS max_processing_attempts INTEGER NOT NULL DEFAULT 3;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS last_attempt_at TIMESTAMPTZ;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS job_id VARCHAR(128);
ALTER TABLE posts ADD COLUMN IF NOT EXISTS processing_lease_token VARCHAR(64);
ALTER TABLE posts ADD COLUMN IF NOT EXISTS processing_lease_expires_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_posts_lease_expiry ON posts(processing_lease_expires_at)
  WHERE processing_status IN ('UPLOADED', 'PROCESSING');

CREATE TABLE IF NOT EXISTS parent_email_otps (
  user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
  code_hash TEXT NOT NULL,
  expires_at TIMESTAMP NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  verified_at TIMESTAMP
);

-- Media Delivery Abstraction: media_assets
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

-- Story Views Persistence
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

-- Mobile Push Notification Device Tokens
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

-- Mobile Bearer Token Revocations (Server-side Session Revocation)
CREATE TABLE IF NOT EXISTS mobile_token_revocations (
  token_hash VARCHAR(64) PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  revoked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_revoked_tokens_user ON mobile_token_revocations(user_id);

-- Semantic Candidate Retrieval & Item Embeddings
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS item_embeddings (
  embedding_id BIGSERIAL PRIMARY KEY,
  source_type VARCHAR(32) NOT NULL,
  source_id BIGINT NOT NULL,
  embedding vector(384),
  model_name VARCHAR(64) NOT NULL DEFAULT 'all-MiniLM-L6-v2',
  version INT NOT NULL DEFAULT 1,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(source_type, source_id, model_name, version)
);

CREATE INDEX IF NOT EXISTS idx_item_embeddings_source ON item_embeddings(source_type, source_id);

-- Performance Composite Indexes
CREATE INDEX IF NOT EXISTS idx_posts_feed_eligible ON posts(moderation_status, is_safe, is_story, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_posts_reels_eligible ON posts(moderation_status, is_safe, is_story, is_reel, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_recommendation_signals_child_src ON recommendation_signals(child_id, source_type, source_id);

-- Multi-device Session Revocation Support
ALTER TABLE users ADD COLUMN IF NOT EXISTS session_version INT NOT NULL DEFAULT 1;


-- Transactional email delivery lifecycle (provider acceptance != delivery).
CREATE TABLE IF NOT EXISTS email_delivery_events (
  event_id BIGSERIAL PRIMARY KEY,
  provider_message_id TEXT UNIQUE NOT NULL,
  recipient TEXT NOT NULL,
  provider VARCHAR(32) NOT NULL DEFAULT 'RESEND',
  email_type VARCHAR(40) NOT NULL DEFAULT 'TRANSACTIONAL',
  status VARCHAR(30) NOT NULL DEFAULT 'ACCEPTED'
    CHECK (status IN ('ACCEPTED','SENT','DELIVERED','DELIVERY_DELAYED','BOUNCED','SUPPRESSED','FAILED','COMPLAINED')),
  failure_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_event_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_email_delivery_recipient_status
  ON email_delivery_events(recipient, status, updated_at DESC);
