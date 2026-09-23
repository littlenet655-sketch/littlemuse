import math,os,tempfile,subprocess
from .common import env_flag,normalize_signals,timed_call,timeout_seconds
from .scene_sampler import combined_frame_indices

CLIP_MODEL_ID='openai/clip-vit-base-patch32'
CLIP_MODEL_REVISION='3d74acf'
FALCON_NSFW_MODEL_ID='Falconsai/nsfw_image_detection'
FALCON_NSFW_REVISION='0436797'


def _runtime_device():
    requested=os.getenv('LITTLENET_DEVICE','auto').lower()
    try:
        import torch
        if requested=='cuda' and torch.cuda.is_available():return 'cuda'
        if requested=='cpu':return 'cpu'
        return 'cuda' if torch.cuda.is_available() else 'cpu'
    except Exception:return 'cpu'


_CLIP=None;_CLIP_PROC=None;_NUDE=None;_NSFW=None;_OPENNSFW2=None;_EXTRA_HF=None;_YOLO=None


def _clip_score_impl(image_path):
    global _CLIP,_CLIP_PROC
    from PIL import Image
    from transformers import CLIPModel,CLIPProcessor
    if _CLIP is None:
        _CLIP=CLIPModel.from_pretrained(CLIP_MODEL_ID,revision=CLIP_MODEL_REVISION);device=_runtime_device()
        if device=='cuda':_CLIP=_CLIP.to(device)
        _CLIP.eval();_CLIP_PROC=CLIPProcessor.from_pretrained(CLIP_MODEL_ID,revision=CLIP_MODEL_REVISION)
    labels=['normal child-friendly content','nudity or sexually explicit content','physical violence','weapon gun knife dangerous object','smoking drugs or alcohol']
    inp=_CLIP_PROC(text=labels,images=Image.open(image_path).convert('RGB'),return_tensors='pt',padding=True);device=_runtime_device()
    if device=='cuda':inp={k:v.to(device) if hasattr(v,'to') else v for k,v in inp.items()}
    probs=_CLIP(**inp).logits_per_image.softmax(dim=1)[0].detach().cpu().tolist()
    return {'adult':probs[1],'sexual':probs[1],'violence':probs[2],'weapon':probs[3],'general':max(probs[1:])}


def _clip_score(image_path):
    try:return timed_call('clip',lambda:_clip_score_impl(image_path),timeout_seconds('clip',90))
    except Exception:return None


def _nudenet(path):
    global _NUDE
    from nudenet import NudeDetector
    if _NUDE is None:_NUDE=NudeDetector()
    ds=_NUDE.detect(path)
    risky={'FEMALE_BREAST_EXPOSED','FEMALE_GENITALIA_EXPOSED','MALE_GENITALIA_EXPOSED','ANUS_EXPOSED','BUTTOCKS_EXPOSED'}
    return max([float(d.get('score',0)) for d in ds if d.get('class') in risky] or [0])


def _falconsai(path):
    global _NSFW
    from transformers import pipeline
    if _NSFW is None:_NSFW=pipeline('image-classification',model=FALCON_NSFW_MODEL_ID,revision=FALCON_NSFW_REVISION,device=0 if _runtime_device()=='cuda' else -1)
    rs=_NSFW(path)
    return max([float(x['score']) for x in rs if str(x['label']).lower()=='nsfw'] or [0])


def _opennsfw2(path):
    if not env_flag('LITTLENET_ENABLE_OPENNSFW2'):return None
    import opennsfw2
    return float(opennsfw2.predict_image(path))


