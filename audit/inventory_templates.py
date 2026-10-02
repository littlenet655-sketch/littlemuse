import os
import re
import json

routes_code = ""
for root, dirs, files in os.walk('.'):
    if any(k in root for k in ['.git', '.venv', 'node_modules']): continue
    for f in files:
        if f.endswith('.py'):
            with open(os.path.join(root, f), 'r', encoding='utf-8', errors='ignore') as pf:
                routes_code += pf.read() + "\n"

templates = []
for root, dirs, files in os.walk('.'):
    if any(k in root for k in ['.git', '.venv', 'node_modules']): continue
    for f in files:
        if f.endswith('.html'):
            p = os.path.relpath(os.path.join(root, f), '.').replace('\\', '/')
            base = os.path.basename(p)
            
            # check if referenced
            is_referenced = base in routes_code or p in routes_code
            templates.append({
                "path": p,
                "referenced_in_python": is_referenced,
                "is_admin_operator": "admin" in p or "moderation" in p,
                "is_parent": "parent" in p,
                "is_child": "child" in p,
                "is_auth": "auth" in p or "login" in p
            })

referenced_count = sum(1 for t in templates if t['referenced_in_python'])
print(f"Total templates: {len(templates)}")
print(f"Referenced in Python routes/tests: {referenced_count}")
print(f"Unreferenced: {len(templates) - referenced_count}")

with open("audit/templates_inventory.json", "w", encoding="utf-8") as f:
    json.dump(templates, f, indent=2)
