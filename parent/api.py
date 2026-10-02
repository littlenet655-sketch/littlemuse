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
    """Return the five most recently watched Reel items for Parent Mode.

    This intentionally replaces the old 7d/30d/category aggregation. The demo
    only needs a small supervision snapshot, so one bounded query is cheaper
    and easier to explain. Callers must enforce the owns() gate.
    """
    rows=fetch_all(
        """SELECT *
           FROM (
             SELECT DISTINCT ON (ci.source_type,ci.source_id)
               ci.source_type,
               ci.source_id,
               ci.shown_at,
               ci.watched_ms,
               CASE
                 WHEN ci.source_type='CURATED' THEN COALESCE(cc.title,'Curated reel')
                 ELSE COALESCE(NULLIF(LEFT(p.caption,120),''),'Social reel')
               END AS title,
               CASE
                 WHEN ci.source_type='CURATED' THEN COALESCE(cat.display_name,'Other')
                 ELSE COALESCE(p.content_category,'Other')
               END AS category
             FROM content_impressions ci
             LEFT JOIN curated_content cc
               ON cc.content_id=ci.source_id AND ci.source_type='CURATED'
             LEFT JOIN content_categories cat ON cat.category_id=cc.category_id
             LEFT JOIN posts p
               ON p.post_id=ci.source_id AND ci.source_type='SOCIAL'
             WHERE ci.child_id=%s
               AND COALESCE(ci.watched_ms,0) > 0
               AND (
                 (ci.source_type='CURATED' AND COALESCE(cc.is_reel,FALSE)=TRUE)
                 OR
                 (ci.source_type='SOCIAL' AND COALESCE(p.is_reel,FALSE)=TRUE)
               )
             ORDER BY ci.source_type,ci.source_id,ci.shown_at DESC
           ) recent
           ORDER BY shown_at DESC
           LIMIT 5""",
        (child_id,)) or []

    def secs(ms):
        try:return max(0,int(ms or 0)//1000)
        except (TypeError,ValueError):return 0

    return dict(
        child_id=child_id,
        recent_items=[
            {
                'kind':str(row.get('source_type') or '').lower(),
                'id':int(row.get('source_id') or 0),
                'title':row.get('title') or 'Reel',
                'category':row.get('category') or 'Other',
                'watch_seconds':secs(row.get('watched_ms')),
                'watched_at':row.get('shown_at'),
            }
            for row in rows
        ],
    )


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
