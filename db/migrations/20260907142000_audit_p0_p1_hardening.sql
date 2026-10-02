-- migrate:up
-- Security/runtime hardening from the 2026-09-07 independent audit.

-- LittleNet supports children through age 18. Keep quiz constraints aligned
-- with quiz.service.age_group(), which returns the 14-18 band for older teens.
ALTER TABLE quizzes DROP CONSTRAINT IF EXISTS quizzes_age_group_check;
ALTER TABLE quizzes
  ADD CONSTRAINT quizzes_age_group_check
  CHECK(age_group IN ('6-8','9-11','12-13','14-18'));

INSERT INTO quizzes(category,question,option_a,option_b,option_c,option_d,correct_answer,age_group) VALUES
('Digital Safety','A site asks you to install an unknown browser extension to claim a prize. What is safest?','Install it quickly','Check with a trusted adult and avoid unknown software','Disable antivirus first','Share the link with friends','Check with a trusted adult and avoid unknown software','14-18'),
('Digital Safety','Which is the strongest response to a login alert you do not recognize?','Ignore it','Change the password and review active sessions','Post the alert publicly','Reuse an older password','Change the password and review active sessions','14-18'),
('Digital Safety','What is phishing designed to do?','Improve Wi-Fi speed','Trick people into revealing sensitive information','Compress files','Update operating systems','Trick people into revealing sensitive information','14-18'),
('Digital Safety','A friend sends a shortened link with no context. What should you do?','Open it immediately','Verify with the friend before opening','Forward it to everyone','Enter your password if asked','Verify with the friend before opening','14-18'),
('Technology','What does two-factor authentication add to a password?','A second independent proof of identity','A shorter username','A public backup password','Automatic password sharing','A second independent proof of identity','14-18'),
('Technology','Which protocol normally protects web traffic in transit?','HTTP only','HTTPS/TLS','FTP','SMTP without TLS','HTTPS/TLS','14-18'),
('Science','Which molecule carries most genetic information in humans?','ATP','DNA','Glucose','Hemoglobin','DNA','14-18'),
('Science','What is the SI unit of force?','Joule','Newton','Pascal','Watt','Newton','14-18'),
('Math','Solve 2x + 5 = 19. What is x?','5','6','7','8','7','14-18'),
('Math','What is 25% of 360?','72','80','90','100','90','14-18'),
('General Knowledge','Which branch of government interprets laws in a constitutional system?','Judiciary','Executive only','Media','Private companies','Judiciary','14-18'),
('Digital Citizenship','Before posting a photo of another person, what is the best practice?','Post first and ask later','Ask for their consent','Remove your own name only','Send it to strangers','Ask for their consent','14-18')
ON CONFLICT DO NOTHING;

-- Compatibility for the child Notifications page. These generated columns
-- mirror the canonical media_path, eliminating undefined-column crashes while
-- keeping a single storage reference authoritative.
ALTER TABLE posts
  ADD COLUMN IF NOT EXISTS media_url VARCHAR(500)
  GENERATED ALWAYS AS (media_path) STORED;
ALTER TABLE posts
  ADD COLUMN IF NOT EXISTS thumbnail_url VARCHAR(500)
  GENERATED ALWAYS AS (media_path) STORED;

-- /uploads/<path> authorization performs equality lookups on these columns.
CREATE INDEX IF NOT EXISTS idx_posts_media_path ON posts(media_path) WHERE media_path IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_posts_story_music_path ON posts(story_music_path) WHERE story_music_path IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_messages_media_path ON child_messages(media_path) WHERE media_path IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_profiles_picture ON child_profiles(profile_picture) WHERE profile_picture IS NOT NULL;

-- A legacy HTTP shortcut must never turn a pending guardian-verification row
-- into an approved child mapping unless that child has a VERIFIED guardian
-- verification record for the approving parent.
CREATE OR REPLACE FUNCTION littlenet_guard_parent_child_approval()
RETURNS TRIGGER AS $$
DECLARE
  expected_parent INTEGER;
BEGIN
  IF OLD.approved=FALSE AND NEW.approved=TRUE
     AND OLD.approval_status IN ('PENDING_PARENT_VERIFICATION','AWAITING_PARENT_APPROVAL') THEN
    expected_parent=COALESCE(NEW.verified_parent_id,NEW.parent_id,OLD.verified_parent_id,OLD.parent_id);
    IF expected_parent IS NULL OR NOT EXISTS(
      SELECT 1 FROM parent_verifications pv
      WHERE pv.child_id=OLD.child_id
        AND pv.parent_user_id=expected_parent
        AND pv.verification_status='VERIFIED'
    ) THEN
      RAISE EXCEPTION 'verified guardian record required before child approval';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_littlenet_guard_parent_child_approval ON parent_child_map;
CREATE TRIGGER trg_littlenet_guard_parent_child_approval
BEFORE UPDATE OF approved ON parent_child_map
FOR EACH ROW EXECUTE FUNCTION littlenet_guard_parent_child_approval();

-- migrate:down
DROP TRIGGER IF EXISTS trg_littlenet_guard_parent_child_approval ON parent_child_map;
DROP FUNCTION IF EXISTS littlenet_guard_parent_child_approval();
DROP INDEX IF EXISTS idx_profiles_picture;
DROP INDEX IF EXISTS idx_messages_media_path;
DROP INDEX IF EXISTS idx_posts_story_music_path;
DROP INDEX IF EXISTS idx_posts_media_path;
ALTER TABLE posts DROP COLUMN IF EXISTS thumbnail_url;
ALTER TABLE posts DROP COLUMN IF EXISTS media_url;
ALTER TABLE quizzes DROP CONSTRAINT IF EXISTS quizzes_age_group_check;
ALTER TABLE quizzes
  ADD CONSTRAINT quizzes_age_group_check
  CHECK(age_group IN ('6-8','9-11','12-13'));
