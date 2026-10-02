import os
import ast
import traceback

errors = []
total_py = 0

for root, dirs, files in os.walk('.'):
    if any(k in root for k in ['.git', '.venv', 'node_modules', '__pycache__']):
        continue
    for f in files:
        if f.endswith('.py'):
            total_py += 1
            path = os.path.join(root, f)
            try:
                with open(path, 'r', encoding='utf-8') as py_f:
                    code = py_f.read()
                ast.parse(code, filename=path)
            except Exception as e:
                errors.append({"file": path, "error": str(e), "traceback": traceback.format_exc()})

print(f"Total Python files parsed: {total_py}")
print(f"AST Parsing syntax errors: {len(errors)}")
for err in errors:
    print(f"  FAILED: {err['file']} -> {err['error']}")

with open('audit/evidence/ast_parse_results.txt', 'w', encoding='utf-8') as out_f:
    out_f.write(f"Total Python files: {total_py}\nSyntax Errors: {len(errors)}\n")
    for err in errors:
        out_f.write(f"\n{err['file']}:\n{err['error']}\n{err['traceback']}\n")