def _extra_hf_nsfw(path):
    if not env_flag('LITTLENET_ENABLE_EXTRA_NSFW'):return None
    model_id=os.getenv('LITTLENET_EXTRA_NSFW_MODEL','').strip()
    revision=os.getenv('LITTLENET_EXTRA_NSFW_REVISION','').strip()
    if not model_id or not revision:raise RuntimeError('extra_nsfw_model_or_revision_missing')
    global _EXTRA_HF
    if _EXTRA_HF is None:
        from transformers import pipeline
        _EXTRA_HF=pipeline('image-classification',model=model_id,revision=revision,device=0 if _runtime_device()=='cuda' else -1)
    rows=_EXTRA_HF(path);score=0.0
    for row in rows or []:
        label=str(row.get('label','')).lower()
        if any(k in label for k in ('nsfw','porn','sexual','adult','unsafe')):score=max(score,float(row.get('score',0) or 0))
    return score


# ---------------------------------------------------------------------------
# OCR for burned-in text (phone numbers, handles, URLs) in images.
#
# OCR is an always-on, bounded enhancement: it runs unless
# LITTLENET_ENABLE_OCR=0. When enabled, extracted text is routed through the
# SAME text + PII policy as user-typed text (check_text + scan_pii); no policy
# logic is duplicated here. OCR evidence can only strengthen the visual
# decision: scores merge by max, hard-block text flags propagate, and any OCR
# failure becomes partial safety evidence (REVIEW at most), never a bypass.
#
# The preferred OCR backend is rapidocr-onnxruntime (pinned in
# requirements-core.txt; no external system binary needed). easyocr and
# pytesseract (+ tesseract binary) are supported fallbacks, tried in that
# order. When the flag is on but no backend is importable the stage fails
# closed: it records 'ocr_unavailable' and sets partial_safety_failure so the
# item goes to REVIEW instead of being silently allowed.
# ---------------------------------------------------------------------------

class _OCRUnavailable(RuntimeError):
    pass


_OCR_READER = None           # cached backend reader callable: path -> str
_OCR_BACKEND_NAME = None
_OCR_BACKEND_MISSING = False
_OCR_UNAVAILABLE_LOGGED = False


def _rapidocr_reader():
    from rapidocr_onnxruntime import RapidOCR
    engine = RapidOCR()

    def read(path):
        out = engine(path)
        rows = out[0] if isinstance(out, tuple) else out
        parts = []
        for row in rows or []:
            try:
                parts.append(str(row[1]))
            except Exception:
                continue
        return ' '.join(parts)

    return read


def _easyocr_reader():
    import easyocr
    reader = easyocr.Reader(['en'], gpu=False)

    def read(path):
        return ' '.join(str(row[1]) for row in (reader.readtext(path) or []))

    return read


def _pytesseract_reader():
    import pytesseract
    from PIL import Image

    def read(path):
        with Image.open(path) as img:
            return pytesseract.image_to_string(img.convert('RGB'))

    return read


def _load_ocr_backend():
    """Return a cached ``read_text(path) -> str`` callable.

    Guarded optional import: raises ``_OCRUnavailable`` when no supported OCR
    backend is installed, instead of silently pretending OCR works.
    """
    global _OCR_READER, _OCR_BACKEND_NAME, _OCR_BACKEND_MISSING
    if _OCR_READER is not None:
        return _OCR_READER
    if _OCR_BACKEND_MISSING:
        raise _OCRUnavailable('no_ocr_backend')
    last_error = None
    for name, factory in (('rapidocr', _rapidocr_reader),
                          ('easyocr', _easyocr_reader),
                          ('pytesseract', _pytesseract_reader)):
        try:
            _OCR_READER = factory()
            _OCR_BACKEND_NAME = name
            return _OCR_READER
        except Exception as exc:
            last_error = exc
    _OCR_BACKEND_MISSING = True
    raise _OCRUnavailable(
        f'no_ocr_backend: {type(last_error).__name__}' if last_error else 'no_ocr_backend'
    )


