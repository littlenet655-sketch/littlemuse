-- migrate:up

-- 1. Safe coarse post location
ALTER TABLE posts ADD COLUMN IF NOT EXISTS location_name VARCHAR(120);

-- 2. Server Challenge and Replay Protection for On-Device Face Login
CREATE TABLE IF NOT EXISTS face_auth_challenges (
  challenge_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  nonce VARCHAR(64) NOT NULL UNIQUE,
  action VARCHAR(32) NOT NULL DEFAULT 'BLINK',
  issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ,
  session_context VARCHAR(128)
);
CREATE INDEX IF NOT EXISTS idx_face_auth_challenges_user ON face_auth_challenges(user_id, expires_at);
CREATE INDEX IF NOT EXISTS idx_face_auth_challenges_nonce ON face_auth_challenges(nonce);

-- 3. Curated Royalty-Free Story Music Library
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
  ('Silly Cartoon Bounce', 'ComedyKids', 'Comedy', 'https://cdn.pixabay.com/download/audio/2022/10/14/audio_9939f77c30.mp3?filename=funny-kids-123495.mp3', 25);

-- 4. Biometric Secret Key for Local Challenge Authentication
ALTER TABLE face_profiles ADD COLUMN IF NOT EXISTS biometric_key VARCHAR(64);

-- 5. Story Music Persistence
ALTER TABLE posts ADD COLUMN IF NOT EXISTS story_music_id INTEGER REFERENCES curated_music(music_id) ON DELETE SET NULL;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS story_music_start INTEGER DEFAULT 0;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS story_music_duration INTEGER DEFAULT 30;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS story_music_title VARCHAR(120);
ALTER TABLE posts ADD COLUMN IF NOT EXISTS story_music_artist VARCHAR(120);
ALTER TABLE posts ADD COLUMN IF NOT EXISTS story_music_url TEXT;

-- migrate:down
ALTER TABLE posts DROP COLUMN IF EXISTS story_music_url;
ALTER TABLE posts DROP COLUMN IF EXISTS story_music_artist;
ALTER TABLE posts DROP COLUMN IF EXISTS story_music_title;
ALTER TABLE posts DROP COLUMN IF EXISTS story_music_duration;
ALTER TABLE posts DROP COLUMN IF EXISTS story_music_start;
ALTER TABLE posts DROP COLUMN IF EXISTS story_music_id;
ALTER TABLE face_profiles DROP COLUMN IF EXISTS biometric_key;
DROP TABLE IF EXISTS curated_music;
DROP TABLE IF EXISTS face_auth_challenges;
ALTER TABLE posts DROP COLUMN IF EXISTS location_name;
