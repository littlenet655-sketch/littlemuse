from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import modal

app = modal.App("littlenet-live-media-probe")
probe_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "requests>=2.32,<3",
        "psycopg2-binary>=2.9,<3",
        "itsdangerous>=2.2,<3",
        "Pillow>=11,<13",
    )
)
web_secret = modal.Secret.from_name(os.getenv("LITTLENET_WEB_SECRET", "littlemuse-web-secrets"))


def _fail(label: str, status: int | None = None, body: object | None = None) -> RuntimeError:
    safe = {"step": label}
    if status is not None:
        safe["status"] = status
    if isinstance(body, dict):
        safe["body"] = {k: v for k, v in body.items() if k not in {"token", "upload_url", "media_url", "playback_url"}}
    return RuntimeError(json.dumps(safe, sort_keys=True))


@app.function(image=probe_image, secrets=[web_secret], timeout=900)
def run_probe() -> dict:
    import requests
    import psycopg2
    import psycopg2.extras
    from itsdangerous import URLSafeTimedSerializer
    from PIL import Image, ImageDraw

    base = (os.environ.get("BASE_URL") or "").strip().rstrip("/")
    db_url = (os.environ.get("DATABASE_URL") or "").strip()
    secret = os.environ.get("SECRET_KEY") or ""
    if not base.startswith("https://") or not db_url or len(secret) < 16:
        raise RuntimeError("release probe environment is incomplete")

    child_a = 2
    child_b = 3

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT user_id,username,full_name,role,account_status,session_version
                     FROM users WHERE user_id IN (%s,%s) ORDER BY user_id""",
                (child_a, child_b),
            )
            users = {int(r["user_id"]): dict(r) for r in cur.fetchall()}
            cur.execute(
                """SELECT child_id,following_child_id,approved,approval_stage
                     FROM followers
                    WHERE ((child_id=%s AND following_child_id=%s)
                       OR (child_id=%s AND following_child_id=%s))""",
                (child_a, child_b, child_b, child_a),
            )
            rels = [dict(r) for r in cur.fetchall()]
            cur.execute(
                """SELECT post_id,moderation_status,is_reel
                     FROM posts
                    WHERE moderation_status IN ('REVIEW','BLOCKED')
                    ORDER BY created_at DESC NULLS LAST, post_id DESC
                    LIMIT 40"""
            )
            hidden_candidates = [dict(r) for r in cur.fetchall()]
            cur.execute(
                """SELECT current_database() AS database_name,
                          (SELECT COUNT(*) FROM users) AS users,
                          (SELECT COUNT(*) FROM posts) AS posts,
                          (SELECT COUNT(*) FROM schema_migrations) AS migrations,
                          (SELECT MAX(version) FROM schema_migrations) AS latest_migration"""
            )
            db_fingerprint = dict(cur.fetchone() or {})
    finally:
        conn.close()

    safe_user_state = {
        str(uid): {
            "exists": bool(users.get(uid)),
            "role": (users.get(uid) or {}).get("role"),
            "status": (users.get(uid) or {}).get("account_status"),
            "session_version": int((users.get(uid) or {}).get("session_version") or 0),
        }
        for uid in (child_a, child_b)
    }
    for uid in (child_a, child_b):
        u = users.get(uid)
        if not u or u.get("role") != "CHILD" or u.get("account_status") != "ACTIVE":
            raise RuntimeError(
                "MODAL_DB_FINGERPRINT "
                + json.dumps(
                    {"db": db_fingerprint, "e2e_users": safe_user_state},
                    sort_keys=True,
                    default=str,
                )
            )
    if not any(
        int(r["child_id"]) == child_a
        and int(r["following_child_id"]) == child_b
        and r.get("approved")
        and r.get("approval_stage") == "ACTIVE"
        for r in rels
    ):
        raise RuntimeError("Child A -> Child B relationship is not ACTIVE")
    if not any(
        int(r["child_id"]) == child_b
        and int(r["following_child_id"]) == child_a
        and r.get("approved")
        and r.get("approval_stage") == "ACTIVE"
        for r in rels
    ):
        raise RuntimeError("Child B -> Child A relationship is not ACTIVE")

    serializer = URLSafeTimedSerializer(secret, salt="littlenet-native-auth-v1")

    def token_for(uid: int) -> str:
        u = users[uid]
        return serializer.dumps(
            {
                "uid": uid,
                "role": "CHILD",
                "name": u.get("full_name") or u.get("username") or "Release Probe",
                "sver": int(u.get("session_version") or 1),
            }
        )

    token_a = token_for(child_a)
    token_b = token_for(child_b)
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    session = requests.Session()

    def backend(method: str, path: str, *, headers=None, json_body=None, timeout=90):
        r = session.request(
            method,
            base + path,
            headers=headers or {},
            json=json_body,
            timeout=timeout,
        )
        try:
            body = r.json()
        except Exception:
            body = {"raw": r.text[:500]}
        if r.status_code >= 400:
            raise _fail(path, r.status_code, body)
        return r, body

    # Verify both tokens are accepted and no child gate blocks the release probe.
    for uid, hdr in ((child_a, headers_a), (child_b, headers_b)):
        r, body = backend("GET", "/api/mobile/v1/kids/home", headers=hdr)
        if body.get("ok") is not True:
            raise _fail(f"kids-home-{uid}", r.status_code, body)

    with tempfile.TemporaryDirectory(prefix="littlenet-release-probe-") as td:
        root = Path(td)
        image_path = root / "safe-release-probe.png"
        video_path = root / "safe-release-probe.mp4"

        img = Image.new("RGB", (640, 480), (230, 242, 255))
        draw = ImageDraw.Draw(img)
        draw.rectangle((90, 90, 550, 390), outline=(30, 90, 150), width=8)
        draw.ellipse((250, 160, 390, 300), fill=(90, 180, 120))
        draw.text((155, 330), "LittleNet safe release probe", fill=(20, 50, 80))
        img.save(image_path, format="PNG")

        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=skyblue:s=640x360:r=24:d=3",
                "-vf", "drawbox=x=120:y=80:w=400:h=200:color=green@0.8:t=fill",
                "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                str(video_path),
            ],
            check=True,
        )

        created_posts: list[int] = []

        def upload(kind: str, path: Path, mime: str, media_type: str) -> dict:
            start_payload = {
                "kind": kind,
                "filename": path.name,
                "media_type": media_type,
                "size_bytes": path.stat().st_size,
                "extension": path.suffix.lstrip("."),
                "mime_type": mime,
            }
            r, start = backend(
                "POST",
                "/api/mobile/v2/uploads/session",
                headers={**headers_a, "Content-Type": "application/json"},
                json_body=start_payload,
            )
            upload_id = str(start.get("upload_id") or "")
            upload_url = str(start.get("upload_url") or "")
            required_headers = dict(start.get("required_headers") or {})
            if not upload_id or not upload_url.startswith("https://"):
                raise _fail("upload-session-contract", r.status_code, start)

            with path.open("rb") as fh:
                put = session.put(upload_url, data=fh, headers=required_headers, timeout=120)
            if put.status_code not in (200, 201, 204):
                raise _fail("r2-signed-put", put.status_code)

            r, completed = backend(
                "POST",
                f"/api/mobile/v2/uploads/{upload_id}/complete",
                headers={**headers_a, "Content-Type": "application/json"},
                json_body={
                    "caption": f"LittleNet safe {kind} release probe",
                    "content_category": "Education",
                    "audience_age_group": "ALL",
                    "tags": ["releaseprobe", "education"],
                },
                timeout=120,
            )
            post_id = int(completed.get("post_id") or 0)
            if not post_id:
                raise _fail("upload-complete-contract", r.status_code, completed)
            created_posts.append(post_id)

            deadline = time.time() + 300
            latest = {}
            while time.time() < deadline:
                _, latest = backend(
                    "GET",
                    f"/api/mobile/v2/posts/{post_id}/processing-status",
                    headers=headers_a,
                    timeout=60,
                )
                status = str(latest.get("status") or "").upper()
                if status in {"ALLOWED", "REVIEW", "BLOCKED", "FAILED"}:
                    break
                time.sleep(4)
            if str(latest.get("status") or "").upper() != "ALLOWED":
                raise _fail(f"{kind}-moderation-not-allowed", 200, latest)
            if str(latest.get("moderation_status") or "").upper() != "ALLOWED" or latest.get("is_safe") is not True:
                raise _fail(f"{kind}-publication-not-safe", 200, latest)
            return {
                "post_id": post_id,
                "status": latest.get("status"),
                "moderation_status": latest.get("moderation_status"),
                "is_safe": bool(latest.get("is_safe")),
            }

        evidence: dict[str, object] = {}
        try:
            image_evidence = upload("post", image_path, "image/png", "IMAGE")
            reel_evidence = upload("reel", video_path, "video/mp4", "VIDEO")
            image_id = int(image_evidence["post_id"])
            reel_id = int(reel_evidence["post_id"])

            def fetch_page(path: str) -> dict:
                _, body = backend("GET", path, headers=headers_b, timeout=90)
                if body.get("ok") is not True:
                    raise _fail(path, 200, body)
                return body

            feed = fetch_page("/api/mobile/v2/kids/feed?mode=friends&limit=50")
            reels = fetch_page("/api/mobile/v2/kids/reels?limit=50")

            feed_items = list(feed.get("items") or [])
            reel_items = list(reels.get("items") or [])

            def social_ids(items: list[dict]) -> set[int]:
                ids: set[int] = set()
                for item in items:
                    if str(item.get("source_type") or "").upper() != "SOCIAL":
                        continue
                    for key in ("post_id", "source_id"):
                        try:
                            ids.add(int(item.get(key)))
                        except Exception:
                            pass
                return ids

            feed_ids = social_ids(feed_items)
            reel_ids = social_ids(reel_items)

            if image_id not in feed_ids:
                # A newly-created stable feed session should include the newest friend post;
                # retry with a fresh session once to rule out an expired/raced snapshot.
                time.sleep(2)
                feed = fetch_page("/api/mobile/v2/kids/feed?mode=friends&limit=50")
                feed_items = list(feed.get("items") or [])
                feed_ids = social_ids(feed_items)
            if reel_id not in reel_ids:
                time.sleep(2)
                reels = fetch_page("/api/mobile/v2/kids/reels?limit=50")
                reel_items = list(reels.get("items") or [])
                reel_ids = social_ids(reel_items)

            image_item = next((x for x in feed_items if int(x.get("post_id") or x.get("source_id") or 0) == image_id), None)
            if not image_item:
                raise RuntimeError(f"Child B v2 friends feed did not include release-probe image post {image_id}")
            if reel_id not in reel_ids:
                raise RuntimeError(f"Child B v2 reels did not include release-probe Reel {reel_id}")

            image_url = str(image_item.get("media_url") or "")
            if not image_url.startswith("https://"):
                raise RuntimeError("Feed image did not expose a signed HTTPS media URL")
            img_resp = session.get(image_url, timeout=90, stream=True)
            image_content_type = str(img_resp.headers.get("content-type") or "").split(";", 1)[0].lower()
            image_bytes = len(img_resp.raw.read(65536))
            if img_resp.status_code != 200 or not image_content_type.startswith("image/") or image_bytes <= 0:
                raise RuntimeError(
                    f"Signed image fetch failed status={img_resp.status_code} type={image_content_type!r} bytes={image_bytes}"
                )

            _, playback = backend(
                "GET",
                f"/api/mobile/v2/kids/reels/{reel_id}/playback",
                headers=headers_b,
                timeout=90,
            )
            playback_url = str(playback.get("playback_url") or "")
            if not playback_url.startswith("https://"):
                raise RuntimeError("Reel JIT endpoint did not expose a signed HTTPS playback URL")
            video_resp = session.get(
                playback_url,
                headers={"Range": "bytes=0-65535"},
                timeout=90,
                stream=True,
            )
            video_content_type = str(video_resp.headers.get("content-type") or "").split(";", 1)[0].lower()
            video_bytes = len(video_resp.raw.read(65536))
            if video_resp.status_code not in (200, 206) or not video_content_type.startswith("video/") or video_bytes <= 0:
                raise RuntimeError(
                    f"JIT video fetch failed status={video_resp.status_code} type={video_content_type!r} bytes={video_bytes}"
                )

            hidden_ids = {int(r["post_id"]) for r in hidden_candidates}
            public_page_ids = feed_ids | reel_ids
            hidden_leak = sorted(hidden_ids & public_page_ids)
            if hidden_leak:
                raise RuntimeError(f"REVIEW/BLOCKED post leaked into Child B public surfaces: {hidden_leak[:10]}")

            conn2 = psycopg2.connect(db_url)
            try:
                with conn2.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        """SELECT post_id,child_id,media_type,media_path,poster_path,source_media_path,
                                  moderation_status,processing_status,is_safe,is_reel
                             FROM posts WHERE post_id IN (%s,%s) ORDER BY post_id""",
                        (image_id, reel_id),
                    )
                    post_rows = [dict(r) for r in cur.fetchall()]
                    cur.execute(
                        """SELECT post_id,media_kind,provider,published_reference,poster_reference,status
                             FROM media_assets WHERE post_id IN (%s,%s) ORDER BY post_id,media_id""",
                        (image_id, reel_id),
                    )
                    media_rows = [dict(r) for r in cur.fetchall()]
            finally:
                conn2.close()

            if len(post_rows) != 2 or any(r.get("moderation_status") != "ALLOWED" or not r.get("is_safe") for r in post_rows):
                raise RuntimeError("Published post rows did not persist as ALLOWED + safe")
            if not any(int(r.get("post_id") or 0) == reel_id and r.get("published_reference") for r in media_rows):
                raise RuntimeError("Reel media_assets row is missing its published R2 reference")

            evidence = {
                "ok": True,
                "backend": base,
                "child_a": child_a,
                "child_b": child_b,
                "image": {
                    **image_evidence,
                    "visible_in_child_b_friends_feed": True,
                    "signed_http_status": img_resp.status_code,
                    "content_type": image_content_type,
                    "sample_bytes": image_bytes,
                },
                "reel": {
                    **reel_evidence,
                    "visible_in_child_b_reels": True,
                    "playback_http_status": video_resp.status_code,
                    "content_type": video_content_type,
                    "sample_bytes": video_bytes,
                    "jit_playback": True,
                },
                "postgres_media_rows": len(media_rows),
                "review_block_public_leak_count": 0,
            }
            return evidence
        finally:
            # Use the same owner-facing API that the app uses so R2 references are
            # queued for deletion instead of leaving release-probe objects behind.
            for post_id in created_posts:
                try:
                    session.delete(
                        base + f"/api/mobile/v1/kids/posts/{post_id}",
                        headers=headers_a,
                        timeout=60,
                    )
                except Exception:
                    pass


@app.local_entrypoint()
def main():
    result = run_probe.remote()
    print("LIVE_MEDIA_PROBE " + json.dumps(result, sort_keys=True))
