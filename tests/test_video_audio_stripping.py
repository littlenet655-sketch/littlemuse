from pathlib import Path

import pytest

from services import media_sanitizer, object_storage


class FakeS3:
    def __init__(self):self.uploads=[]
    def upload_file(self,*args,**kwargs):self.uploads.append((args,kwargs))


def test_video_is_stripped_before_r2_upload(tmp_path,monkeypatch):
    path=tmp_path/'clip.mp4';path.write_bytes(b'fake-video')
    calls=[];s3=FakeS3()
    monkeypatch.setattr(media_sanitizer,'strip_video_audio_in_place',lambda p:calls.append(p) or True)
    monkeypatch.setattr(object_storage,'_client',lambda:s3)
    monkeypatch.setenv('R2_BUCKET','test-bucket')
    ref=object_storage.upload_file(str(path),'posts/1/test.mp4')
    assert calls == [str(path)]
    assert len(s3.uploads) == 1
    assert ref == 'uploads/r2/posts/1/test.mp4'


def test_audio_strip_failure_prevents_r2_publish(tmp_path,monkeypatch):
    path=tmp_path/'clip.mp4';path.write_bytes(b'fake-video')
    s3=FakeS3()
    def fail(_):raise media_sanitizer.MediaSanitizationError('audio_stream_still_present')
    monkeypatch.setattr(media_sanitizer,'strip_video_audio_in_place',fail)
    monkeypatch.setattr(object_storage,'_client',lambda:s3)
    monkeypatch.setenv('R2_BUCKET','test-bucket')
    with pytest.raises(media_sanitizer.MediaSanitizationError):
        object_storage.upload_file(str(path),'posts/1/test.mp4')
    assert s3.uploads == []


def test_images_do_not_use_video_sanitizer(tmp_path,monkeypatch):
    path=tmp_path/'image.jpg';path.write_bytes(b'fake-image')
    s3=FakeS3()
    monkeypatch.setattr(media_sanitizer,'strip_video_audio_in_place',lambda _p:pytest.fail('image must not be video-sanitized'))
    monkeypatch.setattr(object_storage,'_client',lambda:s3)
    monkeypatch.setenv('R2_BUCKET','test-bucket')
    object_storage.upload_file(str(path),'posts/1/image.jpg')
    assert len(s3.uploads) == 1


def test_sanitizer_contract_uses_ffmpeg_an_and_verifies_audio_absent():
    source=Path(media_sanitizer.__file__).read_text(encoding='utf-8')
    assert "'ffmpeg'" in source
    assert "'-an'" in source
    assert 'has_audio_stream(tmp)' in source
    assert 'audio_stream_still_present' in source
    assert 'os.replace' in source


def _make_video_with_audio(path):
    import subprocess
    subprocess.run(
        ['ffmpeg','-hide_banner','-loglevel','error','-y',
         '-f','lavfi','-i','testsrc=duration=1:size=320x240:rate=10',
         '-f','lavfi','-i','sine=frequency=440:duration=1',
         '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',
         str(path)],
        check=True, timeout=60,
    )


def test_strip_removes_audio_from_real_video(tmp_path):
    path=tmp_path/'clip.mp4'
    _make_video_with_audio(path)
    assert media_sanitizer.has_audio_stream(str(path)) is True
    assert media_sanitizer.has_video_stream(str(path)) is True
    assert media_sanitizer.strip_video_audio_in_place(str(path)) is True
    assert media_sanitizer.has_audio_stream(str(path)) is False
    assert media_sanitizer.has_video_stream(str(path)) is True


def test_strip_is_idempotent_for_silent_video(tmp_path):
    path=tmp_path/'silent.mp4'
    _make_video_with_audio(path)
    media_sanitizer.strip_video_audio_in_place(str(path))
    assert media_sanitizer.strip_video_audio_in_place(str(path)) is False
    assert media_sanitizer.has_audio_stream(str(path)) is False


def test_strip_fails_closed_on_garbage_input(tmp_path):
    path=tmp_path/'clip.mp4'
    path.write_bytes(b'not-a-video')
    with pytest.raises(media_sanitizer.MediaSanitizationError):
        media_sanitizer.strip_video_audio_in_place(str(path))


def test_all_video_publish_paths_route_through_audio_strip():
    """No code path may publish a video without stripping its audio first.

    Publish paths (see docs/VIDEO_AUDIO_SAFETY_DECISION.md):
    * services/media_processor._make_video_derivatives -- both the async
      worker path (_process_media_job_impl) and sanitize_and_promote_media
      (quarantine promotion) strip via strip_video_audio_in_place and raise
      on any failure;
    * services/object_storage.upload_file strips any video/* upload, which
      covers every persist_before_db caller (mobile post creation,
      uploadPost, chat media).
    """
    import services.media_persistence as media_persistence

    # Read the processor source without importing it: importing
    # services.media_processor requires database/config wiring.
    derivatives = (
        Path(media_sanitizer.__file__).parent / 'media_processor.py'
    ).read_text(encoding='utf-8')
    assert 'strip_video_audio_in_place(str(clean_video))' in derivatives
    assert 'raise RuntimeError(f"video_sanitization_failed' in derivatives
    # Both video publish paths in the processor use the derivatives helper.
    assert derivatives.count('_make_video_derivatives(source_local, temp_dir)') >= 2

    upload_src = Path(object_storage.__file__).read_text(encoding='utf-8')
    assert 'strip_video_audio_in_place(str(path))' in upload_src

    persist_src = Path(media_persistence.__file__).read_text(encoding='utf-8')
    assert 'upload_file(str(path), key)' in persist_src