def _downscale_for_ocr(path, max_px=1024):
    """Bounded OCR input: downscale to a temp PNG so OCR stays fast."""
    from PIL import Image
    fd, tmp = tempfile.mkstemp(prefix='littlenet_ocr_', suffix='.png')
    os.close(fd)
    try:
        with Image.open(path) as img:
            work = img.convert('RGB')
            work.thumbnail((max_px, max_px))
            work.save(tmp, format='PNG')
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return tmp


def _ocr_extract_text(path):
    """Extract burned-in text, bounded by downscale + timeout.

    Returns ``(text, error_code)``; ``error_code`` is None on success (even
    when no text is found). Never raises: failures are reported as codes so
    the caller records them as partial safety evidence instead of bypassing.
    A non-None ``error_code`` is a failure signal -- the caller must treat it
    as a safety gap (fail closed), never as "no text present".
    """
    global _OCR_UNAVAILABLE_LOGGED
    try:
        read = _load_ocr_backend()
    except _OCRUnavailable:
        if not _OCR_UNAVAILABLE_LOGGED:
            _OCR_UNAVAILABLE_LOGGED = True
            print('[littlenet-safety] OCR is enabled but no OCR backend is installed; '
                  'burned-in text screening is inactive and images fail closed to '
                  'REVIEW. Install rapidocr-onnxruntime (preferred), easyocr, or '
                  'pytesseract (+ tesseract binary) to restore it.')
        return None, 'ocr_unavailable'
    tmp = None
    try:
        tmp = _downscale_for_ocr(path)
        text = timed_call('ocr', lambda: read(tmp), timeout_seconds('ocr', 30))
    except Exception as exc:
        code = 'ocr_timeout' if 'timeout' in str(exc).lower() else 'ocr_failed'
        return None, code
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    text = (text or '').strip()
    return (text or None), None


def _apply_ocr_evidence(result, ocr_text):
    """Fold OCR-extracted text into image signals through the shared policy.

    Routes ``ocr_text`` through the SAME ``check_text`` + PII policy used for
    user-typed text. Visual evidence is never weakened: scores merge by max,
    deterministic hard-block text flags propagate, and burned-in contact/PII
    (scan_pii policy_action BLOCK) sets ``deterministic_ocr_pii`` so
    ``policy.decide`` hard-blocks. OCR text that cannot be moderated (text
    models unavailable, no deterministic hits) is partial safety evidence
    only: it can push the image to REVIEW, never to ALLOW, and never escalates
    the image to a total safety failure.
    """
    from .pii_service import scan_pii
    from .text_service import check_text

    text = (ocr_text or '').strip()
    if not text:
        return result
    ocr_signals = check_text(text)
    pii = scan_pii(text)

    for key in ('adult_score', 'sexual_score', 'violence_score', 'weapon_score',
                'toxicity_score', 'general_score'):
        result[key] = max(float(result.get(key, 0) or 0),
                          float(ocr_signals.get(key, 0) or 0))
    for flag in ('deterministic_grooming', 'deterministic_severe_abuse',
                 'deterministic_self_harm', 'deterministic_dangerous_challenge',
                 'deterministic_sexual'):
        if ocr_signals.get(flag):
            result[flag] = True

    errors = list(result.get('errors') or [])
    errors.append('ocr_text_present')
    if pii.get('detected'):
        errors.append('ocr_pii_detected:' + ','.join(pii.get('categories', []) or []))
    if pii.get('detected') and pii.get('policy_action') == 'BLOCK':
        # Burned-in contact/PII sharing: honored as a hard block by policy.decide.
        result['deterministic_ocr_pii'] = True
        errors.append('ocr_pii_block')
    if ocr_signals.get('total_safety_failure'):
        # OCR text extracted but text models unavailable and no deterministic
        # hits: partial evidence (REVIEW at most), never a bypass, never an
        # escalation of the image to a total failure.
        errors.append('ocr_text_unmoderated')
        result['partial_safety_failure'] = True
    if ocr_signals.get('partial_safety_failure'):
        result['partial_safety_failure'] = True
    result['errors'] = errors
    # Store the redacted form only, so raw PII is not persisted in evidence.
    result['ocr_redacted_text'] = str(pii.get('redacted_text') or '')[:500]
    return result


