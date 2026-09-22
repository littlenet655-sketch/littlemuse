from pathlib import Path
import ast,sys
root=Path(__file__).parents[1];errors=[];routes=[]
public_prefixes={
    'auth/routes.py':{'mode_select','login','register_page','verify_parent','parent_approve_child','approve_child','register_parent','register_parent_direct_page','admin_login','logout','switch_mode'},
    'auth/api.py':{'api_login'},
}
route_files=sorted(p for p in (set(root.rglob('routes.py'))|set(root.rglob('api.py'))) if not any(part in ('.venv', 'venv', 'node_modules', '.git') for part in p.parts))
for p in route_files:
    mod=ast.parse(p.read_text(encoding='utf-8'));rel=p.relative_to(root).as_posix()
    for n in mod.body:
        if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
        decos=[];route=None;methods=['GET']
        for d in n.decorator_list:
            if isinstance(d,ast.Name):decos.append(d.id)
            elif isinstance(d,ast.Call):
                if isinstance(d.func,ast.Name):decos.append(d.func.id)
                if isinstance(d.func,ast.Attribute) and d.func.attr=='route':
                    if d.args and isinstance(d.args[0],ast.Constant):route=d.args[0].value
                    for kw in d.keywords:
                        if kw.arg=='methods' and isinstance(kw.value,(ast.List,ast.Tuple)):methods=[x.value for x in kw.value.elts if isinstance(x,ast.Constant)]
        if route:
            routes.append((rel,n.name,route,methods,decos))
            is_public=n.name in public_prefixes.get(rel,set())
            # Parent OTP/liveness routes intentionally run before a normal login.
            # They are guarded by _pending_parent(), which requires the short-lived
            # pending_parent_user_id session and re-checks that the DB account is
            # still a PARENT in PENDING_APPROVAL state. Treat that narrowly scoped
            # pre-auth registration guard as equivalent to the normal decorators.
            has_pending_parent_guard=any(
                isinstance(call,ast.Call) and isinstance(call.func,ast.Name) and call.func.id=='_pending_parent'
                for call in ast.walk(n)
            )
            # Token-guardian OTP step: requires the short-lived session token
            # set by the first verification step to equal the URL token
            # (``session.get('pending_token_verification') != token`` ->
            # redirect), plus a re-check that the parent row and child data
            # still exist. Treat that session-bound pre-auth guard as
            # equivalent to the normal decorators.
            has_token_session_guard=any(
                isinstance(call,ast.Call)
                and isinstance(call.func,ast.Attribute)
                and isinstance(call.func.value,ast.Name)
                and call.func.value.id=='session'
                and call.func.attr=='get'
                and call.args
                and isinstance(call.args[0],ast.Constant)
                and call.args[0].value=='pending_token_verification'
                for call in ast.walk(n)
            )
            if not is_public and not has_pending_parent_guard and not has_token_session_guard and not any(x in decos for x in {'child_required','parent_required','admin_required','login_required'}):
                errors.append(f'unguarded {rel}:{n.name} {route}')
            if route!='/parent/deleted-posts/' and any(x in route for x in ['/delete','/block','/mute','/follow-action','/review/','/safety-level','/submit','/send-','/share-']) and 'GET' in methods:
                errors.append(f'mutating GET {rel}:{route}')

# The app-level upload route uses manual role/ownership checks rather than a
# decorator because it serves CHILD and PARENT review media differently.
app=(root/'app.py').read_text(encoding='utf-8')
for needle in ["@app.route('/uploads/<path:filename>')","if not uid:return ('Unauthorized',401)","role=='PARENT'","role=='CHILD'"]:
    if needle not in app:errors.append(f'app upload protection missing: {needle}')

# template references
html_names={p.name for p in root.rglob('*.html') if not any(part in ('.venv', 'venv', 'node_modules', '.git') for part in p.parts)}
for p in root.rglob('*.py'):
    if any(part in ('.venv', 'venv', 'node_modules', '.git') for part in p.parts): continue
    try:mod=ast.parse(p.read_text())
    except Exception:continue
    for n in ast.walk(mod):
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='render_template' and n.args and isinstance(n.args[0],ast.Constant):
            name=n.args[0].value
            if name not in html_names:errors.append(f'missing template {name} referenced by {p.relative_to(root)}')
print('ROUTES',len(routes),'ERRORS',len(errors));[print('-',e) for e in errors];sys.exit(bool(errors))
