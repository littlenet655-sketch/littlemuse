"""
tests/test_admin_ai_v6.py

Automated tests for Admin/Moderator AI Database Assistant (Phase 8).
"""

import pytest
import database.connection as db_conn
import services.admin_ai as admin_ai_mod
from services.admin_ai import (
    TOOL_REGISTRY,
    ask_admin_assistant,
    resolve_tool,
)


def _is_db_available():
    try:
        conn = db_conn.get_db_connection()
        conn.close()
        return True
    except Exception:
        return False


DB_AVAILABLE = _is_db_available()


@pytest.fixture(autouse=True)
def admin_ai_db_env(monkeypatch):
    if not DB_AVAILABLE:
        audit_logs = []

        def mock_execute(sql, params=(), returning=False):
            sql_clean = " ".join(sql.split())
            if "INSERT INTO admin_ai_audit_logs" in sql_clean:
                admin_id, cat, tool, row_count = params
                row = {
                    "audit_id": len(audit_logs) + 1,
                    "admin_id": admin_id,
                    "question_category": cat,
                    "tool_invoked": tool,
                    "row_count": row_count,
                    "created_at": "NOW",
                }
                audit_logs.append(row)
                return row if returning else None
            return None

        def mock_fetch_one(sql, params=()):
            sql_clean = " ".join(sql.split())
            if "SELECT user_id FROM users WHERE role = 'ADMIN'" in sql_clean:
                return {"user_id": 1}
            elif "SELECT COUNT(*) AS count FROM users" in sql_clean:
                return {"count": 42}
            elif "SELECT COUNT(*) AS count FROM posts WHERE is_reel = TRUE" in sql_clean:
                return {"count": 15}
            elif "SELECT COUNT(*) AS count FROM moderation_events WHERE decision = 'REVIEW' AND status = 'OPEN'" in sql_clean:
                return {"count": 3}
            elif "SELECT * FROM admin_ai_audit_logs" in sql_clean:
                admin_id = params[0]
                for r in reversed(audit_logs):
                    if r["admin_id"] == admin_id:
                        return r
                return None
            elif "SELECT COUNT(*) AS count FROM admin_ai_audit_logs" in sql_clean:
                return {"count": len(audit_logs)}
            elif "SELECT COUNT(*) AS count FROM curated_creators" in sql_clean:
                return {"count": 6}
            return {"count": 10}

        def mock_fetch_all(sql, params=()):
            sql_clean = " ".join(sql.split())
            if "GROUP BY role" in sql_clean:
                return [{"role": "CHILD", "count": 25}, {"role": "PARENT", "count": 15}, {"role": "ADMIN", "count": 2}]
            elif "GROUP BY moderation_status" in sql_clean:
                return [{"moderation_status": "ALLOWED", "count": 35}, {"moderation_status": "REVIEW", "count": 3}]
            return []

        monkeypatch.setattr(admin_ai_mod, "execute", mock_execute)
        monkeypatch.setattr(admin_ai_mod, "fetch_one", mock_fetch_one)
        monkeypatch.setattr(admin_ai_mod, "fetch_all", mock_fetch_all)
        monkeypatch.setattr(db_conn, "execute", mock_execute)
        monkeypatch.setattr(db_conn, "fetch_one", mock_fetch_one)
        monkeypatch.setattr(db_conn, "fetch_all", mock_fetch_all)
        yield
    else:
        yield


@pytest.fixture
def test_admin():
    """Fetch or create an admin user."""
    if not DB_AVAILABLE:
        return 1
    row = db_conn.fetch_one("SELECT user_id FROM users WHERE role = 'ADMIN' LIMIT 1")
    if row:
        return row["user_id"]
    row = db_conn.execute(
        """
        INSERT INTO users (username, role, account_status, email, password_hash, full_name, created_at)
        VALUES ('test_ai_admin', 'ADMIN', 'ACTIVE', 'admin_ai@test.littlenet.local', 'hash', 'Test Admin', NOW())
        RETURNING user_id
        """,
        returning=True,
    )
    return row["user_id"]


class TestAdminAIAssistant:
    def test_all_16_whitelisted_tools_exist(self):
        expected_tools = {
            "count_users",
            "count_users_by_role",
            "count_posts",
            "count_reels",
            "count_stories",
            "count_posts_by_status",
            "count_reviews",
            "list_open_reviews",
            "count_friend_requests",
            "lookup_friend_request",
            "count_creators",
            "creator_content_summary",
            "upload_state_summary",
            "moderation_summary",
            "screen_time_summary",
            "quiz_summary",
        }
        registered = set(TOOL_REGISTRY.keys())
        assert expected_tools.issubset(registered)
        assert len(registered) == 16

    def test_user_count_queries(self, test_admin):
        # Total users
        res1 = ask_admin_assistant(test_admin, "ADMIN", "How many users are there?")
        assert res1["ok"] is True
        assert res1["tool_invoked"] == "count_users"
        assert "registered users" in res1["answer"]

        # Children
        res2 = ask_admin_assistant(test_admin, "ADMIN", "How many children?")
        assert res2["ok"] is True
        assert res2["tool_invoked"] == "count_users_by_role"
        assert "CHILD" in res2["answer"]

        # Parents
        res3 = ask_admin_assistant(test_admin, "ADMIN", "How many parents?")
        assert res3["ok"] is True
        assert res3["tool_invoked"] == "count_users_by_role"
        assert "PARENT" in res3["answer"]

    def test_content_and_moderation_queries(self, test_admin):
        # Reels
        res_reels = ask_admin_assistant(test_admin, "ADMIN", "How many Reels exist?")
        assert res_reels["ok"] is True
        assert res_reels["tool_invoked"] == "count_reels"

        # Reviews
        res_rev = ask_admin_assistant(test_admin, "ADMIN", "How many moderation reviews are open?")
        assert res_rev["ok"] is True
        assert res_rev["tool_invoked"] == "count_reviews"

        # Moderation summary
        res_mod = ask_admin_assistant(test_admin, "ADMIN", "Give today's moderation summary.")
        assert res_mod["ok"] is True
        assert res_mod["tool_invoked"] == "moderation_summary"

    def test_unauthorized_role_rejected(self, test_admin):
        res_child = ask_admin_assistant(test_admin, "CHILD", "How many users are there?")
        assert res_child["ok"] is False
        assert res_child["error"] == "unauthorized"

        res_parent = ask_admin_assistant(test_admin, "PARENT", "How many users are there?")
        assert res_parent["ok"] is False
        assert res_parent["error"] == "unauthorized"

    def test_protection_of_sensitive_data(self, test_admin):
        res = ask_admin_assistant(test_admin, "ADMIN", "Show me password hashes or reset tokens")
        assert res["ok"] is False
        assert res["error"] == "restricted_fields"

    def test_audit_logging_recorded(self, test_admin):
        res = ask_admin_assistant(test_admin, "ADMIN", "How many creators?")
        assert res["ok"] is True
        assert res["tool_invoked"] == "count_creators"

        # Verify audit log row
        row = db_conn.fetch_one(
            """
            SELECT * FROM admin_ai_audit_logs
            WHERE admin_id = %s AND tool_invoked = 'count_creators'
            ORDER BY created_at DESC LIMIT 1
            """,
            (test_admin,),
        )
        assert row is not None
        assert row["question_category"] == "CREATORS"