def _yolo_objects(path):
    """Run the bundled YOLO model and return dangerous-object evidence."""
    global _YOLO
    from ultralytics import YOLO
    weights=(os.getenv('LITTLENET_YOLO_WEIGHTS') or '').strip()
    if not weights:
        weights='yolov8n-oiv7.pt' if os.path.exists('yolov8n-oiv7.pt') else 'yolov8n.pt'
    if not os.path.exists(weights):raise RuntimeError('yolo_weights_missing')
    if _YOLO is None:_YOLO=YOLO(weights)
    results=_YOLO.predict(source=path,verbose=False,device=0 if _runtime_device()=='cuda' else 'cpu',conf=0.20)
    weapon_score=0.0;danger_score=0.0;detections=[]
    weapon_terms=('gun','pistol','rifle','revolver','firearm','weapon','knife','dagger','sword','machete','bow and arrow','crossbow','axe','hatchet','cleaver')
    danger_terms=('grenade','bomb','explosive','chainsaw','dynamite','land mine','landmine')
    for result in results or []:
        names=getattr(result,'names',{}) or {}
        boxes=getattr(result,'boxes',None)
        if boxes is None:continue
        for box in boxes:
            try:
                cls_id=int(box.cls[0].item());conf=float(box.conf[0].item());label=str(names.get(cls_id,cls_id)).lower()
            except Exception:
                continue
            if any(term in label for term in weapon_terms):weapon_score=max(weapon_score,conf)
            if any(term in label for term in danger_terms):danger_score=max(danger_score,conf)
            if conf>=.20:detections.append({'label':label,'confidence':round(conf,4)})
    return {'weapon':max(weapon_score,danger_score),'danger':danger_score,'detections':detections[:25]}


def _merge_yolo_into_trained(path, trained):
    """Defense in depth on the trained-ensemble path.

    The EfficientNet V2/V3 ensemble replaces NudeNet/FalconsAI/CLIP for 18+
    detection, but YOLO dangerous-object detection still runs: its detections
    merge into ``model_signals`` so ``yolo_policy.classify_signals``
    (per-family BLOCK/REVIEW from ``config/safety_policy.yaml``) keeps firing,
    and the weapon score takes the max of both detectors. A YOLO failure is
    recorded as partial safety evidence (REVIEW at most) — never a bypass of
    the trained ensemble result.
    """
    errors = trained.get('errors')
    if not isinstance(errors, list):
        errors = trained['errors'] = list(errors or [])
    try:
        y = timed_call('yolo', lambda: _yolo_objects(path), timeout_seconds('yolo', 90))
    except Exception as exc:
        errors.append('yolo_timeout' if 'timeout' in str(exc).lower() else 'yolo')
        trained['partial_safety_failure'] = True
        return
    try:
        trained['weapon_score'] = max(float(trained.get('weapon_score', 0) or 0),
                                      float(y.get('weapon', 0) or 0))
        trained['general_score'] = max(float(trained.get('general_score', 0) or 0),
                                        float(trained.get('weapon_score', 0) or 0))
    except (TypeError, ValueError):
        pass
    signals = trained.get('model_signals')
    if isinstance(signals, dict):
        signals['yolo'] = y
    if errors:
        trained['partial_safety_failure'] = True


