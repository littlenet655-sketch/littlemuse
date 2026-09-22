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


def test_face_challenge_and_replay_protection(client):
    # Ensure a test parent/user exists in DB
    user = fetch_one("SELECT user_id, username, email FROM users WHERE role='CHILD' LIMIT 1")
    if not user:
        user = execute(
            """INSERT INTO users(username, full_name, email, password_hash, role, account_status)
               VALUES('master_test_child', 'Master Child', 'master_child@littlenet.test', 'fakehash', 'CHILD', 'ACTIVE')
               RETURNING user_id, username, email""",
            returning=True,
        )

    identifier = user["username"]

    # 1. Issue challenge
    res = client.post(
        "/api/mobile/v1/auth/face/challenge",
        json={"identifier": identifier, "mode": "child"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    challenge_id = data["challenge_id"]
    nonce = data["nonce"]
    action = data["action"]
    assert action in {"BLINK", "TURN_LEFT", "TURN_RIGHT"}
    assert len(nonce) >= 32

    # Ensure user has biometric credentials enrolled
    import hmac, hashlib, secrets, json
    face_prof = fetch_one("SELECT biometric_key FROM face_profiles WHERE child_id=%s", (user["user_id"],))
    if not face_prof or not face_prof.get("biometric_key"):
        b_key = secrets.token_hex(32)
        execute(
            """INSERT INTO face_profiles(child_id, embedding, model_name, biometric_key)
               VALUES(%s, %s::jsonb, 'Facenet512', %s)
               ON CONFLICT (child_id) DO UPDATE SET biometric_key=EXCLUDED.biometric_key, model_name='Facenet512', embedding=EXCLUDED.embedding""",
            (user["user_id"], json.dumps([0.05] * 512), b_key),
        )
    else:
        b_key = face_prof["biometric_key"]

    msg = f"{challenge_id}:{nonce}:{action}:{user['user_id']}".encode("utf-8")
    sig = hmac.new(b_key.encode("utf-8"), msg, hashlib.sha256).hexdigest().lower()

    # 2. Complete challenge successfully
    res_verify = client.post(
        "/api/mobile/v1/auth/face/verify-challenge",
        json={
            "challenge_id": challenge_id,
            "nonce": nonce,
            "action_completed": action,
            "signature": sig,
            "similarity_score": 0.94,
        },
    )
    assert res_verify.status_code == 200
    verify_data = res_verify.get_json()
    assert verify_data["ok"] is True
    assert "token" in verify_data
    assert verify_data["user"]["username"] == user["username"]

    # 3. REPLAY ATTEMPT: Attempting to verify the exact same challenge again MUST fail with 403
    res_replay = client.post(
        "/api/mobile/v1/auth/face/verify-challenge",
        json={
            "challenge_id": challenge_id,
            "nonce": nonce,
            "action_completed": action,
            "signature": sig,
            "similarity_score": 0.94,
        },
    )
    assert res_replay.status_code == 403
    replay_data = res_replay.get_json()
    assert replay_data["error"] == "challenge_already_used_replay_detected"


def test_face_challenge_rejects_invalid_nonce(client):
    user = fetch_one("SELECT user_id, username FROM users WHERE role='CHILD' LIMIT 1")
    if not user:
        return

    res = client.post(
        "/api/mobile/v1/auth/face/challenge",
        json={"identifier": user["username"], "mode": "child"},
    )
    data = res.get_json()
    challenge_id = data["challenge_id"]
    action = data["action"]

    # Invalid nonce
    res_verify = client.post(
        "/api/mobile/v1/auth/face/verify-challenge",
        json={
            "challenge_id": challenge_id,
            "nonce": "bogus_wrong_nonce",
            "action_completed": action,
        },
    )
    assert res_verify.status_code == 403
    assert res_verify.get_json()["error"] == "challenge_nonce_mismatch"


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

