-- migrate:up
-- LittleNet adopted dbmate after the existing schema/upgrade SQL had already
-- been deployed to live/demo databases. This no-op establishes a safe version
-- boundary; all schema changes created after this point belong in db/migrations.
SELECT 1;

-- migrate:down
-- Adoption marker only; rolling it back must not destroy existing LittleNet data.
SELECT 1;