def _apply_ocr_stage(result, path, ocr, ran):
    """Burned-in text screening shared by the trained and legacy image paths.

    ``ocr``: None (default) honors LITTLENET_ENABLE_OCR, which is ON unless
    explicitly set to 0; True/False forces the OCR stage on/off. OCR evidence
    can only strengthen the visual decision: scores merge by max, hard-block
    text flags propagate, and any OCR failure becomes partial safety evidence
    (REVIEW at most), never a bypass.
    """
    if ocr is None:
        ocr = env_flag('LITTLENET_ENABLE_OCR', default=True)
    if not ocr:
        return result
    ocr_text, ocr_error = _ocr_extract_text(path)
    if ocr_error:
        # Fail closed: an OCR stage that ran but could not screen burned-in
        # text (missing backend, timeout, engine failure) is a safety gap,
        # not a silent skip. Unconditional partial evidence -- consistent
        # with _merge_legacy_into_trained's treatment of legacy errors.
        result['errors'].append(ocr_error)
        result['partial_safety_failure'] = True
    elif ocr_text:
        signals = result.get('model_signals')
        if isinstance(signals, dict):
            signals['ocr'] = {'backend': _OCR_BACKEND_NAME, 'text_chars': len(ocr_text)}
        _apply_ocr_evidence(result, ocr_text)
    if ran > 0 and result['errors']:
        result['partial_safety_failure'] = True
    return result


def _legacy_image_scores(path, *, include_yolo=True, extra_errors=()):
    """Run the legacy detector stack and return per-class evidence.

    Never raises: each detector is individually guarded so one failure is
    recorded as partial safety evidence instead of aborting the stack. Scores
    start at 0.0, so a failed detector can never downgrade evidence another
    detector (or the trained ensemble) already produced.
    """
    adult=sexual=violence=weapon=general=0.0;ran=0;errors=list(extra_errors or []);details={}
    for name,fn in [('nudenet',lambda:_nudenet(path)),('falconsai',lambda:_falconsai(path))]:
        try:
            score=float(timed_call(name,fn,timeout_seconds(name,90)));ran+=1;adult=max(adult,score);sexual=max(sexual,score);details[name]=score
        except Exception as exc:errors.append(name+'_timeout' if 'timeout' in str(exc) else name)
    if include_yolo:
        try:
            y=timed_call('yolo',lambda:_yolo_objects(path),timeout_seconds('yolo',90));ran+=1
            weapon=max(weapon,float(y.get('weapon',0) or 0));general=max(general,weapon);details['yolo']=y
        except Exception as exc:errors.append('yolo_timeout' if 'timeout' in str(exc) else 'yolo')
    c=_clip_score(path)
    if c:ran+=1;adult=max(adult,c['adult']);sexual=max(sexual,c.get('sexual',0));violence=max(violence,c['violence']);weapon=max(weapon,c.get('weapon',0));general=max(general,c['general']);details['clip']=c
    else:errors.append('clip')
    if env_flag('LITTLENET_ENABLE_OPENNSFW2'):
        try:
            s=float(timed_call('opennsfw2',lambda:_opennsfw2(path),timeout_seconds('opennsfw2',90)));ran+=1;adult=max(adult,s);sexual=max(sexual,s);details['opennsfw2']=s
        except Exception as exc:errors.append('opennsfw2_timeout' if 'timeout' in str(exc) else 'opennsfw2')
    if env_flag('LITTLENET_ENABLE_EXTRA_NSFW'):
        try:
            s=float(timed_call('extra_nsfw',lambda:_extra_hf_nsfw(path),timeout_seconds('extra_nsfw',90)));ran+=1;adult=max(adult,s);sexual=max(sexual,s);details['extra_nsfw']=s
        except Exception as exc:errors.append('extra_nsfw_timeout' if 'timeout' in str(exc) else 'extra_nsfw')
    return {'adult':adult,'sexual':sexual,'violence':violence,'weapon':weapon,'general':general,'ran':ran,'errors':errors,'details':details}


# Legacy block lines per class, mirroring the legacy path's own category rule:
# adult_block for 18+ evidence, weapon_block for weapons. The trained
# ensemble's per-class thresholds are tuned higher than these; the merge
# below guarantees the trained path can only strengthen the legacy verdict.
_LEGACY_BLOCK_LINES={'nudity':0.40,'sexy':0.40,'weapons':0.45,'violence':0.48}


