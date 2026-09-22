"""Standalone LittleNet heavy AI inference service.

The locked LittleNet scope supports TEXT, IMAGE and VIDEO moderation.
Standalone audio/voice moderation is intentionally not exposed.
"""
import json
import math
import os
import tempfile
import hmac
from pathlib import Path

os.environ["LITTLENET_AI_SERVER"] = "1"

from flask import Flask, jsonify, request

from safety.text_service import check_text
from safety.visual_service import check_image
from safety.video_service import check_video

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024


def authorized():
    secret = os.getenv("AI_SHARED_SECRET", "").strip()
    supplied = request.headers.get("X-LittleNet-AI-Key", "")
    return bool(secret) and hmac.compare_digest(supplied, secret)


def deny():
    return jsonify({"ok": False, "error": "unauthorized"}), 401


def save_upload():
    f = request.files.get("file")
    if not f or not f.filename:
        raise ValueError("file_required")
    suffix = Path(f.filename).suffix[:12]
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    f.save(path)
    return path


@app.get("/healthz")
def healthz():
    if not authorized(): return deny()
    return jsonify({"ok": True, "service": "littlenet-ai", "moderation": ["TEXT", "IMAGE", "VIDEO"]})


def _sanitize(val):
    if isinstance(val, dict): return {k: _sanitize(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)): return [_sanitize(v) for v in val]
    if hasattr(val, 'item'): return val.item()
    return val


@app.post("/ai/moderate")
def moderate():
    if not authorized(): return deny()
    t = (request.form.get("content_type") or "").upper()
    if t == "TEXT":
        return jsonify({"ok": True, "signals": _sanitize(check_text(request.form.get("text", "")))})
    if t not in {"IMAGE", "VIDEO"}:
        return jsonify({"ok": False, "error": "unsupported_content_type"}), 400
    path = None
    try:
        path = save_upload()
        signals = check_video(path) if t == "VIDEO" else check_image(path)
        return jsonify({"ok": True, "signals": _sanitize(signals)})
    finally:
        if path:
            try: os.unlink(path)
            except OSError: pass


@app.post("/ai/moderate-upload")
def moderate_upload_endpoint():
    """Moderate caption text and uploaded media in a single GPU-container request."""
    if not authorized(): return deny()
    t = (request.form.get("content_type") or "").upper()
    if t not in {"IMAGE", "VIDEO"}:
        return jsonify({"ok": False, "error": "unsupported_content_type"}), 400
    text = str(request.form.get("text") or "")[:4000]
    path = None
    try:
        path = save_upload()
        text_signals = check_text(text) if text else {}
        media_signals = check_video(path) if t == "VIDEO" else check_image(path)
        return jsonify({
            "ok": True,
            "text_signals": _sanitize(text_signals),
            "media_signals": _sanitize(media_signals),
        })
    finally:
        if path:
            try: os.unlink(path)
            except OSError: pass


@app.post("/ai/rank")
def rank_endpoint():
    if not authorized(): return deny()
    data=request.get_json(silent=True) or {}
    profile_text=str(data.get("profile_text") or "")[:500]
    raw=data.get("items") or []
    if not isinstance(raw,list) or len(raw)>60:
        return jsonify({"ok":False,"error":"invalid_items"}),400
    items=[]
    for x in raw:
        if not isinstance(x,dict):continue
        try:item_id=int(x.get("id"))
        except (TypeError,ValueError):continue
        items.append({"id":item_id,"text":str(x.get("text") or "")[:500]})
    try:
        from safety.semantic_service import rank_texts
        scores=rank_texts(profile_text,[x["text"] for x in items])
        ranked=[{"id":x["id"],"score":float(score)} for x,score in zip(items,scores)]
        ranked.sort(key=lambda x:x["score"],reverse=True)
        return jsonify({"ok":True,"items":ranked})
    except Exception:
        app.logger.exception("semantic ranking failed")
        return jsonify({"ok":False,"error":"ranking_unavailable"}),503


# Background media processing is dispatched by the web app through Modal
# Function.spawn(). The retired QStash receiver was removed to avoid carrying
# a second unauthoritative production job path.


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8081")))