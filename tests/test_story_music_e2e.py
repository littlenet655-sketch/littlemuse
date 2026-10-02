import io
import pytest
from PIL import Image
from app import create_app
from database.connection import fetch_one, execute
from mobile.api import _issue_token


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _get_child_token():
    child = fetch_one("SELECT * FROM users WHERE role='CHILD' AND account_status='ACTIVE' LIMIT 1")
    if not child:
        child = execute(
            """INSERT INTO users(username, full_name, email, password_hash, role, account_status)
               VALUES('story_music_child_1', 'Story Child', 'story_child1@test.org', 'pwd', 'CHILD', 'ACTIVE')
               RETURNING *""",
            returning=True,
        )
    token = _issue_token(dict(child))
    return token, child["user_id"]


def test_story_music_full_lifecycle(client):
    """
    Test Complete Story Music Lifecycle:
    1. Fetch curated active music tracks
    2. Upload a story specifying music_id
    3. Verify story is persisted with correct music metadata in DB
    4. Fetch story feed and verify story_music payload structure
    """
    # 1. Fetch curated music
    res_music = client.get("/api/mobile/v1/music/curated")
    assert res_music.status_code == 200
    music_data = res_music.get_json()
    assert music_data["ok"] is True
    tracks = music_data.get("tracks") or []
    assert len(tracks) > 0, "Curated music table must contain active tracks"
    selected_track = tracks[0]
    track_id = selected_track["music_id"]
    track_url = selected_track["audio_url"]

    token, child_id = _get_child_token()

    # 2. Create the story through the canonical v2 pipeline:
    #    upload session (quarantine) -> complete -> background processing.
    #    (The legacy synchronous POST /api/mobile/v1/kids/posts was retired;
    #    story music metadata is preserved by the v2 complete handler.)
    import uuid
    from pathlib import Path

    upload_id = str(uuid.uuid4())
    object_key = f"quarantine/{child_id}/{upload_id}/source.jpg"

    buf = io.BytesIO()
    Image.new("RGB", (120, 120), color="green").save(buf, format="JPEG")
    jpeg_bytes = buf.getvalue()

    execute(
        """INSERT INTO upload_sessions(upload_id, child_id, object_key, media_type, kind,
               expected_size_bytes, mime_type, extension, status, expires_at)
           VALUES(%s, %s, %s, 'IMAGE', 'STORY', %s, 'image/jpeg', 'jpg', 'UPLOADED',
                  NOW() + INTERVAL '1 hour')""",
        (upload_id, child_id, object_key, len(jpeg_bytes)),
    )
    mock_file = Path("uploads/mock_quarantine") / str(child_id) / upload_id / "source.jpg"
    mock_file.parent.mkdir(parents=True, exist_ok=True)
    mock_file.write_bytes(jpeg_bytes)

    from unittest.mock import patch

    with patch("mobile.api._child_gate", return_value=None), \
         patch("mobile.api.effective_categories", return_value={"Other"}), \
         patch("services.job_queue.enqueue_media_job", return_value="job-test-1"):
        res_upload = client.post(
            f"/api/mobile/v2/uploads/{upload_id}/complete",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "caption": "Story with curated track #music",
                "content_category": "Other",
                "audience_age_group": "ALL",
                "music_id": track_id,
                "music_start": 0,
                "music_duration": 30,
            },
        )
    assert res_upload.status_code == 200, res_upload.get_json()
    upload_data = res_upload.get_json()
    assert upload_data["ok"] is True
    assert upload_data["status"] == "PROCESSING"
    post_id = upload_data["post_id"]

    # 3. Verify DB persistence of music metadata
    db_row = fetch_one(
        "SELECT is_story, story_music_id, story_music_url, story_music_title, story_music_artist FROM posts WHERE post_id=%s",
        (post_id,),
    )
    assert db_row is not None
    assert db_row["is_story"] is True
    assert db_row["story_music_id"] == track_id
    assert db_row["story_music_url"] == track_url

    # 4. Fetch serialized story payload and verify story_music structure
    from mobile.api import _post_json
    full_db_row = fetch_one("SELECT * FROM posts WHERE post_id=%s", (post_id,))
    serialized = _post_json(dict(full_db_row))
    assert "story_music" in serialized
    music_info = serialized["story_music"]
    assert music_info["music_id"] == track_id
    assert music_info["audio_url"] == track_url
    assert music_info["title"] == selected_track["title"]
    assert music_info["artist"] == selected_track["artist"]
