import io
import os
import pytest
from unittest.mock import Mock, patch

from app import app
from mobile.api import _issue_token

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c

def _child_headers(uid=110):
    token = _issue_token({'user_id': uid, 'role': 'CHILD', 'full_name': 'Kid 110'})
    return { 'Authorization': 'Bearer ' + token }


def test_r2_upload_session_put_flow_and_head_verification(client):
    user_pool = {'user_id': 110, 'role': 'CHILD', 'full_name': 'Kid 110', 'account_status': 'ACTIVE', 'session_version': 1}
    with patch('mobile.api._mobile_token_revoked', return_value=False), \
         patch('mobile.api.fetch_one', return_value=user_pool), \
         patch('mobile.api._child_gate', return_value=None), \
         patch('mobile.api.effective_categories', return_value=['Other']), \
         patch('mobile.api.execute'), \
         patch('services.object_storage.enabled', return_value=True), \
         patch('services.object_storage.signed_upload_url', return_value='https://r2.example/put?signed'):
        res = client.post('/api/mobile/v2/uploads/session', headers=_child_headers(110), json={
            'kind': 'post',
            'media_type': 'IMAGE',
            'extension': 'jpg',
            'mime_type': 'image/jpeg',
            'size_bytes': 1024,
        })
        assert res.status_code == 200
        data = res.get_json()
        assert data['ok'] is True
        assert 'upload_url' in data
        assert data['upload_url'] == 'https://r2.example/put?signed'
        assert 'object_key' in data
        assert data['object_key'].startswith('uploads/r2/quarantine/110/')



def test_media_processor_re_head_verification():
    from services.media_processor import _process_media_job_impl
    post_row = {
        'post_id': 999,
        'child_id': 110,
        'media_type': 'IMAGE',
        'caption': 'Test',
        'content_category': 'Other',
        'audience_age_group': 'ALL',
        'is_story': False,
        'is_reel': False,
        'processing_status': 'UPLOADED',
        'moderation_status': 'PENDING',
        'processing_lease_token': None,
        'processing_lease_expires_at': None,
    }
    with patch('services.media_processor.fetch_one', return_value=post_row), \
         patch('services.media_processor.execute', return_value=post_row), \
         patch('services.object_storage.enabled', return_value=True), \
         patch('services.object_storage.head_object', return_value=None):
        res = _process_media_job_impl(999, 110, 'uploads/r2/quarantine/110/xyz/source.jpg', 'post')
        assert res['ok'] is False
        assert res['error'] == 'quarantine_object_unavailable'
