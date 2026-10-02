import pytest
from app import create_app
from database.connection import execute, fetch_one


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_curated_music_endpoint(client):
    res = client.get("/api/mobile/v1/music/curated")
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert "tracks" in data
    assert len(data["tracks"]) >= 5
    first = data["tracks"][0]
    assert "music_id" in first
    assert "title" in first
    assert "artist" in first
    assert "audio_url" in first
    assert first["audio_url"].startswith("http")


def test_post_location_persistence():
    # Insert post with coarse location
    child = fetch_one("SELECT user_id FROM users WHERE role='CHILD' LIMIT 1")
    if not child:
        child = execute(
            """INSERT INTO users(username, full_name, email, password_hash, role, account_status)
               VALUES('master_test_child', 'Master Child', 'master_child@littlenet.test', 'fakehash', 'CHILD', 'ACTIVE')
               RETURNING user_id""",
            returning=True,
        )

    post = execute(
        """INSERT INTO posts(child_id, media_type, caption, content_category, is_safe, moderation_status, location_name)
           VALUES(%s, 'TEXT', 'Science museum visit #science', 'Science', TRUE, 'ALLOWED', 'Bengaluru Science Center')
           RETURNING post_id, location_name""",
        (child["user_id"],),
        returning=True,
    )
    assert post["post_id"] > 0
    assert post["location_name"] == "Bengaluru Science Center"

    # Query back from DB
    loaded = fetch_one("SELECT location_name FROM posts WHERE post_id=%s", (post["post_id"],))
    assert loaded["location_name"] == "Bengaluru Science Center"

