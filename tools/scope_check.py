from pathlib import Path
import sys

R = Path(__file__).parents[1]
checks = {
    'Kids Mode feed': ('child/routes.py', '/child/dashboard/'),
    'Posts/upload': ('uploadPost/routes.py', '/child/upload-post/'),
    'Reels': ('uploadPost/routes.py', '/reels/'),
    'Messages/chat': ('childMessage/routes.py', '/messages/'),
    'Discover': ('child/routes.py', '/discover/'),
    'Parent email OTP gate': ('auth/routes.py', '/verify-parent-email/'),
    'Mandatory age onboarding quiz': ('auth/api.py', '/quiz/start/?onboarding=1'),
    '18+ hard block': ('safety/policy.py', '18+ content hard blocked'),
    'NSFW visual moderation': ('safety/visual_service.py', 'Falconsai/nsfw_image_detection'),
    'YOLO object detection': ('safety/visual_service.py', 'from ultralytics import YOLO'),
    'Scene-aware video sampling': ('safety/visual_service.py', 'combined_frame_indices(path,total,max_frames)'),
    'Cyberbullying/toxic NLP': ('safety/text_service.py', 'CYBERBULLYING'),
    'Parent review': ('parent/routes.py', '/parent/review/'),
    'Screen time': ('services/usage.py', 'SCREEN_TIME_LIMIT_REACHED'),
    'Smart parent controls': ('services/controls.py', 'educational_only_feed'),
    'Quizzes': ('quiz/routes.py', '/quiz/start/'),
    'Admin/Moderator': ('admin/routes.py', '/admin/moderation/'),
    'PostgreSQL activity logs': ('database/schema.sql', 'CREATE TABLE IF NOT EXISTS activity_logs'),
    'R2 media adapter': ('services/object_storage.py', 'uploads/r2/'),
    'React Native app source': ('mobile_app/App.tsx', 'LittleNet'),
    'Expo package contract': ('mobile_app/app.json', 'com.littlenet.app'),
    'Mobile bearer API': ('mobile/api.py', '/api/mobile/v1/health'),
    'v2 direct upload API': ('mobile/api.py', '/api/mobile/v2/uploads/session'),
    'v2 processing status API': ('mobile/api.py', '/api/mobile/v2/posts/<int:post_id>/processing-status'),
    'Async media job queue': ('services/job_queue.py', 'enqueue_media_job'),
    'Modal AI deployment': ('modal_ai.py', 'gpu="T4"'),
    'Quiet hours': ('services/controls.py', 'quiet_hours_state'),
    'Approved-only interaction': ('uploadPost/routes.py', 'approved connection required'),
}
errors = []
for name, (rel, needle) in checks.items():
    p = R / rel
    ok = p.exists() and needle in p.read_text(encoding='utf-8')
    print(('PASS' if ok else 'FAIL'), name)
    if not ok:
        errors.append(name)

negative = {
    'Standalone speech dependency removed': ('requirements-ai.txt', 'openai-whisper'),
    'Legacy mobile source removed': ('mobile_flutter', None),
    'Duplicate Android root removed': ('android', None),
    'Old native release workflow removed': ('.github/workflows/release-android.yml', None),
}
for name, (rel, forbidden) in negative.items():
    p = R / rel
    ok = not p.exists() if forbidden is None else (not p.exists() or forbidden.lower() not in p.read_text(encoding='utf-8').lower())
    print(('PASS' if ok else 'FAIL'), name)
    if not ok:
        errors.append(name)

print(f'\nSCOPE_CHECK={len(checks)+len(negative)-len(errors)}/{len(checks)+len(negative)}')
sys.exit(bool(errors))