def _merge_legacy_into_trained(path, trained):
    """Defense in depth: run the legacy detector stack alongside the trained
    ensemble and merge evidence by max.

    The trained ensemble replaces NudeNet/FalconsAI/CLIP on this path, but
    its per-class thresholds are tuned higher than the legacy block lines
    (e.g. trained nudity threshold 0.89 vs legacy 0.40). Without this merge,
    any image the legacy stack would BLOCK but the ensemble scores below its
    own threshold would flip to ALLOW the day the checkpoints are staged --
    including images where the ensemble scores low but a legacy detector
    fires. Merging per-class by max guarantees the trained path can only
    strengthen the legacy verdict, never weaken it. Fail-closed: the legacy
    helper never raises and scores merge by max only, so a legacy-detector
    failure can never downgrade a trained BLOCK; it is recorded as partial
    safety evidence instead. YOLO is not run here:
    _merge_yolo_into_trained covers it on this path.
    """
    legacy=_legacy_image_scores(path, include_yolo=False)
    try:
        trained['adult_score']=max(float(trained.get('adult_score',0) or 0),legacy['adult'],legacy['sexual'])
        trained['sexual_score']=max(float(trained.get('sexual_score',0) or 0),legacy['sexual'],legacy['adult'])
        trained['violence_score']=max(float(trained.get('violence_score',0) or 0),legacy['violence'])
        trained['weapon_score']=max(float(trained.get('weapon_score',0) or 0),legacy['weapon'])
        trained['general_score']=max(float(trained.get('general_score',0) or 0),legacy['general'],trained['adult_score'],trained['sexual_score'],trained['violence_score'],trained['weapon_score'])
    except (TypeError,ValueError):pass
    # The merged category must reflect legacy verdicts so policy.decide sees
    # them (mirrors the legacy path's own category rule).
    if max(legacy['adult'],legacy['sexual'])>=0.40:
        trained['category']='ADULT'
    elif legacy['weapon']>=0.45 and str(trained.get('category','')).upper()!='ADULT':
        trained['category']='WEAPON'
    errors=trained.get('errors')
    if not isinstance(errors,list):errors=trained['errors']=list(errors or [])
    errors.extend(legacy['errors'])
    signals=trained.get('model_signals')
    if isinstance(signals,dict):signals['legacy']=legacy['details']
    if legacy['errors']:trained['partial_safety_failure']=True


