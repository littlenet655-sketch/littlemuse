-- migrate:up
-- Curated creators are editorial personas. They deliberately do not reference
-- users/child_profiles and therefore cannot participate in child follows or DMs.
CREATE TABLE IF NOT EXISTS curated_creators (
  creator_id BIGSERIAL PRIMARY KEY,
  creator_key VARCHAR(64) NOT NULL UNIQUE,
  display_name VARCHAR(120) NOT NULL,
  username VARCHAR(64) NOT NULL UNIQUE,
  avatar_reference TEXT,
  bio TEXT,
  interest_vertical VARCHAR(64),
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO curated_creators(creator_key,display_name,username,interest_vertical) VALUES
 ('ananya_explores','Ananya Explorer','ananya_explores','Nature & Animals'),
 ('aarav_cooking','Chef Aarav','aarav_cooking','Culinary Arts & Food'),
 ('kabir_sports','Kabir Champion','kabir_sports','Sports'),
 ('maya_astronomy','Maya Sharma','maya_astronomy','Astronomy & Space'),
 ('sam_origami','Samantha Rao','sam_origami','Art & Paper Crafts'),
 ('leo_robotics','Leo D''Souza','leo_robotics','Robotics & Coding'),
 ('ait_star_student','AIT Star Student','ait_star_student',NULL),
 ('real_kid_alpha','Real Kid Alpha','real_kid_alpha',NULL),
 ('tagkid','Tag Kid','tagkid',NULL),
 ('prockid','Proc Kid','prockid',NULL),
 ('statuskid','Status Kid','statuskid',NULL),
 ('kid_hbndif','Little Kid','kid_hbndif',NULL),
 ('kid_wpzaxm','Little Kid','kid_wpzaxm',NULL),
 ('hkid_14','hkid_14 Name','hkid_14',NULL)
ON CONFLICT (creator_key) DO UPDATE SET
  display_name=EXCLUDED.display_name,
  username=EXCLUDED.username,
  interest_vertical=EXCLUDED.interest_vertical,
  updated_at=CURRENT_TIMESTAMP;

ALTER TABLE curated_content
  ADD COLUMN IF NOT EXISTS creator_id BIGINT REFERENCES curated_creators(creator_id);

-- Conservative deterministic backfill. Generic/ambiguous content uses the
-- neutral editorial persona rather than pretending to be a child account.
UPDATE curated_content cc
SET creator_id = cr.creator_id
FROM curated_creators cr
WHERE cc.creator_id IS NULL
  AND cr.creator_key = CASE
    WHEN LOWER(COALESCE(cc.title,'') || ' ' || COALESCE(cc.caption,'')) ~ '(recipe|cook|cooking|food|snack)' THEN 'aarav_cooking'
    WHEN LOWER(COALESCE(cc.title,'') || ' ' || COALESCE(cc.caption,'')) ~ '(football|sport|sports|fitness)' THEN 'kabir_sports'
    WHEN LOWER(COALESCE(cc.title,'') || ' ' || COALESCE(cc.caption,'')) ~ '(astronomy|space|planet|galaxy|telescope)' THEN 'maya_astronomy'
    WHEN LOWER(COALESCE(cc.title,'') || ' ' || COALESCE(cc.caption,'')) ~ '(origami|paper craft|paper folding)' THEN 'sam_origami'
    WHEN LOWER(COALESCE(cc.title,'') || ' ' || COALESCE(cc.caption,'')) ~ '(robot|robotics|coding|programming)' THEN 'leo_robotics'
    WHEN LOWER(COALESCE(cc.title,'') || ' ' || COALESCE(cc.caption,'')) ~ '(nature|animal|wildlife|forest|ocean)' THEN 'ananya_explores'
    ELSE 'ait_star_student'
  END;

CREATE INDEX IF NOT EXISTS idx_curated_content_creator_id ON curated_content(creator_id);

-- Polymorphic engagement is intentionally separate from social likes/saves so
-- curated content IDs can never collide with child post IDs.
CREATE TABLE IF NOT EXISTS content_reactions (
  child_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  source_type VARCHAR(16) NOT NULL CHECK(source_type IN ('CURATED')),
  source_id BIGINT NOT NULL,
  reaction_type VARCHAR(16) NOT NULL CHECK(reaction_type IN ('LIKE')),
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(child_id,source_type,source_id,reaction_type)
);
CREATE INDEX IF NOT EXISTS idx_content_reactions_source
  ON content_reactions(source_type,source_id,reaction_type);

CREATE TABLE IF NOT EXISTS content_saves (
  child_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  source_type VARCHAR(16) NOT NULL CHECK(source_type IN ('CURATED')),
  source_id BIGINT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(child_id,source_type,source_id)
);
CREATE INDEX IF NOT EXISTS idx_content_saves_source ON content_saves(source_type,source_id);

CREATE TABLE IF NOT EXISTS content_shares (
  share_id BIGSERIAL PRIMARY KEY,
  child_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  source_type VARCHAR(16) NOT NULL CHECK(source_type IN ('CURATED')),
  source_id BIGINT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_content_shares_source ON content_shares(source_type,source_id,created_at DESC);

-- migrate:down
DROP TABLE IF EXISTS content_shares;
DROP TABLE IF EXISTS content_saves;
DROP TABLE IF EXISTS content_reactions;
DROP INDEX IF EXISTS idx_curated_content_creator_id;
ALTER TABLE curated_content DROP COLUMN IF EXISTS creator_id;
DROP TABLE IF EXISTS curated_creators;
