"""Reconcile LittleMuse's known legacy dbmate drift on an isolated Neon branch.

Uses the tracked migration SQL, never tools/init_db.py. Run --plan first, then
--apply on the audit clone. Repeat on a backed-up LittleMuse release branch.
The old production branch is explicitly refused.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import psycopg2
from psycopg2 import sql

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "steep-silence-70924571"
PRODUCTION = "br-fancy-cell-aeynnrbq"
AUDIT = "br-dry-rain-ae90sqqs"
FIRST_PENDING = "20260908195500"
MIGRATIONS = sorted((ROOT / "db/migrations").glob("[0-9]*.sql"))
CLASSIFICATION = {
    "20260908195500": "A",  # Curated schema, indexes, trigger and category seeds exist.
    "20260909120000": "C",
    "20260910231500": "A",  # Story/music and face objects exist; face is later removed.
    "20260911153000": "C",
    "20260911230000": "B",  # All keys exist; idempotent update restores exact seed content.
    "20260912235000": "B",  # Old account status CHECK lacks DEACTIVATED.
    "20260913000000": "B",  # Face hardening is superseded; post columns/indexes absent.
    "20260913010000": "C",
    "20260920000000": "B",  # story_views exists, new columns and other tables absent.
    "20260920020000": "C",
    "20260920021000": "C",
    "20260920093500": "C",
    "20260920151500": "C",
    "20260920160000": "C",  # Added, then removed by 20260922000001.
    "20260921000000": "A",  # Password reset fallback already made exact table.
    "20260921000100": "B",  # Five duplicate music pairs need deduplication.
    "20260922000000": "C",
    "20260922000001": "C",  # Intentional isolated-branch face removal.
    "20260922000002": "C",
    "20260922000003": "C",
}
CORE_KEYS = {
    "users": ("user_id", "role", "account_status"),
    "posts": ("post_id", "child_id", "media_path", "moderation_status"),
    "child_messages": ("child_message_id", "conversation_id", "sender_child_id", "receiver_child_id"),
    "comments": ("comment_id", "post_id", "child_id"),
    "followers": ("follower_id", "child_id", "following_child_id", "approved"),
    "parent_child_map": ("map_id", "child_id", "parent_id", "approved"),
}


def connection(branch: str):
    if branch == PRODUCTION:
        raise SystemExit("Refusing old production branch")
    cli = shutil.which("neon.cmd" if os.name == "nt" else "neon")
    if not cli:
        raise SystemExit("Authenticated Neon CLI is required")
    branches = json.loads(subprocess.run(
        [cli, "branches", "list", "--project-id", PROJECT, "--output", "json"],
        capture_output=True, text=True, check=True,
    ).stdout)
    selected = next((row for row in branches if row["id"] == branch), None)
    if not selected or (branch != AUDIT and not selected["name"].startswith("littlemuse-release-")):
        raise SystemExit("Branch must be the named audit clone or a dedicated LittleMuse release branch")
    url = subprocess.run(
        [cli, "connection-string", branch, "--project-id", PROJECT,
         "--database-name", "neondb", "--output", "json"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if "-pooler" in url.split("@")[-1].split("/")[0]:
        raise SystemExit("Migrations require a direct Neon endpoint")
    return psycopg2.connect(url), selected


def snapshot(cur):
    result = {}
    for table, columns in CORE_KEYS.items():
        query = sql.SQL("SELECT {} FROM {} ORDER BY 1").format(
            sql.SQL(",").join(map(sql.Identifier, columns)), sql.Identifier(table)
        )
        cur.execute(query)
        rows = cur.fetchall()
        encoded = json.dumps(rows, default=str, separators=(",", ":")).encode()
        result[table] = {"count": len(rows), "sha256": hashlib.sha256(encoded).hexdigest()}
    return result


def exists(cur, kind, name):
    if kind == "table":
        cur.execute("SELECT to_regclass(%s) IS NOT NULL", ("public." + name,))
    elif kind == "column":
        table, column = name.split(".")
        cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name=%s AND column_name=%s)", (table, column))
    else:
        cur.execute("SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=%s)", (name,))
    return cur.fetchone()[0]


def verify_existing(cur, version):
    expected = {
        "20260908195500": {
            "table": "content_categories curated_media_assets curated_content hashtags curated_content_hashtags content_impressions feed_sessions feed_session_items",
            "index": "ux_hashtags_lower idx_curated_assets_allowed idx_curated_content_feed idx_curated_hashtag_lookup idx_content_impressions_recent idx_feed_sessions_child idx_feed_session_items_source",
        },
        "20260910231500": {
            "table": "face_auth_challenges curated_music",
            "column": "posts.location_name face_profiles.biometric_key posts.story_music_id posts.story_music_start posts.story_music_duration posts.story_music_title posts.story_music_artist posts.story_music_url",
            "index": "idx_face_auth_challenges_user idx_face_auth_challenges_nonce",
        },
        "20260921000000": {
            "table": "password_reset_otps",
            "column": "password_reset_otps.user_id password_reset_otps.code_hash password_reset_otps.expires_at password_reset_otps.attempts password_reset_otps.sent_at",
        },
    }[version]
    missing = [name for kind, names in expected.items() for name in names.split() if not exists(cur, kind, name)]
    columns = {
        "20260908195500": {
            "content_categories": "category_id slug display_name is_educational active created_at",
            "curated_media_assets": "asset_id dataset_version source_row_id archive_file original_filename sha256 media_type original_object_key delivery_object_key poster_object_key thumbnail_object_key mime_type width height duration_seconds file_size_bytes moderation_status is_safe safety_score adult_score violence_score weapon_score toxicity_score moderation_reason created_at updated_at",
            "curated_content": "content_id asset_id category_id title caption audience_age_group min_age max_age is_reel is_story destination_tab publish_status editorial_weight published_at created_at updated_at",
            "hashtags": "hashtag_id tag created_at",
            "curated_content_hashtags": "content_id hashtag_id",
            "content_impressions": "impression_id child_id source_type source_id surface shown_at watched_ms completed liked saved",
            "feed_sessions": "session_id child_id surface created_at expires_at",
            "feed_session_items": "session_id position source_type source_id category_slug rank_score",
        },
        "20260910231500": {
            "face_auth_challenges": "challenge_id user_id nonce action issued_at expires_at used_at session_context",
            "curated_music": "music_id title artist category audio_url duration_seconds is_active created_at",
        },
        "20260921000000": {
            "password_reset_otps": "user_id code_hash expires_at attempts sent_at",
        },
    }[version]
    missing.extend(f"{table}.{column}" for table, names in columns.items() for column in names.split()
                   if not exists(cur, "column", f"{table}.{column}"))
    if missing:
        raise RuntimeError(f"{version} classified A but missing: {missing}")
    constraints = {
        "20260908195500": "content_categories_pkey content_categories_slug_key content_categories_display_name_key curated_media_assets_pkey curated_media_assets_sha256_key curated_media_assets_original_object_key_key curated_media_assets_delivery_object_key_key curated_media_assets_dataset_version_source_row_id_key curated_content_pkey curated_content_asset_id_fkey curated_content_category_id_fkey curated_content_asset_id_key curated_content_hashtags_pkey content_impressions_pkey content_impressions_child_id_fkey feed_sessions_pkey feed_session_items_pkey feed_session_items_session_id_source_type_source_id_key",
        "20260910231500": "face_auth_challenges_pkey face_auth_challenges_nonce_key face_auth_challenges_user_id_fkey curated_music_pkey",
        "20260921000000": "password_reset_otps_pkey password_reset_otps_user_id_fkey password_reset_otps_attempts_check",
    }[version].split()
    cur.execute("SELECT conname FROM pg_constraint WHERE conname = ANY(%s)", (constraints,))
    found = {row[0] for row in cur.fetchall()}
    if set(constraints) - found:
        raise RuntimeError(f"{version} classified A but missing constraints: {sorted(set(constraints) - found)}")
    if version == "20260908195500":
        cur.execute("SELECT count(*) FROM content_categories WHERE slug IN ('family','animals','crafts','gardening','cooking')")
        if cur.fetchone()[0] != 5:
            raise RuntimeError("Curated category seeds incomplete")
        cur.execute("SELECT count(*) FROM pg_trigger WHERE tgname='trg_validate_curated_publish' AND NOT tgisinternal")
        if cur.fetchone()[0] != 1:
            raise RuntimeError("Curated publication trigger missing")
        cur.execute("SELECT count(*) FROM pg_proc WHERE proname='littlenet_validate_curated_publish'")
        if cur.fetchone()[0] != 1:
            raise RuntimeError("Curated publication function missing")
    if version == "20260910231500":
        cur.execute("SELECT count(DISTINCT title) FROM curated_music WHERE title IN ('Sunshine Whistle','Playful Ukulele','Lofi Study Beats','Silly Cartoon Bounce')")
        if cur.fetchone()[0] != 4:
            raise RuntimeError("Curated music seeds incomplete")


def migration_up(path):
    body = path.read_text(encoding="utf-8").split("-- migrate:up", 1)[1].split("-- migrate:down", 1)[0]
    if path.name.startswith("20260913000000"):
        # Face constraints are superseded by the tracked removal migration.
        # Keep source-path dedup and processing columns/indexes from section 3.
        body = body.split("-- 3. Add durable", 1)[1]
        body = "-- 3. Add durable" + body
    return body


def verify_final(cur):
    tables = "media_assets user_device_tokens email_delivery_events moderation_signal_cache chat_typing login_throttle password_reset_otps recommendation_signals feed_sessions feed_session_items upload_sessions media_delete_outbox".split()
    columns = "posts.upload_id posts.processing_attempts posts.max_processing_attempts posts.processing_lease_token posts.processing_lease_expires_at content_impressions.replay_count story_views.first_viewed_at story_views.last_viewed_at story_views.completion_ratio".split()
    for kind, names in (("table", tables), ("column", columns)):
        missing = [name for name in names if not exists(cur, kind, name)]
        if missing:
            raise RuntimeError(f"Missing final {kind}: {missing}")
    for name in ("face_profiles", "face_auth_challenges", "face_login_attempts"):
        if exists(cur, "table", name):
            raise RuntimeError(f"Face table remains: {name}")
    for name in ("child_profiles.face_enrollment_skipped", "parent_verifications.liveness_status", "parent_verifications.face_match_status"):
        if exists(cur, "column", name):
            raise RuntimeError(f"Face column remains: {name}")
    cur.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='users_account_status_check'")
    if "DEACTIVATED" not in str(cur.fetchone()):
        raise RuntimeError("DEACTIVATED account status is not permitted")
    indexes = "idx_posts_upload_id_uniq idx_posts_source_media_path_uniq idx_posts_lease_expiry idx_media_assets_post_id idx_media_assets_playback_id idx_story_views_post_child idx_user_device_tokens_active idx_email_delivery_recipient_status idx_content_impressions_child_shown idx_feed_sessions_child_exp idx_recommendation_signals_child_type_recent idx_moderation_signal_cache_recent idx_chat_typing_updated_at".split()
    missing = [name for name in indexes if not exists(cur, "index", name)]
    if missing:
        raise RuntimeError(f"Missing final indexes: {missing}")
    cur.execute("SELECT count(*) FROM pg_constraint WHERE conname='uq_push_token_owner'")
    if cur.fetchone()[0] != 1:
        raise RuntimeError("Push tokens lack the single-owner constraint")
    cur.execute("SELECT age_group,count(*) FROM quizzes GROUP BY age_group")
    if any(count < 54 for _, count in cur.fetchall()):
        raise RuntimeError("Onboarding safety quiz bank incomplete")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    conn, branch = connection(args.branch)
    try:
        cur = conn.cursor()
        cur.execute("SELECT version FROM schema_migrations ORDER BY version")
        recorded = {str(row[0]) for row in cur.fetchall()}
        before = snapshot(cur)
        print(json.dumps({"branch": branch["name"], "id": branch["id"], "mode": "apply" if args.apply else "plan", "before": before}, sort_keys=True))
        pending = [path for path in MIGRATIONS if path.name[:14] >= FIRST_PENDING and path.name[:14] not in recorded]
        if {p.name[:14] for p in pending} != set(CLASSIFICATION) - recorded:
            raise RuntimeError("Migration set changed; review the reconciliation plan")
        for path in pending:
            version = path.name[:14]
            classification = CLASSIFICATION[version]
            if classification == "A":
                verify_existing(cur, version)
            print(version, classification, path.name)
        if not pending:
            verify_final(cur)
            print("final_schema verified")
        conn.rollback()
        if not args.apply:
            return
        for path in pending:
            version = path.name[:14]
            with conn:
                with conn.cursor() as cur:
                    if CLASSIFICATION[version] != "A":
                        cur.execute(migration_up(path))
                    else:
                        verify_existing(cur, version)
                    cur.execute("INSERT INTO schema_migrations(version) VALUES(%s)", (version,))
            print("reconciled", version)
        with conn.cursor() as cur:
            verify_final(cur)
            after = snapshot(cur)
            cur.execute("SELECT version FROM schema_migrations")
            versions = {str(row[0]) for row in cur.fetchall()}
        if before != after or not set(CLASSIFICATION).issubset(versions):
            raise RuntimeError("Core data preservation or migration history check failed")
        print(json.dumps({"final_schema": "verified", "core_data_preserved": True, "after": after}, sort_keys=True))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
