import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _question_rows():
    source = (ROOT / "tools/seed_quizzes.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    env = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {"QUESTIONS", "EXTRA_QUESTIONS"}:
                    env[target.id] = ast.literal_eval(node.value)
    return list(env.get("QUESTIONS", [])) + list(env.get("EXTRA_QUESTIONS", []))


def test_static_quiz_bank_is_large_and_age_complete():
    rows = _question_rows()
    assert 220 <= len(rows) <= 300
    groups = {}
    for row in rows:
        assert len(row) == 8
        category, question, a, b, c, d, correct, age_group = row
        assert category and question
        assert correct in {a, b, c, d}
        groups[age_group] = groups.get(age_group, 0) + 1
    assert set(groups) == {"6-8", "9-11", "12-13", "14-18"}
    assert groups["14-18"] >= 40
    assert min(groups.values()) >= 40


def test_deploy_seeds_bank_after_migrations():
    entry = (ROOT / "docker-entrypoint.sh").read_text(encoding="utf-8")
    migration = 'dbmate --no-dump-schema --migrations-dir "${DBMATE_MIGRATIONS_DIR:-db/migrations}" up'
    seed = "python tools/seed_quizzes.py"
    assert migration in entry
    assert seed in entry
    assert entry.index(migration) < entry.index(seed) < entry.index("exec gunicorn")
