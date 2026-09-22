from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def text(path):
    return (ROOT / path).read_text(encoding='utf-8')

def test_parent_flow_is_email_then_otp_activation():
    api = text('auth/api.py')
    routes = text('auth/routes.py')
    otp = text('auth/parent_email_otp.py')
    assert "request.path.rstrip('/')!='/register-parent'" in api
    assert "'PARENT',%s,'PENDING_APPROVAL'" in otp
    assert 'pending_parent_email_verified' in api
    assert "return redirect('/verify-parent-email/')" in api
    # The live adult/liveness step was removed: OTP success activates the
    # parent account directly and signs them in.
    assert "return redirect('/verify-parent-liveness/')" not in routes
    assert "@auth_bp.route('/verify-parent-liveness/'" not in routes
    assert "@api_bp.route('/verify-parent-liveness/'" not in api
    assert "UPDATE users SET account_status='ACTIVE'" in routes
    assert "UPDATE users SET account_status='ACTIVE'" not in otp
    assert 'verify_adult_face' not in routes
    assert 'parent_liveness_verify.html' not in routes
    assert 'selfie_data' not in routes

def test_parent_otp_is_hashed_expiring_and_rate_limited():
    otp = text('auth/parent_email_otp.py')
    routes = text('auth/routes.py')
    assert 'hashlib.sha256' in otp
    assert 'hmac.compare_digest' in otp
    assert 'OTP_MAX_ATTEMPTS = 5' in otp
    assert "INTERVAL '10 minutes'" in otp
    assert 'code VARCHAR' not in otp
    assert 'code TEXT' not in otp
    assert "5 per 10 minutes" in routes

def test_parent_liveness_page_and_js_are_removed_no_bypass_possible():
    # The parent liveness page and its MediaPipe JS were removed entirely by
    # explicit product decision, so no demo/manual-capture bypass can exist.
    assert not (ROOT / 'auth/templates/parent_liveness_verify.html').exists()
    assert not (ROOT / 'static/js/parent_liveness_mediapipe.js').exists()
    routes = text('auth/routes.py')
    assert 'verify_parent_liveness_page' not in routes
    assert 'parent_liveness_mediapipe' not in routes
    assert 'drawFallbackSelfie' not in routes
    assert 'manualCaptureBtn' not in routes

def test_doom_scroll_quiz_is_compulsory_and_non_skippable():
    js = text('static/js/feed_quiz.js')
    assert 'QUIZ_INTERVAL = 4' in js
    assert "document.documentElement.style.overflow = 'hidden'" in js
    assert 'Mandatory Brain Break' in js
    assert 'Answer to continue Home or Reels.' in js
    assert 'Retry quiz' in js
    assert 'fq-skip-btn' not in js
    assert 'Skip for now' not in js
    assert '_unlockScroll()' in js

def test_text_hard_blocks_cover_adult_grooming_and_severe_abuse():
    service = text('safety/text_service.py')
    policy = text('safety/policy.py')
    assert 'GROOMING_PATTERNS' in service
    assert 'SEVERE_ABUSE_TERMS' in service
    assert "category='GROOMING'" in service
    assert "category='SEVERE_ABUSE'" in service
    assert "HARD_TEXT_CATEGORIES={'GROOMING','SEVERE_ABUSE'}" in policy
    assert 'deterministic_grooming' in policy
    assert '18+ content hard blocked' in policy

def test_yolo_and_nsfw_are_active_for_image_and_video_moderation():
    visual = text('safety/visual_service.py')
    requirements = text('requirements-ai.txt')
    modal = text('modal_ai.py')
    assert 'from ultralytics import YOLO' in visual
    assert "timed_call('yolo'" in visual
    assert '_nudenet' in visual
    assert '_falconsai' in visual
    assert '_video_frames' in visual
    assert 'ultralytics>=8.3,<9' in requirements
    assert 'ultralytics>=8.3,<9' in modal
    assert 'yolo_oiv7' in modal

def test_audio_voice_whisper_and_story_music_are_retired():
    requirements = text('requirements-ai.txt')
    modal = text('modal_ai.py')
    server = text('ai_server.py')
    moderation = text('safety/moderation_service.py')
    audio = text('safety/audio_service.py')
    api = text('auth/api.py')
    upload_ui = text('uploadPost/templates/upload_post.html')
    chat_ui = text('childMessage/templates/chat.html')
    assert 'openai-whisper' not in requirements.lower()
    assert 'openai-whisper' not in modal.lower()
    assert 'import whisper' not in audio.lower()
    assert 'whisper.load_model' not in audio.lower()
    assert 'check_audio' not in server
    assert 'standalone_audio_disabled' in audio
    assert 'No\nWhisper or audio model is loaded' in audio or 'No Whisper or audio model is loaded' in audio
    assert "Standalone audio and voice uploads are disabled" in moderation
    assert '_AUDIO_EXTS' in api
    assert "field=='music_file'" in api
    assert 'accept="image/*,video/*"' in upload_ui
    assert 'accept="image/*,video/*,.pdf,.docx,.txt"' in chat_ui

def test_r2_is_required_and_persisted_for_child_media():
    api = text('auth/api.py')
    storage = text('services/object_storage.py')
    assert 'locked_media_surface_gate' in api
    assert 'Media storage is unavailable. LittleNet requires R2' in api
    assert 'persist_child_media_to_r2' in api
    assert "upload_file(local,_r2_key('posts'" in api
    assert "upload_file(local,_r2_key('messages'" in api
    assert "media_path NOT LIKE 'uploads/r2/%%'" in api
    assert "moderation_status='BLOCKED'" in api
    assert 'R2 storage unavailable' in api
    assert 'def upload_file' in storage
    assert 'return f"uploads/r2/{key}"' in storage
