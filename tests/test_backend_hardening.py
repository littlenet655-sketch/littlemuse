"""Backend audit + hardening tests.

Covers the recommendation hard-hide for NOT_INTERESTED/HIDE feedback, the
Modal text-moderation env var naming, the retired QStash verifier removal, and
the parent web routes' approved-mapping checks.
"""
from __future__ import annotations

import os
import sys
import types

import pytest

import services.curated_feed as cf
import services.recommendation as rec


# ── hidden_items ──────────────────────────────────────────────────────────────

def _item(source_type, source_id, **overrides):
    base = {
        "source_type": source_type,
        "source_id": source_id,
        "post_id": source_id,
        "content_id": source_id,
        "category": "Nature & Animals",
        "content_category": "Nature & Animals",
        "audience_age_group": "ALL",
        "min_age": 4,
        "max_age": 18,
        "is_safe": True,
        "moderation_status": "ALLOWED",
        "is_reel": False,
        "ranking_metadata": {"child_id": 42, "created_at": "2026-09-20T10:00:00Z"},
    }
    base.update(overrides)
    return base


def test_hidden_items_returns_not_interested_and_hide(monkeypatch):
    seen = {}

    def fake_fetch_all(sql, params):
        seen["sql"] = sql
        seen["params"] = params
        return [
            {"source_type": "SOCIAL", "source_id": 101},
            {"source_type": "CURATED", "source_id": 7},
        ]

    monkeypatch.setattr(rec, "fetch_all", fake_fetch_all)
    items = [_item("SOCIAL", 101), _item("CURATED", 7), _item("SOCIAL", 202)]
    hidden = rec.hidden_items(9, items)

    assert hidden == {("SOCIAL", 101), ("CURATED", 7)}
    assert "NOT_INTERESTED" in seen["sql"] and "'HIDE'" in seen["sql"]
    # Only the candidate ids are ever sent to the database (order irrelevant).
    assert set(seen["params"][1]) == {101, 202}
    assert set(seen["params"][2]) == {7}


def test_hidden_items_fail_open_on_db_error(monkeypatch):
    def boom(sql, params):
        raise RuntimeError("db down")

    monkeypatch.setattr(rec, "fetch_all", boom)
    assert rec.hidden_items(9, [_item("SOCIAL", 101)]) == set()


def test_hidden_items_empty_input_skips_db(monkeypatch):
    def boom(sql, params):
        raise AssertionError("must not query")

    monkeypatch.setattr(rec, "fetch_all", boom)
    assert rec.hidden_items(9, []) == set()


# ── _safe_rank_candidates ─────────────────────────────────────────────────────

def _patch_rank_gates(monkeypatch, hidden_rows=()):
    monkeypatch.setattr(rec, "effective_categories", lambda cid: ["Nature & Animals"])
    monkeypatch.setattr(rec, "_age_group", lambda cid: "9-11")
    monkeypatch.setattr(rec, "_child_real_age", lambda cid: 10)

    def fake_fetch_all(sql, params):
        if "recommendation_signals" in sql:
            return list(hidden_rows)
        if "blocked_users" in sql:
            return []
        raise AssertionError(f"unexpected query: {sql[:60]}")

    monkeypatch.setattr(rec, "fetch_all", fake_fetch_all)


def test_safe_rank_candidates_excludes_hidden_items(monkeypatch):
    _patch_rank_gates(
        monkeypatch,
        hidden_rows=[{"source_type": "SOCIAL", "source_id": 101}],
    )
    items = [
        _item("SOCIAL", 101),  # hidden by the child
        _item("SOCIAL", 102),
        _item("CURATED", 7),
    ]
    eligible = rec._safe_rank_candidates(9, items)
    assert {i["source_id"] for i in eligible} == {102, 7}


def test_safe_rank_candidates_still_enforces_publication_gates(monkeypatch):
    _patch_rank_gates(monkeypatch)
    items = [
        _item("SOCIAL", 102),
        _item("SOCIAL", 103, moderation_status="REVIEW"),
        _item("SOCIAL", 104, is_safe=False),
        _item("SOCIAL", 105, audience_age_group="14-18"),
        _item("SOCIAL", 106, content_category="Cooking", category="Cooking"),
    ]
    eligible = rec._safe_rank_candidates(9, items)
    assert [i["source_id"] for i in eligible] == [102]


