import sys, os
sys.path.insert(0, os.path.abspath('.'))
from dotenv import load_dotenv
load_dotenv('.env')
from database.connection import get_db_connection, fetch_all

def fix_supabase_advisor():
    conn = get_db_connection()
    conn.autocommit = True
    cur = conn.cursor()

    print("--- 1. ENABLING ROW LEVEL SECURITY (RLS) ON ALL PUBLIC TABLES ---")
    rls_tables = [
        "activity_logs", "admin_audit_logs", "blocked_users", "child_ambitions",
        "child_conversations", "child_interests", "child_messages", "child_profiles",
        "child_quiz_attempts", "child_quiz_progress", "child_skills", "child_time_limits",
        "child_usage_logs", "child_usage_sessions", "comments", "deleted_posts",
        "followers", "learning_challenge_attempts",
        "learning_challenges", "likes", "login_activity", "moderation_events",
        "moderation_reviews", "muted_users", "notifications", "parent_child_map",
        "parent_control_settings", "parent_notifications", "parent_quiz_settings",
        "parent_safety_settings", "parent_verifications", "posts", "quizzes",
        "reports", "saved_posts", "story_views", "user_preferences", "users"
    ]

    for tbl in rls_tables:
        try:
            cur.execute(f"ALTER TABLE public.{tbl} ENABLE ROW LEVEL SECURITY;")
            print(f"  ✓ Enabled RLS on {tbl}")
            
            # Add service_role policy if service_role exists in DB
            try:
                cur.execute(f"""
                    DO $$
                    BEGIN
                        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
                            IF NOT EXISTS (
                                SELECT 1 FROM pg_policies 
                                WHERE schemaname = 'public' AND tablename = '{tbl}' AND policyname = 'service_role_access'
                            ) THEN
                                EXECUTE 'CREATE POLICY service_role_access ON public.{tbl} FOR ALL TO service_role USING (true) WITH CHECK (true)';
                            END IF;
                        END IF;
                    END
                    $$;
                """)
            except Exception as pe:
                print(f"    (policy note for {tbl}: {pe})")
        except Exception as e:
            print(f"  ✗ Failed RLS on {tbl}: {e}")

    print("\n--- 2. SECURING SENSITIVE COLUMNS & TABLES ---")
    try:
        cur.execute("""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                    REVOKE ALL ON public.child_usage_sessions FROM anon;
                    REVOKE ALL ON public.parent_verifications FROM anon;
                    REVOKE ALL ON public.users FROM anon;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                    REVOKE ALL ON public.child_usage_sessions FROM authenticated;
                    REVOKE ALL ON public.parent_verifications FROM authenticated;
                END IF;
            END
            $$;
        """)
        print("  ✓ Revoked anon/authenticated permissions from sensitive tables")
    except Exception as e:
        print(f"  ✗ Error revoking permissions: {e}")

    print("\n--- 3. CREATING INDEXES FOR UNINDEXED FOREIGN KEYS ---")
    # Query all unindexed foreign keys dynamically and create indexes for them
    fk_query = """
    SELECT
        c.conrelid::regclass AS table_name,
        c.conname AS foreign_key_name,
        a.attname AS column_name
    FROM pg_constraint c
    JOIN pg_namespace n ON n.oid = c.connamespace
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
    WHERE c.contype = 'f'
      AND n.nspname = 'public'
      AND NOT EXISTS (
          SELECT 1
          FROM pg_index i
          WHERE i.indrelid = c.conrelid
            AND (i.indkey::int2[])[0:cardinality(c.conkey)-1] = c.conkey[0:cardinality(c.conkey)-1]
      )
    ORDER BY table_name, column_name;
    """
    cur.execute(fk_query)
    unindexed = cur.fetchall()
    print(f"Found {len(unindexed)} unindexed foreign key columns to index.")

    created = 0
    for row in unindexed:
        tbl = row['table_name']
        col = row['column_name']
        idx_name = f"idx_{tbl}_{col}".replace(".", "_").replace('"', '')
        try:
            cur.execute(f'CREATE INDEX IF NOT EXISTS "{idx_name}" ON {tbl} ("{col}");')
            created += 1
            print(f"  [OK] Created index {idx_name} on {tbl}({col})")
        except Exception as e:
            print(f"  [FAIL] Failed index {idx_name} on {tbl}({col}): {e}")

    cur.close()
    conn.close()
    print(f"\nSUCCESS: Enabled RLS on {len(rls_tables)} tables and created {created} foreign key indexes.")

if __name__ == "__main__":
    fix_supabase_advisor()
