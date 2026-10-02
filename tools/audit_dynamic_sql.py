"""Fail CI on f-string SQL except LittleNet's single fixed content-approval whitelist.

Bandit's B608 cannot distinguish a hard-coded identifier whitelist from user-driven
SQL. This audit is intentionally narrower and stricter for LittleNet: every call
to execute/fetch_one/fetch_all using an f-string is rejected unless it is inside
parent.routes.content_approval and interpolates only the exact internally defined
(table, primary-key) pairs below. Query *values* must still use DB parameters.
"""
from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ["admin", "auth", "child", "childMessage", "parent", "quiz", "safety", "services", "uploadPost"]
DB_CALLS = {"execute", "fetch_one", "fetch_all"}
ALLOWED_PAIRS = {
    ("child_skills", "skill_id"),
    ("child_interests", "interest_id"),
    ("child_ambitions", "ambition_id"),
}


def call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def enclosing_function(tree: ast.AST, target: ast.AST) -> str | None:
    # AST has no parent pointers; find the smallest function containing the call.
    result = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if target in set(ast.walk(node)):
                result = node.name
    return result


def main() -> int:
    errors: list[str] = []
    dynamic_calls = 0
    allowed_calls = 0

    for directory in SCAN_DIRS:
        for path in (ROOT / directory).rglob("*.py"):
            try:
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(path))
            except Exception as exc:
                errors.append(f"cannot parse {path.relative_to(ROOT)}: {exc}")
                continue

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or call_name(node) not in DB_CALLS or not node.args:
                    continue
                query = node.args[0]
                if not isinstance(query, ast.JoinedStr):
                    continue
                dynamic_calls += 1
                rel = path.relative_to(ROOT).as_posix()
                func = enclosing_function(tree, node)
                names = {
                    value.value.id
                    for value in query.values
                    if isinstance(value, ast.FormattedValue) and isinstance(value.value, ast.Name)
                }
                if rel == "parent/routes.py" and func == "content_approval" and names.issubset({"table", "col"}):
                    allowed_calls += 1
                    continue
                errors.append(f"dynamic SQL forbidden: {rel}:{getattr(node, 'lineno', '?')} ({func or 'module'})")

    # The only exception is safe only while the source contains this exact identifier whitelist.
    parent_routes = (ROOT / "parent" / "routes.py").read_text(encoding="utf-8")
    expected = "[('child_skills','skill_id'),('child_interests','interest_id'),('child_ambitions','ambition_id')]"
    if expected not in parent_routes:
        errors.append("content_approval SQL whitelist changed; security review required")
    if allowed_calls != 2:
        errors.append(f"expected exactly 2 approved identifier-format SQL calls, found {allowed_calls}")

    print(f"DYNAMIC_SQL_CALLS {dynamic_calls} APPROVED {allowed_calls} ERRORS {len(errors)}")
    for error in errors:
        print("-", error)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