def check_image(path, *, ocr=None):
    """Moderate an image through the local visual stack plus optional OCR.

    ``ocr``: None (default) honors LITTLENET_ENABLE_OCR, which is ON unless
    explicitly set to 0; True/False forces the OCR stage on/off. Video frame
    samplers pass False unless LITTLENET_ENABLE_OCR_VIDEO_FRAMES=1 so
    per-frame OCR stays bounded.
    """
    # Prefer the scale-to-zero CPU tier for all web-side image moderation,
    # including the legacy/Jinja upload path. Inside an AI worker this client is
    # disabled, so local model execution continues without recursion.
    if os.getenv('LITTLENET_AI_SERVER') != '1':
        try:
            from services.modal_image_moderation import (
                allow_gpu_fallback as image_gpu_fallback_allowed,
                enabled as modal_image_cpu_enabled,
                moderate_image_upload as moderate_image_upload_cpu,
            )
            if modal_image_cpu_enabled():
                try:
                    result=moderate_image_upload_cpu(path,run_text=False,run_media=True)
                    signals=result.get('media_signals') or {}
                    signals['compute_tier']='modal_cpu'
                    return normalize_signals(signals,category='IMAGE')
                except Exception:
                    if not image_gpu_fallback_allowed():
                        return normalize_signals({
                            'category':'IMAGE',
                            'total_safety_failure':True,
                            'errors':['modal_cpu_image_moderation_unavailable'],
                            'compute_tier':'modal_cpu_failed_closed',
                        },category='IMAGE')
        except Exception:
            pass

    from .remote_client import enabled,moderate_file
    if enabled():
        try:return normalize_signals(moderate_file('IMAGE',path),category='IMAGE')
        except Exception:return normalize_signals({'category':'IMAGE','total_safety_failure':True,'errors':['remote_ai_unavailable']},category='IMAGE')

    # Preferred local path once the private V2/V3 checkpoints are staged on the
    # persistent Modal model-cache volume. The two EfficientNet-B0 specialists
    # run first; the legacy detector stack (NudeNet/FalconsAI/CLIP) then also
    # runs and merges by max (_merge_legacy_into_trained), so the trained path
    # can only strengthen the legacy verdict, never weaken it. YOLO
    # dangerous-object detection and the OCR burned-in-text stage still run on
    # this path (defense in depth). If either checkpoint is missing or
    # inference fails, the existing detector stack remains the fail-safe
    # fallback.
    trained_error=None
    try:
        from . import littlenet_trained_image
        if littlenet_trained_image.available():
            try:
                trained=littlenet_trained_image.predict(path)
                trained['compute_tier']='trained_cpu' if _runtime_device()=='cpu' else 'trained_gpu'
                _merge_legacy_into_trained(path, trained)
                _merge_yolo_into_trained(path, trained)
                _apply_ocr_stage(trained, path, ocr, 1)
                return normalize_signals(trained,category='IMAGE')
            except Exception as exc:
                trained_error=f'trained_image:{type(exc).__name__}'
    except Exception as exc:
        trained_error=f'trained_image_loader:{type(exc).__name__}'

    legacy=_legacy_image_scores(path, extra_errors=[trained_error] if trained_error else [])
    adult=legacy['adult'];sexual=legacy['sexual'];violence=legacy['violence'];weapon=legacy['weapon'];general=legacy['general'];ran=legacy['ran'];errors=legacy['errors'];details=legacy['details']
    result={'adult_score':adult,'sexual_score':sexual,'violence_score':violence,'weapon_score':weapon,'toxicity_score':0,'general_score':max(general,adult,sexual,violence,weapon),'category':'ADULT' if max(adult,sexual)>=.4 else ('WEAPON' if weapon>=.45 else 'IMAGE'),'total_safety_failure':ran==0,'partial_safety_failure':ran>0 and bool(errors),'errors':errors,'model_signals':details}
    # Burned-in text screening (shared stage; see _apply_ocr_stage).
    _apply_ocr_stage(result, path, ocr, ran)
    return normalize_signals(result,category='IMAGE')


def video_duration_seconds(path):
    try:
        r=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',path],capture_output=True,text=True,timeout=15,check=True);return float((r.stdout or '0').strip() or 0)
    except Exception:
        try:
            import cv2;c=cv2.VideoCapture(path);fps=c.get(cv2.CAP_PROP_FPS) or 0;frames=c.get(cv2.CAP_PROP_FRAME_COUNT) or 0;c.release();return frames/fps if fps else 0
        except Exception:return 0


def _audio_from_video(_path):
    """Retired compatibility symbol. Video moderation is frames only."""
    return None


def _retired_video_audio_contract(ap=None):
    """Never executed; keeps older import-level contracts fail-closed during migration."""
    if False:  # pragma: no cover - standalone/video audio is intentionally retired
        from .audio_service import check_audio
        return check_audio(ap)
    return None


