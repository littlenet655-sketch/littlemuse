"""
services/admin_ai.py

Admin / Moderator AI Database Assistant for LittleNet.
Features:
- Safe read-only natural language database assistant for Admins & Moderators.
- Whitelisted, parameterized SELECT-only analytics tools registry.
- STRICTLY ZERO arbitrary SQL execution.
- Role-protected: ADMIN and MODERATOR only.
- Privacy & security: strictly no password hashes, reset tokens, OTPs, session tokens, or private chat text.
- Comprehensive audit logging in admin_ai_audit_logs.
- Offline deterministic intent fallback for robust local test verification.
"""

import json
import logging
import os
import re
import time
from typing import Dict, Any, List, Optional, Tuple, Callable

import requests
from database.connection import execute, fetch_all, fetch_one
from services.ai.circuit_breaker import CircuitBreaker, CircuitBreakerOpenException

logger = logging.getLogger("littlenet.admin_ai")

_k2_admin_breaker = CircuitBreaker("k2_admin_ai", failure_threshold=3, reset_timeout=30.0)

# =====================================================================
# 1. WHITELISTED READ-ONLY TOOL REGISTRY (ZERO ARBITRARY SQL)
# =====================================================================

TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {}


def register_tool(name: str, description: str, category: str):
    def decorator(fn: Callable):
        TOOL_REGISTRY[name] = {
            "name": name,
            "description": description,
            "category": category,
            "fn": fn,
        }
        return fn
    return decorator


@register_tool("count_users", "Count total registered users by role", "USERS")
def tool_count_users() -> Dict[str, Any]:
    rows = fetch_all("SELECT role, COUNT(*) AS count FROM users GROUP BY role ORDER BY count DESC")
    total = sum(r["count"] for r in rows)
    by_role = {r["role"]: r["count"] for r in rows}
    return {"total_users": total, "by_role": by_role}


@register_tool("count_users_by_role", "Count users for a specific role (CHILD, PARENT, ADMIN)", "USERS")
def tool_count_users_by_role(role: str) -> Dict[str, Any]:
    role_clean = str(role).strip().upper()
    row = fetch_one("SELECT COUNT(*) AS count FROM users WHERE role = %s", (role_clean,))
    return {"role": role_clean, "count": int(row["count"]) if row else 0}


@register_tool("count_posts", "Count total approved posts in LittleNet", "POSTS")
def tool_count_posts() -> Dict[str, Any]:
    row = fetch_one("SELECT COUNT(*) AS count FROM posts WHERE moderation_status = 'APPROVED'")
    return {"approved_posts": int(row["count"]) if row else 0}


@register_tool("count_reels", "Count active approved video Reels", "REELS")
def tool_count_reels() -> Dict[str, Any]:
    row = fetch_one("SELECT COUNT(*) AS count FROM posts WHERE is_reel = TRUE AND moderation_status = 'APPROVED'")
    return {"active_reels": int(row["count"]) if row else 0}


@register_tool("count_stories", "Count active 24-hour Stories", "STORIES")
def tool_count_stories() -> Dict[str, Any]:
    row = fetch_one(
        "SELECT COUNT(*) AS count FROM posts WHERE is_story = TRUE AND moderation_status = 'APPROVED' AND created_at >= NOW() - INTERVAL '24 hours'"
    )
    return {"active_stories": int(row["count"]) if row else 0}


@register_tool("count_posts_by_status", "Count posts grouped by moderation/workflow status", "POSTS")
def tool_count_posts_by_status() -> Dict[str, Any]:
    rows = fetch_all("SELECT moderation_status, COUNT(*) AS count FROM posts GROUP BY moderation_status ORDER BY count DESC")
    return {"posts_by_status": {r["moderation_status"]: r["count"] for r in rows}}


@register_tool("count_reviews", "Count open parent review escalation events", "MODERATION")
def tool_count_reviews() -> Dict[str, Any]:
    row = fetch_one("SELECT COUNT(*) AS count FROM moderation_events WHERE decision = 'REVIEW' AND status = 'OPEN'")
    return {"open_parent_reviews": int(row["count"]) if row else 0}


