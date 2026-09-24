from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_upload_ack_is_private_processing_not_fake_publication_success():
    api = text("mobile/api.py")
    assert 'moderation_queued=True' in api
    assert 'publication_state="PRIVATE_PROCESSING"' in api
    assert "moderation_status='ALLOWED'" in text("services/media_processor.py")


def test_mobile_upload_ux_acknowledges_fast_then_allows_browsing():
    create = text("mobile_app/src/screens/kids/CreateScreen.tsx")
    processing = text("mobile_app/src/screens/kids/ProcessingScreen.tsx")
    assert "Finalizing your upload…" in create
    assert "Uploaded ✓ — checking privately" in processing
    assert 'label="Keep browsing"' in processing
    assert "Your post is live!" in processing


def test_feed_and_reels_remain_cursor_paginated():
    hook = text("mobile_app/src/kids/useFeed.ts")
    feed = text("mobile_app/src/screens/kids/FeedScreen.tsx")
    reels = text("mobile_app/src/screens/kids/ReelsScreen.tsx")
    assert "useInfiniteQuery" in hook
    assert "getNextPageParam" in hook
    assert "fetchNextPage()" in hook
    assert "onEndReached={feed.loadMore}" in feed
    assert "onEndReached={feed.loadMore}" in reels


def test_random_reel_brain_break_is_server_driven_and_feed_stays_optional():
    feed = text("mobile_app/src/screens/kids/FeedScreen.tsx")
    reels = text("mobile_app/src/screens/kids/ReelsScreen.tsx")
    service = text("quiz/service.py")
    assert "ALLOWED_QUIZ_THRESHOLDS = (2, 3, 4, 5)" in service
    assert "Quiz Zone" in feed
    assert "scrollEnabled={!quizLocked}" not in feed
    assert "withQuizBreaks(visibleItems" not in feed
    assert "const displayItems = feed.items" in reels
    assert "scrollEnabled={!quizLocked}" in reels
    assert "if (result.quiz_required)" in reels
    assert "withQuizBreaks(feed.items" not in reels


def test_perf_hardening_has_no_cross_request_discovery_ttl():
    child = text("child/service.py")
    cache = text("services/request_cache.py")
    assert "_DISCOVERABLE_CACHE_TTL" not in child
    assert "_discoverable_cache" not in child
    assert '("discoverable_child_ids", viewer_id)' in child
    assert "cache[key] = maker()" in cache
    assert "except Exception:\n        return maker()" in cache


def test_direct_upload_session_uses_deployment_scoped_r2_key():
    storage = text("services/object_storage.py")
    api = text("mobile/api.py")
    processor = text("services/media_processor.py")
    assert "def deployment_object_key(key: str)" in storage
    assert "def new_reference(key: str)" in storage
    assert "object_storage.new_reference(" in api
    assert 'f"quarantine/{uid}/{upload_id}/source.{ext}"' in api
    assert "published_media_ref = object_storage.upload_file(" in processor
    assert 'published_media_ref = f"uploads/r2/{namespace}/' not in processor


def test_child_modal_close_paths_have_home_fallback_and_hardware_back():
    create = text("mobile_app/src/screens/kids/CreateScreen.tsx")
    stories = text("mobile_app/src/screens/kids/StoriesScreen.tsx")
    conversations = text("mobile_app/src/screens/kids/ConversationsScreen.tsx")
    for source in (create, stories, conversations):
        assert "BackHandler.addEventListener('hardwareBackPress'" in source
        assert "navigation.canGoBack()" in source
        assert "FeedTab" in source


def test_feed_has_only_shell_brand_header():
    feed = text("mobile_app/src/screens/kids/FeedScreen.tsx")
    tabs = text("mobile_app/src/screens/kids/KidsTabs.tsx")
    assert '<BrandHeader title="LittleNet"' not in feed
    assert "<LnWordmark width={128}" in tabs