def _video_sample_count(path,max_frames=None):
    """Choose a small scene-aware/time-distributed frame budget with a hard cap."""
    if max_frames is not None:
        try:return max(1,int(max_frames))
        except (TypeError,ValueError):pass
    duration=max(0.0,video_duration_seconds(path))
    try:interval=max(2.0,float(os.getenv('LITTLENET_VIDEO_SAMPLE_INTERVAL_SECONDS','8')))
    except ValueError:interval=8.0
    try:min_frames=max(2,int(os.getenv('LITTLENET_VIDEO_MIN_FRAMES','3')))
    except ValueError:min_frames=3
    try:cap=max(min_frames,int(os.getenv('LITTLENET_VIDEO_MAX_FRAMES','8')))
    except ValueError:cap=8
    desired=max(min_frames,int(math.ceil(max(duration,1.0)/interval))+1)
    return min(cap,desired)


def video_sampling_coverage(path, requested):
    """Describe whether the bounded sample meets the auto-allow time-gap contract."""
    duration=max(0.0,video_duration_seconds(path))
    try:max_gap=max(2.0,float(os.getenv('LITTLENET_VIDEO_MAX_AUTO_ALLOW_GAP_SECONDS','12')))
    except ValueError:max_gap=12.0
    required=max(1,int(math.ceil(duration/max_gap))+1) if duration else 1
    return {
        'duration_seconds':round(duration,3),
        'max_auto_allow_gap_seconds':max_gap,
        'required_frames_for_auto_allow':required,
        'coverage_complete':int(requested)>=required,
    }


def _video_frames(path,max_frames):
    import cv2
    from .policy import decide
    cap=cv2.VideoCapture(path);total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    idxs=combined_frame_indices(path,total,max_frames);outs=[]
    for idx in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES,idx);good,frame=cap.read()
        if not good:continue
        fd,tmp=tempfile.mkstemp(suffix='.jpg');os.close(fd);cv2.imwrite(tmp,frame)
        try:
            # Frame OCR stays off unless explicitly enabled: OCR across the
            # bounded video frame set can otherwise dominate moderation time.
            signals=check_image(tmp,ocr=env_flag('LITTLENET_ENABLE_OCR_VIDEO_FRAMES'));outs.append(signals)
            if decide(signals).action=='BLOCK':break
        finally:
            try:os.unlink(tmp)
            except OSError:pass
    cap.release();return outs


def check_video(path,max_frames=None):
    from .remote_client import enabled,moderate_file
    if enabled():
        try:return normalize_signals(moderate_file('VIDEO',path),category='VIDEO')
        except Exception:return normalize_signals({'category':'VIDEO','total_safety_failure':True,'errors':['remote_ai_unavailable']},category='VIDEO')
    try:
        requested=_video_sample_count(path,max_frames)
        coverage=video_sampling_coverage(path,requested)
        outs=timed_call('video_frames',lambda:_video_frames(path,requested),timeout_seconds('video_frames',240))
        if not outs:return normalize_signals({'total_safety_failure':True,'category':'VIDEO','errors':['no_video_frames']},category='VIDEO')
        keys=['adult_score','sexual_score','weapon_score','violence_score','general_score'];out={k:max(float(x.get(k,0)) for x in outs) for k in keys};out['toxicity_score']=0
        out['partial_safety_failure']=(not coverage['coverage_complete']) or any(x.get('partial_safety_failure') for x in outs);out['total_safety_failure']=all(x.get('total_safety_failure') for x in outs);out['errors']=[err for x in outs for err in x.get('errors',[])]
        if not coverage['coverage_complete']:out['errors'].append('video_temporal_coverage_incomplete')
        out['model_signals']={'sampled_frames':len(outs),'requested_frames':requested,'sampling':'scene+uniform',**coverage,'frames':[x.get('model_signals',{}) for x in outs]}
        out['category']='ADULT' if max(out['adult_score'],out['sexual_score'])>=.4 else ('WEAPON' if out['weapon_score']>=.45 else 'VIDEO')
        return normalize_signals(out,category='VIDEO')
    except Exception as exc:return normalize_signals({'total_safety_failure':True,'category':'VIDEO','errors':['video_timeout' if 'timeout' in str(exc) else 'video_processing']},category='VIDEO')
