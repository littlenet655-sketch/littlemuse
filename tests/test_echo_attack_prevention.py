import secrets
import hmac
import hashlib
import pytest
from app import create_app
from database.connection import fetch_one, execute


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


import json


def _ensure_child_with_biometrics():
    user = fetch_one("SELECT user_id, username FROM users WHERE role='CHILD' LIMIT 1")
    if not user:
        user = execute(
            """INSERT INTO users(username, full_name, email, password_hash, role, account_status)
               VALUES('echo_child_1', 'Echo Child', 'echo_child1@littlenet.test', 'pwd', 'CHILD', 'ACTIVE')
               RETURNING user_id, username""",
            returning=True,
        )
    face_prof = fetch_one("SELECT biometric_key FROM face_profiles WHERE child_id=%s", (user["user_id"],))
    if not face_prof or not face_prof.get("biometric_key"):
        execute(
            """INSERT INTO face_profiles(child_id, embedding, model_name, biometric_key)
               VALUES(%s, %s::jsonb, 'Facenet512', %s)
               ON CONFLICT (child_id) DO UPDATE SET biometric_key=EXCLUDED.biometric_key, model_name='Facenet512', embedding=EXCLUDED.embedding""",
            (user["user_id"], json.dumps([0.05] * 512), secrets.token_hex(32)),
        )
    return user


def test_echo_attack_missing_signature_fails(client):
    """
    Echo Attack Test A-E:
    Request legitimate challenge, but bypass camera, liveness, and face comparison.
    Send challenge_id, nonce, and action_completed without valid cryptographic signature.
    Authentication MUST FAIL with 403 Forbidden.
    """
    user = _ensure_child_with_biometrics()

    # 1. Request legitimate challenge
    res = client.post(
        "/api/mobile/v1/auth/face/challenge",
        json={"identifier": user["username"], "mode": "child"},
    )
    assert res.status_code == 200
    data = res.get_json()
    challenge_id = data["challenge_id"]
    nonce = data["nonce"]
    action = data["action"]

    # 2. ECHO ATTACK: send challenge parameters back with NO cryptographic signature
    res_echo = client.post(
        "/api/mobile/v1/auth/face/verify-challenge",
        json={
            "challenge_id": challenge_id,
            "nonce": nonce,
            "action_completed": action,
        },
    )
    assert res_echo.status_code == 403
    payload = res_echo.get_json()
    assert payload["error"] == "biometric_proof_required_echo_attack_rejected"


def test_echo_attack_boolean_bypass_fields_fail(client):
    """
    Attempt to authenticate using naive boolean bypass parameters:
    face_match=True, verified=True, blink_passed=True, liveness_passed=True.
    None of these may authenticate without cryptographic biometric signature.
    """
    user = _ensure_child_with_biometrics()
    res = client.post(
        "/api/mobile/v1/auth/face/challenge",
        json={"identifier": user["username"], "mode": "child"},
    )
    data = res.get_json()
    challenge_id = data["challenge_id"]
    nonce = data["nonce"]
    action = data["action"]

    res_bypass = client.post(
        "/api/mobile/v1/auth/face/verify-challenge",
        json={
            "challenge_id": challenge_id,
            "nonce": nonce,
            "action_completed": action,
            "face_match": True,
            "verified": True,
            "blink_passed": True,
            "liveness_passed": True,
            "is_real": True,
            "signature": "",  # Empty signature
        },
    )
    assert res_bypass.status_code == 403
    assert res_bypass.get_json()["error"] == "biometric_proof_required_echo_attack_rejected"


def test_echo_attack_forged_or_tampered_signature_fails(client):
    """
    Attempt to authenticate with an attacker-forged signature or wrong biometric key.
    Must fail with 403 biometric_signature_invalid.
    """
    user = _ensure_child_with_biometrics()

    res = client.post(
        "/api/mobile/v1/auth/face/challenge",
        json={"identifier": user["username"], "mode": "child"},
    )
    data = res.get_json()

    # Sign with a random bogus attacker key (attacker does not have device secret key)
    attacker_key = secrets.token_hex(32)
    tampered_msg = f"{data['challenge_id']}:{data['nonce']}:{data['action']}:{user['user_id']}".encode("utf-8")
    forged_sig = hmac.new(attacker_key.encode("utf-8"), tampered_msg, hashlib.sha256).hexdigest()

    res_forged = client.post(
        "/api/mobile/v1/auth/face/verify-challenge",
        json={
            "challenge_id": data["challenge_id"],
            "nonce": data["nonce"],
            "action_completed": data["action"],
            "signature": forged_sig,
        },
    )
    assert res_forged.status_code == 403
    assert res_forged.get_json()["error"] == "biometric_signature_invalid"