def test_safe_rank_candidates_blocks_muted_creators(monkeypatch):
    _patch_rank_gates(monkeypatch)

    def fake_fetch_all(sql, params):
        if "recommendation_signals" in sql:
            return []
        if "muted_users" in sql:
            return [{"creator_id": 42}]
        return []

    monkeypatch.setattr(rec, "fetch_all", fake_fetch_all)
    items = [_item("SOCIAL", 102), _item("SOCIAL", 103, ranking_metadata={"child_id": 43})]
    eligible = rec._safe_rank_candidates(9, items)
    assert [i["source_id"] for i in eligible] == [103]


# ── _materialize_session_items ────────────────────────────────────────────────

def _social_db_row(post_id=101, child_id=42, category="Nature & Animals"):
    return {
        "post_id": post_id,
        "child_id": child_id,
        "content_category": category,
        "caption": "rabbit",
        "full_name": "Friend",
        "profile_picture": None,
        "media_type": "IMAGE",
        "media_path": "uploads/r2/posts/rabbit.jpg",
        "is_reel": False,
        "audience_age_group": "ALL",
        "moderation_status": "ALLOWED",
        "is_safe": True,
        "likes": 3,
        "comments_count": 1,
        "is_following": True,
        "created_at": "2026-09-20T10:00:00Z",
    }


