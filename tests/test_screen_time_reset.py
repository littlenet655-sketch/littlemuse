import pytest
from unittest.mock import patch, MagicMock
from app import create_app

@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c

def test_parent_screen_time_reset_unauthorized(client):
    res = client.post("/api/mobile/v1/parent/time-limit/123/reset")
    assert res.status_code in (401, 403)

def test_parent_screen_time_extend_unauthorized(client):
    res = client.post("/api/mobile/v1/parent/time-limit/123/extend", json={"additional_minutes": 30})
    assert res.status_code in (401, 403)

def test_kid_screen_time_reset_unauthorized(client):
    res = client.post("/api/mobile/v1/kids/time-limit/reset")
    assert res.status_code in (401, 403)

def test_kid_screen_time_status_unauthorized(client):
    res = client.get("/api/mobile/v1/kids/time-limit/status")
    assert res.status_code in (401, 403)
