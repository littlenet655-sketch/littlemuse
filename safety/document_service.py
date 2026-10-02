import os,tempfile,zipfile
from defusedxml import ElementTree as ET
from .text_service import check_text
from .visual_service import check_image

def _merge(signals, partial=False):
    out = {
        'adult_score': 0.0,
        'violence_score': 0.0,
        'weapon_score': 0.0,
        'toxicity_score': 0.0,
        'general_score': 0.0,
        'category': 'FILE',
        'partial_safety_failure': partial,
        'total_safety_failure': False,
        'sources': [],
        'model_signals': {},
    }
    for s in signals:
        if not s:
            continue
        for k in ['adult_score', 'violence_score', 'weapon_score', 'toxicity_score', 'general_score']:
            out[k] = max(out[k], float(s.get(k, 0) or 0))
        if s.get('partial_safety_failure'):
            out['partial_safety_failure'] = True
        if s.get('total_safety_failure'):
            out['total_safety_failure'] = True
        out['sources'].append(s.get('category', 'UNKNOWN'))
        if isinstance(s.get('model_signals'), dict):
            out['model_signals'].update(s['model_signals'])
        for k, v in s.items():
            if k.endswith('_score') and k not in out:
                out[k] = v
                out['model_signals'][k] = v

    out['category'] = 'ADULT' if out['adult_score'] >= .4 else ('WEAPON' if out['weapon_score'] >= .45 else 'FILE')
    return out

def _docx(path):
    sig = []
    partial = False
    with zipfile.ZipFile(path) as z:
        try:
            root = ET.fromstring(z.read('word/document.xml'))
            text = ' '.join((n.text or '') for n in root.iter() if n.text)
            sig.append(check_text(text[:100000]))
        except Exception:
            sig.append({'partial_safety_failure': True, 'category': 'DOCX_TEXT'})
            partial = True
        media_files = [n for n in z.namelist() if n.startswith('word/media/')]
        if len(media_files) > 20:
            partial = True
        for name in media_files[:20]:
            suffix = os.path.splitext(name)[1].lower()
            if suffix not in {'.jpg', '.jpeg', '.png', '.webp'}:
                continue
            fd, tmp = tempfile.mkstemp(suffix=suffix)
            os.close(fd)
            try:
                with open(tmp, 'wb') as f:
                    f.write(z.read(name))
                sig.append(check_image(tmp))
            finally:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
    return _merge(sig, partial=partial)

def _pdf(path):
    # Text is AI-moderated, but the PDF remains REVIEW because arbitrary page graphics are not rendered/scanned here.
    try:
        from pypdf import PdfReader
        r=PdfReader(path);text=' '.join((p.extract_text() or '') for p in r.pages[:50]);return _merge([check_text(text[:100000])],partial=True)
    except Exception:return _merge([],partial=True)

def check_document(path,ext):
    ext=ext.lower().lstrip('.')
    if ext=='txt':
        try:
            with open(path,'r',encoding='utf-8',errors='ignore') as f:return _merge([check_text(f.read(100000))])
        except Exception:return _merge([],partial=True)
    if ext=='docx':return _docx(path)
    if ext=='pdf':return _pdf(path)
    return {'adult_score':0,'general_score':0,'category':'FILE','partial_safety_failure':True,'total_safety_failure':False}
