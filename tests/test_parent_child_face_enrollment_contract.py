from io import BytesIO
import os
from unittest.mock import MagicMock, patch
import pytest
from app import app
from mobile.api import _issue_token


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _parent_headers(user_id=101):
    token = _issue_token({"user_id": user_id, "role": "PARENT", "full_name": "Test Parent"})
    return {"Authorization": f"Bearer {token}"}


def _child_headers(user_id=202):
    token = _issue_token({"user_id": user_id, "role": "CHILD", "full_name": "Test Child"})
    return {"Authorization": f"Bearer {token}"}


def _dummy_image_file():
    return (BytesIO(b"fake_jpeg_data_bytes_for_testing" * 40), "selfie.jpg")


def test_parent_child_face_enroll_unauthenticated(client):
    res = client.post("/api/mobile/v1/parent/children/202/face/enroll")
    assert res.status_code == 401
    assert res.get_json()["error"] == "mobile_auth_required"


def test_parent_child_face_enroll_non_parent_rejected(client):
    headers = _child_headers(202)
    with patch("mobile.api.fetch_one", return_value={"user_id": 202, "role": "CHILD", "account_status": "ACTIVE"}):
        res = client.post("/api/mobile/v1/parent/children/202/face/enroll", headers=headers)
        assert res.status_code == 403
        assert res.get_json()["error"] == "role_forbidden"


def test_parent_child_face_enroll_not_owned_child_rejected(client):
    headers = _parent_headers(101)
    with patch("mobile.api.fetch_one", return_value={"user_id": 101, "role": "PARENT", "account_status": "ACTIVE"}), \
         patch("mobile.api.owns", return_value=False):
        res = client.post("/api/mobile/v1/parent/children/999/face/enroll", headers=headers)
        assert res.status_code == 404
        assert res.get_json()["error"] == "child_not_found"


def test_parent_child_face_enroll_missing_image(client):
    headers = _parent_headers(101)
    with patch("mobile.api.fetch_one", return_value={"user_id": 101, "role": "PARENT", "account_status": "ACTIVE"}), \
         patch("mobile.api.owns", return_value=True):
        res = client.post("/api/mobile/v1/parent/children/202/face/enroll", headers=headers, json={})
        assert res.status_code == 400
        assert res.get_json()["error"] == "live_camera_photo_required"


def test_parent_child_face_enroll_success_and_cleanup(client):
    headers = _parent_headers(101)
    recorded_path = []

    def mock_enroll(cid, path):
        assert cid == 202
        assert os.path.exists(path)
        recorded_path.append(path)
        return True

    with patch("mobile.api.fetch_one", return_value={"user_id": 101, "role": "PARENT", "account_status": "ACTIVE"}), \
         patch("mobile.api.owns", return_value=True), \
         patch("mobile.api.enroll", side_effect=mock_enroll), \
         patch("mobile.api.execute", return_value=None) as execute, \
         patch("mobile.api.needs_onboarding_quiz", return_value=True):

        data = {"photo": _dummy_image_file()}
        res = client.post(
            "/api/mobile/v1/parent/children/202/face/enroll",
            headers=headers,
            data=data,
            content_type="multipart/form-data",
        )
        assert res.status_code == 200
        payload = res.get_json()
        assert payload["ok"] is True
        assert payload["child_id"] == 202
        assert payload["face_enrolled"] is True
        assert payload["quiz_required"] is True
        assert "UPDATE face_profiles" in execute.call_args.args[0]
        assert "'[]'" not in execute.call_args.args[0]

        # Ensure temp file was cleaned up
        assert len(recorded_path) == 1
        assert not os.path.exists(recorded_path[0])


def test_parent_child_face_enroll_quiz_not_required(client):
    headers = _parent_headers(101)

    with patch("mobile.api.fetch_one", return_value={"user_id": 101, "role": "PARENT", "account_status": "ACTIVE"}), \
         patch("mobile.api.owns", return_value=True), \
         patch("mobile.api.enroll", return_value=True), \
         patch("mobile.api.execute", return_value=None), \
         patch("mobile.api.needs_onboarding_quiz", return_value=False):

        data = {"photo": _dummy_image_file()}
        res = client.post(
            "/api/mobile/v1/parent/children/202/face/enroll",
            headers=headers,
            data=data,
            content_type="multipart/form-data",
        )
        assert res.status_code == 200
        payload = res.get_json()
        assert payload["ok"] is True
        assert payload["quiz_required"] is False


def test_parent_child_face_enroll_failure_and_cleanup(client):
    headers = _parent_headers(101)
    recorded_path = []

    def mock_enroll_fail(cid, path):
        recorded_path.append(path)
        raise RuntimeError("Embedding model inference failed")

    with patch("mobile.api.fetch_one", return_value={"user_id": 101, "role": "PARENT", "account_status": "ACTIVE"}), \
         patch("mobile.api.owns", return_value=True), \
         patch("mobile.api.enroll", side_effect=mock_enroll_fail):

        data = {"photo": _dummy_image_file()}
        res = client.post(
            "/api/mobile/v1/parent/children/202/face/enroll",
            headers=headers,
            data=data,
            content_type="multipart/form-data",
        )
        assert res.status_code == 400
        payload = res.get_json()
        assert payload["error"] == "face_enrollment_failed"

        # Ensure temp file was cleaned up even when enroll raised
        assert len(recorded_path) == 1
        assert not os.path.exists(recorded_path[0])


def test_parent_child_face_reenroll_returns_persisted_biometric_key(client):
    headers = _parent_headers(101)
    existing_key = "a" * 64

    with patch("mobile.api.fetch_one", return_value={"user_id": 101, "role": "PARENT", "account_status": "ACTIVE"}), \
         patch("mobile.api.owns", return_value=True), \
         patch("mobile.api.enroll", return_value=True), \
         patch("mobile.api.execute", return_value={"biometric_key": existing_key}) as execute, \
         patch("mobile.api.needs_onboarding_quiz", return_value=False):

        res = client.post(
            "/api/mobile/v1/parent/children/202/face/enroll",
            headers=headers,
            data={"photo": _dummy_image_file()},
            content_type="multipart/form-data",
        )

    assert res.status_code == 200
    payload = res.get_json()
    assert payload["biometric_key"] == existing_key
    assert execute.call_args.kwargs["returning"] is True
    assert "RETURNING biometric_key" in execute.call_args.args[0]
