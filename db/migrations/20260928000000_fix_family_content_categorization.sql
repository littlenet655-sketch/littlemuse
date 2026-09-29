-- migrate:up
-- Fix Bug 4: Family content appearing under Food category.
-- Content with cooking keywords (#cooking, recipe, etc.) was assigned to
-- 'aarav_cooking' (Culinary Arts & Food), but some of that content is
-- actually family-oriented (e.g., videos showing family members with
-- cooking hashtags). This recategorizes such content to the neutral
-- 'ait_star_student' persona.
--
-- The match looks for family indicators in title/caption alongside the
-- cooking keywords that triggered the original assignment.

UPDATE curated_content cc
SET creator_id = (SELECT creator_id FROM curated_creators WHERE creator_key = 'ait_star_student')
WHERE cc.creator_id = (SELECT creator_id FROM curated_creators WHERE creator_key = 'aarav_cooking')
  AND LOWER(COALESCE(cc.title,'') || ' ' || COALESCE(cc.caption,'')) ~
      '(family|grandfather|grandmother|grandpa|grandma|mom\y|dad\y|mother|father|sister|brother|uncle|aunt|cousin)';

-- migrate:down
-- Cannot reliably reverse: the original creator_key is lost.
-- Manual review required if rollback is needed.
SELECT 1;
