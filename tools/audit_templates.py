from pathlib import Path
import re,sys
R=Path(__file__).parents[1];errors=[]
# CSRF on every normal POST form.
for p in R.rglob('*.html'):
    if any(part in ('.venv', 'venv', 'node_modules', '.git') for part in p.parts): continue
    s=p.read_text(encoding='utf-8')
    for m in re.finditer(r'<form\b[^>]*method=["\']post["\'][^>]*>(.*?)</form>',s,re.I|re.S):
        if 'csrf_token' not in m.group(1):errors.append(f'POST form missing CSRF: {p.relative_to(R)}')
    for href in re.findall(r'href=["\']([^"\']+)["\']',s,re.I):
        if any(k in href for k in ['/logout','/switch-mode','/delete-','/block/','/mute/','/unfollow/','/approve-follow','/reject-follow']):errors.append(f'mutating link: {p.relative_to(R)} -> {href}')
# Strict CSP compatibility: all UI behavior must live in external JavaScript.
# Inline event handlers such as onclick/onchange/onerror would be blocked by the
# production Content-Security-Policy and can create browser-only regressions.
for p in R.rglob('*.html'):
    if any(part in ('.venv', 'venv', 'node_modules', '.git') for part in p.parts): continue
    s=p.read_text(encoding='utf-8')
    for m in re.finditer(r'\son[a-z]+\s*=',s,re.I):
        errors.append(f'inline event handler blocked by CSP: {p.relative_to(R)}')

# Important templates must not collide by basename; Flask blueprint lookup can otherwise resolve the wrong role UI.
seen={}
for p in R.rglob('templates/*.html'):
    if any(part in ('.venv', 'venv', 'node_modules', '.git') for part in p.parts): continue
    if p.name in seen:errors.append(f'duplicate template basename: {p.name}: {seen[p.name]} / {p.relative_to(R)}')
    seen[p.name]=p.relative_to(R)
# Social media should be lazy/preload-aware rather than eagerly loading entire feeds.
css=(R/'static/css/littlenet.css').read_text(encoding='utf-8');js=(R/'static/js/littlenet.js').read_text(encoding='utf-8')
if 'scroll-snap-type:y mandatory' not in css:errors.append('Reels vertical scroll snap missing')
if 'IntersectionObserver' not in js:errors.append('visible-video observer missing')
html_files=[p for p in R.rglob('*.html') if not any(part in ('.venv', 'venv', 'node_modules', '.git') for part in p.parts)]
print('TEMPLATES',len(html_files),'ERRORS',len(errors));[print('-',e) for e in errors];sys.exit(bool(errors))