def test_materialize_session_items_excludes_hidden(monkeypatch):
    import child.service as child_service

    monkeypatch.setattr(cf, "controls_for_child", lambda cid: {"allow_reels": True})
    monkeypatch.setattr(cf, "effective_categories", lambda cid: ["Nature & Animals"])
    monkeypatch.setattr(cf, "_age_group", lambda cid: "9-11")
    monkeypatch.setattr(cf, "_child_real_age", lambda cid: 10)
    monkeypatch.setattr(child_service, "discoverable_child_ids", lambda cid: [42])

    def fake_fetch_all(sql, params):
        if "FROM posts p" in sql:
            return [_social_db_row(101), _social_db_row(102)]
        if "blocked_users" in sql:
            return []
        raise AssertionError(f"unexpected query: {sql[:60]}")

    monkeypatch.setattr(cf, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(
        rec,
        "hidden_items",
        lambda cid, probe: {("SOCIAL", 101)},
    )
    raw = [
        {"source_type": "SOCIAL", "source_id": 101},
        {"source_type": "SOCIAL", "source_id": 102},
    ]
    hydrated = cf._materialize_session_items(raw, child_id=9, surface="FEED")
    assert [i["source_id"] for i in hydrated] == [102]


def test_materialize_session_items_still_rechecks_blocks(monkeypatch):
    import child.service as child_service

    monkeypatch.setattr(cf, "controls_for_child", lambda cid: {"allow_reels": True})
    monkeypatch.setattr(cf, "effective_categories", lambda cid: ["Nature & Animals"])
    monkeypatch.setattr(cf, "_age_group", lambda cid: "9-11")
    monkeypatch.setattr(cf, "_child_real_age", lambda cid: 10)
    monkeypatch.setattr(child_service, "discoverable_child_ids", lambda cid: [42])
    monkeypatch.setattr(rec, "hidden_items", lambda cid, probe: set())

    def fake_fetch_all(sql, params):
        if "FROM posts p" in sql:
            return [_social_db_row(101, child_id=42), _social_db_row(102, child_id=77)]
        if "blocked_users" in sql:
            return [{"creator_id": 77}]
        raise AssertionError(f"unexpected query: {sql[:60]}")

    monkeypatch.setattr(cf, "fetch_all", fake_fetch_all)
    raw = [
        {"source_type": "SOCIAL", "source_id": 101},
        {"source_type": "SOCIAL", "source_id": 102},
    ]
    hydrated = cf._materialize_session_items(raw, child_id=9, surface="FEED")
    assert [i["source_id"] for i in hydrated] == [101]


# ── modal_text_moderation env var ─────────────────────────────────────────────

def test_text_cpu_function_name_prefers_text_specific_var(monkeypatch):
    from services import modal_text_moderation as client

    monkeypatch.setenv("LITTLENET_AI_TEXT_CPU_FUNCTION", "moderate_text_cpu")
    monkeypatch.setenv("LITTLENET_AI_IMAGE_CPU_FUNCTION", "legacy_image_fn")
    assert client._cpu_function_name() == "moderate_text_cpu"


def test_text_cpu_function_name_falls_back_to_legacy_var(monkeypatch):
    from services import modal_text_moderation as client

    monkeypatch.delenv("LITTLENET_AI_TEXT_CPU_FUNCTION", raising=False)
    monkeypatch.setenv("LITTLENET_AI_IMAGE_CPU_FUNCTION", "legacy_image_fn")
    assert client._cpu_function_name() == "legacy_image_fn"


def test_text_cpu_function_name_defaults_to_shared_function(monkeypatch):
    from services import modal_text_moderation as client

    monkeypatch.delenv("LITTLENET_AI_TEXT_CPU_FUNCTION", raising=False)
    monkeypatch.delenv("LITTLENET_AI_IMAGE_CPU_FUNCTION", raising=False)
    assert client._cpu_function_name() == "moderate_image_upload_cpu"


def test_text_cpu_client_uses_configured_text_function(monkeypatch):
    from services import modal_text_moderation as client

    seen = {}

    class Fn:
        def remote(self, *args):
            return {
                "ok": True,
                "text_signals": {"category": "TEXT", "toxicity_score": 0.01},
                "media_signals": {},
            }

    class Function:
        @staticmethod
        def from_name(app_name, function_name):
            seen["function_name"] = function_name
            return Fn()

    monkeypatch.setitem(sys.modules, "modal", types.SimpleNamespace(Function=Function))
    monkeypatch.setenv("LITTLENET_USE_MODAL_TEXT_CPU", "1")
    monkeypatch.setenv("LITTLENET_AI_TEXT_CPU_FUNCTION", "moderate_text_cpu")
    monkeypatch.delenv("LITTLENET_AI_SERVER", raising=False)

    result = client.moderate_text("hello world")
    assert result["category"] == "TEXT"
    assert seen["function_name"] == "moderate_text_cpu"


# ── dead code removal ─────────────────────────────────────────────────────────

def test_qstash_verifier_removed():
    assert not os.path.exists(
        os.path.join(os.path.dirname(__file__), "..", "services", "qstash_verifier.py")
    )


def test_seed_dataset_script_removed():
    assert not os.path.exists(
        os.path.join(
            os.path.dirname(__file__), "..", "database", "seeds", "seed_dataset_to_app.py"
        )
    )


def test_modal_web_no_longer_sets_legacy_queue_env():
    path = os.path.join(os.path.dirname(__file__), "..", "modal_web.py")
    with open(path, encoding="utf-8") as fh:
        body = fh.read()
    # The misleading env assignment is gone (a comment may still flag it as legacy).
    assert '"LITTLENET_USE_MODAL_QUEUE": "1"' not in body
    assert "'LITTLENET_USE_MODAL_QUEUE': '1'" not in body


# ── parent web routes: approved-mapping checks ────────────────────────────────

def _parent_app():
    from flask import Flask

    import parent.routes as pr

    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.register_blueprint(pr.parent_bp)
    return app, pr


def test_parent_safety_queue_requires_approved_mapping(monkeypatch):
    app, pr = _parent_app()
    captured = {}

    def fake_fetch_one(sql, params=None):
        return {"role": "PARENT", "account_status": "ACTIVE"}

    def fake_fetch_all(sql, params=None):
        captured["sql"] = sql
        captured["params"] = params
        return []

    monkeypatch.setattr(pr, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(pr, "fetch_all", fake_fetch_all)
    # The role decorator reads fetch_one from its own (decorators) namespace.
    monkeypatch.setattr("decorators.fetch_one", fake_fetch_one)
    # Only the SQL scoping is under test here; template rendering needs the
    # full app (shared partials), so stub it out.
    monkeypatch.setattr(pr, "render_template", lambda *a, **k: "ok")

    with app.test_request_context("/parent/safety/"):
        from flask import session

        session["user_id"] = 7
        session["role"] = "PARENT"
        pr.safety()

    sql = captured["sql"]
    assert "m.approved=TRUE" in sql
    assert "m.approval_status='APPROVED'" in sql
    assert "m.parent_id=%s OR m.verified_parent_id=%s" in sql
    assert captured["params"] == (7, 7)


def test_parent_deleted_posts_requires_approved_mapping(monkeypatch):
    app, pr = _parent_app()
    captured = {}

    def fake_fetch_one(sql, params=None):
        return {"role": "PARENT", "account_status": "ACTIVE"}

    def fake_fetch_all(sql, params=None):
        captured["sql"] = sql
        captured["params"] = params
        return []

    monkeypatch.setattr(pr, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(pr, "fetch_all", fake_fetch_all)
    # The role decorator reads fetch_one from its own (decorators) namespace.
    monkeypatch.setattr("decorators.fetch_one", fake_fetch_one)
    # Only the SQL scoping is under test here; template rendering needs the
    # full app (shared partials), so stub it out.
    monkeypatch.setattr(pr, "render_template", lambda *a, **k: "ok")

    with app.test_request_context("/parent/deleted-posts/"):
        from flask import session

        session["user_id"] = 7
        session["role"] = "PARENT"
        pr.deleted_posts()

    sql = captured["sql"]
    assert "m.approved=TRUE" in sql
    assert "m.approval_status='APPROVED'" in sql
    assert "m.parent_id=%s OR m.verified_parent_id=%s" in sql
    assert captured["params"] == (7, 7)


# ── child web recommendation-action route ─────────────────────────────────────

def _child_app():
    from flask import Flask

    import child.routes as cr

    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.register_blueprint(cr.child_bp)
    return app, cr


def _child_session(monkeypatch, cr):
    def fake_fetch_one(sql, params=None):
        if "account_status" in sql:
            return {"role": "CHILD", "account_status": "ACTIVE"}
        return None

    monkeypatch.setattr(cr, "fetch_one", fake_fetch_one)
    # The role decorator reads fetch_one from its own (decorators) namespace.
    monkeypatch.setattr("decorators.fetch_one", fake_fetch_one)


def test_recommendation_action_records_hide_for_visible_post(monkeypatch):
    app, cr = _child_app()
    _child_session(monkeypatch, cr)
    recorded = {}
    monkeypatch.setattr(cr, "post_visible_to", lambda uid, pid: {"post_id": pid})
    monkeypatch.setattr(
        cr, "record_signal", lambda uid, stype, sid, sig: recorded.update(
            {"uid": uid, "stype": stype, "sid": sid, "sig": sig}
        ) or True,
    )

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 9
        sess["role"] = "CHILD"
    resp = client.post(
        "/api/recommendation-action/",
        json={"action": "not_interested", "source_type": "SOCIAL", "source_id": 101},
    )
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True, "action": "NOT_INTERESTED"}
    assert recorded == {"uid": 9, "stype": "SOCIAL", "sid": 101, "sig": "NOT_INTERESTED"}


def test_recommendation_action_rejects_invisible_post(monkeypatch):
    app, cr = _child_app()
    _child_session(monkeypatch, cr)
    monkeypatch.setattr(cr, "post_visible_to", lambda uid, pid: None)
    called = []
    monkeypatch.setattr(cr, "record_signal", lambda *a: called.append(a) or True)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 9
        sess["role"] = "CHILD"
    resp = client.post(
        "/api/recommendation-action/",
        json={"action": "HIDE", "source_type": "SOCIAL", "source_id": 999},
    )
    assert resp.status_code == 404
    assert called == []


def test_recommendation_action_validates_action_and_curated(monkeypatch):
    app, cr = _child_app()
    _child_session(monkeypatch, cr)
    monkeypatch.setattr(cr, "post_visible_to", lambda uid, pid: {"post_id": pid})

    import services.curated_feed as cf_mod

    monkeypatch.setattr(cf_mod, "curated_item_visible_to", lambda uid, cid: True)
    recorded = []
    monkeypatch.setattr(cr, "record_signal", lambda *a: recorded.append(a) or True)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 9
        sess["role"] = "CHILD"

    resp = client.post("/api/recommendation-action/", json={"action": "LIKE", "source_id": 1})
    assert resp.status_code == 400

    resp = client.post("/api/recommendation-action/", json={"action": "HIDE"})
    assert resp.status_code == 400

    resp = client.post(
        "/api/recommendation-action/",
        json={"action": "HIDE", "source_type": "CURATED", "source_id": 7},
    )
    assert resp.status_code == 200
    assert recorded and recorded[0][1:] == ("CURATED", 7, "HIDE")
