from flask import Blueprint,jsonify,session
from decorators import parent_required
from parent.service import children,owns
from database.connection import fetch_all,fetch_one

parent_api_bp=Blueprint('parent_api',__name__)

@parent_api_bp.route('/api/parent/children/')
@parent_required
def api_children():
    return jsonify(success=True,children=children(session['user_id']))

@parent_api_bp.route('/api/parent/child/<int:child_id>/')
@parent_required
def api_child(child_id):
    if not owns(session['user_id'],child_id):
        return jsonify(success=False),404
    return jsonify(success=True,profile=fetch_one('SELECT * FROM child_profiles WHERE child_id=%s',(child_id,)))

def child_viewing_insights(child_id):
    """Read-only aggregation of the child's recorded watch data for Parent Mode.

    Shared helper for the web route below and the mobile v1 Bearer-token
    alias (``GET /api/mobile/v1/parent/child/<child_id>/viewing-insights``).

    Sources: content_impressions (recorded by services/curated_feed.py from the
    FEED/REELS surfaces), with per-item category/title resolved from
    curated_content + content_categories (CURATED) or posts.content_category
    (SOCIAL). Callers must enforce the owns() parent-owns-child gate.
    """

    totals=fetch_one(
        """SELECT
             COUNT(*) FILTER (WHERE shown_at >= NOW() - INTERVAL '7 days') AS views_7d,
             COALESCE(SUM(watched_ms) FILTER (WHERE shown_at >= NOW() - INTERVAL '7 days'), 0) AS ms_7d,
             COUNT(*) FILTER (WHERE shown_at >= NOW() - INTERVAL '30 days') AS views_30d,
             COALESCE(SUM(watched_ms) FILTER (WHERE shown_at >= NOW() - INTERVAL '30 days'), 0) AS ms_30d
           FROM content_impressions
           WHERE child_id=%s""",
        (child_id,)) or {}

    # Per-category watch counts/minutes over the last 30 days. Curated items
    # use the editorial category; social (child-post) items use the post's own
    # content_category label.
    categories=fetch_all(
        """SELECT
             CASE WHEN ci.source_type='CURATED' THEN cat.display_name
                  ELSE COALESCE(p.content_category,'Other') END AS category,
             COUNT(*) AS views,
             COALESCE(SUM(ci.watched_ms),0) AS ms
           FROM content_impressions ci
           LEFT JOIN curated_content cc
             ON cc.content_id=ci.source_id AND ci.source_type='CURATED'
           LEFT JOIN content_categories cat ON cat.category_id=cc.category_id
           LEFT JOIN posts p
             ON p.post_id=ci.source_id AND ci.source_type='SOCIAL'
           WHERE ci.child_id=%s AND ci.shown_at >= NOW() - INTERVAL '30 days'
           GROUP BY 1
           ORDER BY views DESC""",
        (child_id,))

    # Most-watched reels (30d): curated reels plus social reels from the feed.
    top_reels=fetch_all(
        """SELECT kind,id,label,category,views,ms FROM (
             SELECT 'curated' AS kind, cc.content_id AS id, cc.title AS label,
                    cat.display_name AS category, COUNT(*) AS views,
                    COALESCE(SUM(ci.watched_ms),0) AS ms
             FROM content_impressions ci
             JOIN curated_content cc ON cc.content_id=ci.source_id
             LEFT JOIN content_categories cat ON cat.category_id=cc.category_id
             WHERE ci.child_id=%s AND ci.source_type='CURATED' AND cc.is_reel
               AND ci.shown_at >= NOW() - INTERVAL '30 days'
             GROUP BY cc.content_id,cc.title,cat.display_name
             UNION ALL
             SELECT 'social' AS kind, p.post_id AS id,
                    LEFT(COALESCE(p.caption,''),120) AS label,
                    COALESCE(p.content_category,'Other') AS category,
                    COUNT(*) AS views, COALESCE(SUM(ci.watched_ms),0) AS ms
             FROM content_impressions ci
             JOIN posts p ON p.post_id=ci.source_id
             WHERE ci.child_id=%s AND ci.source_type='SOCIAL' AND p.is_reel
               AND ci.shown_at >= NOW() - INTERVAL '30 days'
             GROUP BY p.post_id,p.caption,p.content_category
           ) t
           ORDER BY views DESC
           LIMIT 10""",
        (child_id,child_id))

    def secs(ms):
        try: return int(ms or 0)//1000
        except (TypeError,ValueError): return 0

    return dict(child_id=child_id,windows={
        '7d': {'views':int(totals.get('views_7d') or 0),'watch_seconds':secs(totals.get('ms_7d'))},
        '30d': {'views':int(totals.get('views_30d') or 0),'watch_seconds':secs(totals.get('ms_30d'))},
    },by_category=[
        {'category':row.get('category') or 'Other',
         'views':int(row.get('views') or 0),
         'watch_seconds':secs(row.get('ms'))}
        for row in (categories or [])
    ],top_reels=[
        {'kind':row.get('kind'),'id':row.get('id'),
         'title':row.get('label') or 'Untitled',
         'category':row.get('category') or 'Other',
         'views':int(row.get('views') or 0),
         'watch_seconds':secs(row.get('ms'))}
        for row in (top_reels or [])
    ])


@parent_api_bp.route('/api/parent/child/<int:child_id>/viewing-insights')
@parent_required
def api_child_viewing_insights(child_id):
    if not owns(session['user_id'],child_id):
        return jsonify(success=False),404
    return jsonify(success=True,**child_viewing_insights(child_id))


@parent_api_bp.route('/api/parent/children/<int:parent_id>/')
@parent_required
def api_children_compat(parent_id):
    if parent_id!=session['user_id']:
        return jsonify(success=False),403
    return jsonify(success=True,children=children(session['user_id']))

# Native React Native/Expo APIs are registered once on auth.api.api_bp.
# Do not attach the complete mobile API to this parent-only blueprint: doing so
# duplicates every /api/mobile/* route in Flask's URL map.
