from pathlib import Path
import ast,re,sys,os
root=Path(__file__).parents[1];fail=[]
for p in root.rglob('*.py'):
 if any(x in p.parts for x in ('__pycache__', '.venv', 'venv')):continue
 try:ast.parse(p.read_text(encoding='utf-8'))
 except Exception as e:fail.append(f'PY {p.relative_to(root)}: {e}')
schema=(root/'database/schema.sql').read_text()
for table in ['users','parent_child_map','posts','likes','comments','followers','child_messages','notifications','child_time_limits','child_usage_sessions','quizzes','moderation_events','moderation_reviews','reports','blocked_users','muted_users']:
 if f'CREATE TABLE IF NOT EXISTS {table}' not in schema:fail.append('SCHEMA '+table)
# A real handoff/export must not contain repository metadata. GitHub Actions,
# however, necessarily checks the source out as a Git worktree; CI=true is set
# by GitHub and other standard CI providers, so do not fail for that environment.
if (root/'.git').exists() and not os.getenv('CI') and not os.getenv('LITTLENET_ALLOW_GIT') and '--allow-git' not in sys.argv:fail.append('Git metadata must not exist in local export')
print('PREFLIGHT:', 'PASS' if not fail else 'FAIL');[print('-',x) for x in fail];sys.exit(bool(fail))
