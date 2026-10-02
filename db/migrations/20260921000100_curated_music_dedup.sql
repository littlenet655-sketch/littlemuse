-- migrate:up
-- The curated story-music library was seeded twice with overlapping rows:
-- database/upgrade.sql (legacy bootstrap, 5 tracks) runs before dbmate on
-- fresh databases, and 20260910231500_master_final_release.sql then inserted
-- 4 of the same tracks without ON CONFLICT handling. Remove the duplicates,
-- keeping the earliest row per (title, artist), then guard against recurrence.
DELETE FROM curated_music a
USING curated_music b
WHERE a.music_id > b.music_id
  AND a.title = b.title
  AND a.artist = b.artist;

DO $$ BEGIN
  ALTER TABLE curated_music
    ADD CONSTRAINT curated_music_title_artist_key UNIQUE (title, artist);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- migrate:down
ALTER TABLE curated_music DROP CONSTRAINT IF EXISTS curated_music_title_artist_key;
-- The data dedup is intentionally not reversed: re-creating duplicate seed
-- rows would corrupt the story-music picker again.