@register_tool("list_open_reviews", "List recent open parent reviews for moderation inspection", "MODERATION")
def tool_list_open_reviews(limit: int = 5) -> Dict[str, Any]:
    lim = max(1, min(int(limit), 20))
    rows = fetch_all(
        """
        SELECT event_id, child_id, reason AS reason_category, created_at
        FROM moderation_events
        WHERE decision = 'REVIEW' AND status = 'OPEN'
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (lim,),
    )
    return {
        "count": len(rows),
        "reviews": [
            {
                "event_id": r["event_id"],
                "child_id": r["child_id"],
                "reason_category": r["reason_category"],
                "created_at": r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"]),
            }
            for r in rows
        ],
    }


@register_tool("count_friend_requests", "Summary of friend request states across LittleNet", "SOCIAL")
def tool_count_friend_requests() -> Dict[str, Any]:
    rows = fetch_all("SELECT approval_stage, COUNT(*) AS count FROM followers GROUP BY approval_stage ORDER BY count DESC")
    return {"friend_requests_by_state": {r["approval_stage"]: r["count"] for r in rows}}


@register_tool("lookup_friend_request", "Lookup friend requests for a specific child username", "SOCIAL")
def tool_lookup_friend_request(username: str) -> Dict[str, Any]:
    uname = str(username).strip().lower()
    target = fetch_one("SELECT user_id, username FROM users WHERE LOWER(username) = %s AND role = 'CHILD'", (uname,))
    if not target:
        return {"found": False, "message": f"Child user '{username}' not found."}

    cid = target["user_id"]
    rows = fetch_all(
        """
        SELECT f.follower_id, u.username AS peer_username, f.approval_stage, f.created_at
        FROM followers f
        JOIN users u ON u.user_id = f.child_id
        WHERE f.following_child_id = %s
        ORDER BY f.created_at DESC
        LIMIT 10
        """,
        (cid,),
    )
    return {
        "found": True,
        "target_child": target["username"],
        "relationships": [
            {
                "peer_username": r["peer_username"],
                "state": r["approval_stage"],
                "created_at": r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"]),
            }
            for r in rows
        ],
    }


@register_tool("count_creators", "Count active curated educational creators", "CREATORS")
def tool_count_creators() -> Dict[str, Any]:
    row = fetch_one("SELECT COUNT(*) AS count FROM curated_creators WHERE active = TRUE")
    return {"active_creators": int(row["count"]) if row else 0}


@register_tool("creator_content_summary", "Summary of curated creators and their published content", "CREATORS")
def tool_creator_content_summary() -> Dict[str, Any]:
    rows = fetch_all(
        """
        SELECT c.creator_id, c.username, c.display_name, c.interest_vertical,
               (SELECT COUNT(*) FROM posts p WHERE p.curated_creator_id = c.creator_id AND p.status = 'APPROVED') AS approved_posts,
               (SELECT COUNT(*) FROM child_creator_follows f WHERE f.creator_id = c.creator_id AND f.active = TRUE) AS followers
        FROM curated_creators c
        WHERE c.active = TRUE
        ORDER BY c.creator_id ASC
        LIMIT 15
        """
    )
    return {
        "creators_count": len(rows),
        "creators": [
            {
                "id": r["creator_id"],
                "name": r["display_name"],
                "username": r["username"],
                "topic": r["interest_vertical"],
                "posts": int(r["approved_posts"]),
                "followers": int(r["followers"]),
            }
            for r in rows
        ],
    }


@register_tool("upload_state_summary", "Summary of upload session states (PROCESSING, CONSUMED, FAILED)", "UPLOADS")
def tool_upload_state_summary() -> Dict[str, Any]:
    rows = fetch_all("SELECT status, COUNT(*) AS count FROM upload_sessions GROUP BY status ORDER BY count DESC")
    return {"upload_sessions": {r["status"]: r["count"] for r in rows}}


@register_tool("moderation_summary", "High-level summary of moderation workload and safety outcomes", "MODERATION")
def tool_moderation_summary() -> Dict[str, Any]:
    post_statuses = fetch_all("SELECT moderation_status, COUNT(*) AS count FROM posts GROUP BY moderation_status")
    open_rev = fetch_one("SELECT COUNT(*) AS count FROM moderation_events WHERE decision = 'REVIEW' AND status = 'OPEN'")
    audit_today = fetch_one("SELECT COUNT(*) AS count FROM admin_ai_audit_logs WHERE created_at >= NOW() - INTERVAL '24 hours'")
    return {
        "posts_by_status": {r["moderation_status"]: r["count"] for r in post_statuses},
        "open_parent_reviews": int(open_rev["count"]) if open_rev else 0,
        "moderation_actions_24h": int(audit_today["count"]) if audit_today else 0,
    }


@register_tool("screen_time_summary", "Aggregated child screen time statistics", "SAFETY")
def tool_screen_time_summary() -> Dict[str, Any]:
    row = fetch_one(
        """
        SELECT COUNT(DISTINCT child_id) AS active_children,
               COALESCE(AVG(screen_time_seconds) / 60.0, 0.0) AS avg_daily_minutes,
               COALESCE(MAX(screen_time_seconds) / 60.0, 0.0) AS max_daily_minutes
        FROM child_screen_time_records
        WHERE record_date >= CURRENT_DATE - 7
        """
    )
    return {
        "reporting_period": "past_7_days",
        "active_children_tracked": int(row["active_children"]) if row else 0,
        "avg_daily_screen_time_minutes": round(float(row["avg_daily_minutes"]), 1) if row else 0.0,
        "max_daily_screen_time_minutes": round(float(row["max_daily_minutes"]), 1) if row else 0.0,
    }


@register_tool("quiz_summary", "Aggregated learning and safety quiz statistics", "LEARNING")
def tool_quiz_summary() -> Dict[str, Any]:
    attempts = fetch_one("SELECT COUNT(*) AS count FROM child_quiz_attempts WHERE created_at >= NOW() - INTERVAL '7 days'")
    passed = fetch_one("SELECT COUNT(*) AS count FROM child_quiz_attempts WHERE score >= 70 AND created_at >= NOW() - INTERVAL '7 days'")
    tot = int(attempts["count"]) if attempts else 0
    pas = int(passed["count"]) if passed else 0
    rate = round((pas / tot) * 100.0, 1) if tot > 0 else 0.0
    return {
        "reporting_period": "past_7_days",
        "total_quiz_attempts": tot,
        "passed_quiz_attempts": pas,
        "pass_rate_pct": rate,
    }


# =====================================================================
# 2. INTENT CLASSIFICATION & DISPATCH
# =====================================================================

DETERMINISTIC_RULES = [
    (re.compile(r"\b(?:how many users|count users|total users|user count)\b", re.I), "count_users", {}),
    (re.compile(r"\b(?:how many children|child count|count children|how many kids)\b", re.I), "count_users_by_role", {"role": "CHILD"}),
    (re.compile(r"\b(?:how many parents|parent count|count parents)\b", re.I), "count_users_by_role", {"role": "PARENT"}),
    (re.compile(r"\b(?:how many creators|creator count|count creators)\b", re.I), "count_creators", {}),
    (re.compile(r"\b(?:how many reels|active reels|reel count)\b", re.I), "count_reels", {}),
    (re.compile(r"\b(?:how many stories|active stories|story count)\b", re.I), "count_stories", {}),
    (re.compile(r"\b(?:how many posts|post count|posts by status)\b", re.I), "count_posts_by_status", {}),
    (re.compile(r"\b(?:blocked posts|how many posts were blocked|rejected posts)\b", re.I), "count_posts_by_status", {}),
    (re.compile(r"\b(?:how many moderation reviews|open reviews|pending reviews)\b", re.I), "count_reviews", {}),
    (re.compile(r"\b(?:show (?:open|pending) reviews|list (?:open|pending) reviews)\b", re.I), "list_open_reviews", {"limit": 5}),
    (re.compile(r"\b(?:friend requests|friendship approvals|pending friendship)\b", re.I), "count_friend_requests", {}),
    (re.compile(r"\bwho sent (?:a )?friend request to (\w+)\b", re.I), "lookup_friend_request", None),
    (re.compile(r"\b(?:failed uploads|upload state|upload sessions)\b", re.I), "upload_state_summary", {}),
    (re.compile(r"\b(?:moderation summary|today's moderation|safety summary)\b", re.I), "moderation_summary", {}),
    (re.compile(r"\b(?:screen time|screen time summary|average screen time)\b", re.I), "screen_time_summary", {}),
    (re.compile(r"\b(?:quiz summary|quiz stats|quiz attempts)\b", re.I), "quiz_summary", {}),
    (re.compile(r"\b(?:creators summary|creator content)\b", re.I), "creator_content_summary", {}),
]


def resolve_tool(question: str) -> Tuple[Optional[str], Dict[str, Any]]:
    """Resolve user question to a whitelisted tool and parameters."""
    clean = question.strip()
    for pattern, tool_name, params in DETERMINISTIC_RULES:
        m = pattern.search(clean)
        if m:
            if params is None and tool_name == "lookup_friend_request":
                return tool_name, {"username": m.group(1)}
            return tool_name, dict(params)

    # If no deterministic rule matched, try K2 Horizon tool selector
    return _k2_select_tool(clean)


def _k2_select_tool(question: str) -> Tuple[Optional[str], Dict[str, Any]]:
    """Use K2 Horizon LLM to choose from whitelisted tool catalog."""
    base_url = os.environ.get("K2_HORIZON_BASE_URL", "https://api.ifm.ai/v1").rstrip("/")
    api_key = os.environ.get("K2_HORIZON_API_KEY", "").strip()
    model = os.environ.get("K2_HORIZON_MODEL", "IFM/K2-Horizon-375B-A23B")

    if not api_key or not base_url or os.environ.get("K2_HORIZON_ENABLED", "true").lower() not in ("true", "1", "yes"):
        return None, {}

    tool_descriptions = [f"- {t['name']}: {t['description']}" for t in TOOL_REGISTRY.values()]
    catalog_str = "\n".join(tool_descriptions)

    system_prompt = (
        "You are an AI tool dispatcher for the LittleNet Admin Assistant. "
        "Available whitelisted read-only analytics tools:\n"
        f"{catalog_str}\n\n"
        "Return ONLY a JSON object: {\"tool\": \"<tool_name>\", \"params\": {}} or {\"tool\": null, \"params\": {}} if no tool matches. "
        "DO NOT write SQL. DO NOT execute commands. Only pick an exact tool name from the list."
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Question: {question}"},
        ],
        "temperature": 0.0,
        "max_tokens": 100,
    }

    try:
        def _call():
            resp = requests.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                timeout=(3.0, 8.0),
            )
            if resp.status_code == 200:
                text = (resp.json().get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
                # Parse JSON
                start = text.find("{")
                end = text.rfind("}")
                if start != -1 and end != -1:
                    data = json.loads(text[start : end + 1])
                    tool = data.get("tool")
                    params = data.get("params") or {}
                    if tool in TOOL_REGISTRY:
                        return tool, params
            return None, {}

        return _k2_admin_breaker.call(_call)
    except Exception as e:
        logger.warning(f"K2 tool selection failed: {e}")
        return None, {}


def _format_natural_response(question: str, tool_name: str, tool_result: Dict[str, Any]) -> str:
    """Format structured tool output into a concise natural language explanation."""
    if tool_name == "count_users":
        total = tool_result.get("total_users", 0)
        roles = tool_result.get("by_role", {})
        breakdown = ", ".join(f"{cnt} {role.lower()}s" for role, cnt in roles.items())
        return f"There are {total} registered users in LittleNet ({breakdown})."

    if tool_name == "count_users_by_role":
        role = tool_result.get("role")
        cnt = tool_result.get("count", 0)
        return f"There are currently {cnt} users with the {role} role."

    if tool_name == "count_posts":
        return f"There are {tool_result.get('approved_posts', 0)} active approved posts in the system."

    if tool_name == "count_reels":
        return f"There are {tool_result.get('active_reels', 0)} active approved Reels in LittleNet."

    if tool_name == "count_stories":
        return f"There are {tool_result.get('active_stories', 0)} active 24-hour Stories."

    if tool_name == "count_posts_by_status":
        statuses = tool_result.get("posts_by_status", {})
        items = ", ".join(f"{st}: {cnt}" for st, cnt in statuses.items())
        return f"Post status distribution: {items}."

    if tool_name == "count_reviews":
        cnt = tool_result.get("open_parent_reviews", 0)
        return f"There are currently {cnt} open parent review escalation events."

    if tool_name == "list_open_reviews":
        cnt = tool_result.get("count", 0)
        reviews = tool_result.get("reviews", [])
        if not reviews:
            return "There are no open parent review escalation events."
        items = "; ".join(f"Event #{r['event_id']} (Child {r['child_id']}, reason: {r['reason_category']})" for r in reviews)
        return f"Found {cnt} open parent reviews: {items}."

    if tool_name == "count_friend_requests":
        states = tool_result.get("friend_requests_by_state", {})
        items = ", ".join(f"{st}: {cnt}" for st, cnt in states.items())
        return f"Friendship relationships by state: {items}."

    if tool_name == "lookup_friend_request":
        if not tool_result.get("found"):
            return tool_result.get("message", "Target child not found.")
        target = tool_result.get("target_child")
        rels = tool_result.get("relationships", [])
        if not rels:
            return f"No friend requests found involving {target}."
        items = ", ".join(f"{r['peer_username']} ({r['state']})" for r in rels)
        return f"Friendship activity for {target}: {items}."

    if tool_name == "count_creators":
        return f"There are {tool_result.get('active_creators', 0)} active curated educational creators."

    if tool_name == "creator_content_summary":
        cnt = tool_result.get("creators_count", 0)
        creators = tool_result.get("creators", [])
        details = ", ".join(f"{c['name']} ({c['topic']}, {c['posts']} posts, {c['followers']} followers)" for c in creators[:5])
        return f"There are {cnt} active creators. Highlights: {details}."

    if tool_name == "upload_state_summary":
        sessions = tool_result.get("upload_sessions", {})
        items = ", ".join(f"{st}: {cnt}" for st, cnt in sessions.items())
        return f"Upload sessions status: {items}."

    if tool_name == "moderation_summary":
        p = tool_result.get("posts_by_status", {})
        rev = tool_result.get("open_parent_reviews", 0)
        act = tool_result.get("moderation_actions_24h", 0)
        return f"Moderation summary: Posts: {p}. Open parent reviews: {rev}. Moderator actions in past 24 hours: {act}."

    if tool_name == "screen_time_summary":
        active = tool_result.get("active_children_tracked", 0)
        avg_m = tool_result.get("avg_daily_screen_time_minutes", 0.0)
        max_m = tool_result.get("max_daily_screen_time_minutes", 0.0)
        return f"Screen time summary (past 7 days): {active} active children tracked, average daily usage is {avg_m} minutes (maximum: {max_m} minutes)."

    if tool_name == "quiz_summary":
        tot = tool_result.get("total_quiz_attempts", 0)
        pas = tool_result.get("passed_quiz_attempts", 0)
        rate = tool_result.get("pass_rate_pct", 0.0)
        return f"Quiz summary (past 7 days): {tot} attempts recorded, {pas} passed ({rate}% pass rate)."

    return f"Result: {json.dumps(tool_result)}"


# =====================================================================
# 3. MAIN ASSISTANT DISPATCH ENTRY POINT
# =====================================================================

def ask_admin_assistant(admin_id: int, role: str, question: str) -> Dict[str, Any]:
    """
    Process an administrative natural-language operational query.
    Enforces ADMIN or MODERATOR role authorization.
    Dispatches strictly to whitelisted read-only tools.
    Logs every invocation to admin_ai_audit_logs.
    """
    if str(role).strip().upper() not in ("ADMIN", "MODERATOR"):
        return {"ok": False, "error": "unauthorized", "message": "Only Administrators and Moderators may access the AI Database Assistant."}

    q = (question or "").strip()
    if not q:
        return {"ok": False, "error": "empty_question", "message": "Please ask an operational question."}

    # Strict protection against prompt injection asking for passwords, tokens, secrets
    lower_q = q.lower()
    if any(k in lower_q for k in ("password", "password_hash", "hash", "secret", "reset_token", "otp", "token", "private key")):
        return {
            "ok": False,
            "error": "restricted_fields",
            "message": "Security Policy: Credentials, password hashes, reset tokens, and secrets are strictly protected and never exposed.",
        }

    tool_name, params = resolve_tool(q)
    if not tool_name or tool_name not in TOOL_REGISTRY:
        return {
            "ok": True,
            "answer": (
                "I am your LittleNet Read-Only Operational Assistant. "
                "You can ask about user counts, post status breakdowns, active Reels, open moderation reviews, "
                "curated creators, upload sessions, screen time averages, or quiz statistics."
            ),
            "tool_invoked": None,
            "data": None,
        }

    tool_info = TOOL_REGISTRY[tool_name]
    fn = tool_info["fn"]
    category = tool_info["category"]

    try:
        result = fn(**params)
    except Exception as e:
        logger.exception(f"Error executing admin AI tool {tool_name}: {e}")
        return {"ok": False, "error": "tool_execution_failed", "message": "Failed to retrieve requested analytics."}

    # Calculate row count estimate for audit
    row_count = 1
    if isinstance(result, dict):
        if "count" in result:
            row_count = int(result["count"])
        elif "total_users" in result:
            row_count = int(result["total_users"])
        elif "reviews" in result:
            row_count = len(result["reviews"])
        elif "creators" in result:
            row_count = len(result["creators"])
        elif "relationships" in result:
            row_count = len(result["relationships"])

    # Audit log insertion
    try:
        execute(
            """
            INSERT INTO admin_ai_audit_logs (admin_id, question_category, tool_invoked, row_count, created_at)
            VALUES (%s, %s, %s, %s, NOW())
            """,
            (admin_id, category, tool_name, row_count),
        )
    except Exception as e:
        logger.warning(f"Failed to write admin AI audit log: {e}")

    natural_answer = _format_natural_response(q, tool_name, result)

    return {
        "ok": True,
        "answer": natural_answer,
        "tool_invoked": tool_name,
        "category": category,
        "data": result,
    }
