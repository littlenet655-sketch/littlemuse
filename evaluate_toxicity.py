"""Evaluate a frozen moderation decision export against declared labels.

This is an offline *measurement* tool, not a training script and not a model
loader.  It deliberately requires a prediction CSV rather than downloading a
model or silently selecting the first rows of a dataset.  The CSV must contain
``id``, ``expected_action`` and ``predicted_action`` columns, with actions
``ALLOW``, ``REVIEW`` or ``BLOCK``.

The resulting metrics describe agreement with this particular labelled
dataset only.  They are not a claim about live effectiveness, generalisation,
or any adult-content/age-estimation performance.  See
``docs/MODERATION_BENCHMARK_PROTOCOL.md`` for the submission protocol.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Iterable, Mapping


ACTIONS = ("ALLOW", "REVIEW", "BLOCK")
REQUIRED_COLUMNS = ("id", "expected_action", "predicted_action")


def _action(value: object, *, field: str, row_id: str) -> str:
    action = str(value or "").strip().upper()
    if action not in ACTIONS:
        raise ValueError(
            f"{field} for row {row_id!r} must be one of {', '.join(ACTIONS)}"
        )
    return action


def load_predictions(path: str | Path) -> list[dict[str, str]]:
    """Load and validate a prediction export without changing row order."""

    csv_path = Path(path)
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("prediction CSV has no header")
        missing = [name for name in REQUIRED_COLUMNS if name not in reader.fieldnames]
        if missing:
            raise ValueError(f"prediction CSV is missing columns: {', '.join(missing)}")

        rows: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        for line_number, raw in enumerate(reader, start=2):
            row_id = str(raw.get("id") or "").strip()
            if not row_id:
                raise ValueError(f"prediction CSV row {line_number} has an empty id")
            if row_id in seen_ids:
                raise ValueError(f"duplicate prediction id: {row_id}")
            seen_ids.add(row_id)
            rows.append(
                {
                    "id": row_id,
                    "expected_action": _action(
                        raw.get("expected_action"), field="expected_action", row_id=row_id
                    ),
                    "predicted_action": _action(
                        raw.get("predicted_action"), field="predicted_action", row_id=row_id
                    ),
                }
            )

    if not rows:
        raise ValueError("prediction CSV contains no data rows")
    return rows


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def evaluate_rows(rows: Iterable[Mapping[str, object]]) -> dict[str, object]:
    """Return deterministic action-level metrics for already validated rows."""

    materialized = list(rows)
    if not materialized:
        raise ValueError("cannot evaluate an empty prediction set")

    confusion = {expected: {predicted: 0 for predicted in ACTIONS} for expected in ACTIONS}
    seen_ids: set[str] = set()
    for index, row in enumerate(materialized, start=1):
        row_id = str(row.get("id") or f"row-{index}")
        if row_id in seen_ids:
            raise ValueError(f"duplicate prediction id: {row_id}")
        seen_ids.add(row_id)
        expected = _action(row.get("expected_action"), field="expected_action", row_id=row_id)
        predicted = _action(row.get("predicted_action"), field="predicted_action", row_id=row_id)
        confusion[expected][predicted] += 1

    per_action: dict[str, dict[str, object]] = {}
    f1_values: list[float] = []
    total = len(materialized)
    for action in ACTIONS:
        true_positive = confusion[action][action]
        false_positive = sum(
            confusion[other][action] for other in ACTIONS if other != action
        )
        false_negative = sum(
            confusion[action][other] for other in ACTIONS if other != action
        )
        precision = _rate(true_positive, true_positive + false_positive)
        recall = _rate(true_positive, true_positive + false_negative)
        f1 = _rate(2 * precision * recall, precision + recall)
        f1_values.append(f1)
        per_action[action] = {
            "support": sum(confusion[action].values()),
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }

    exact_agreement = sum(
        confusion[action][action] for action in ACTIONS
    )
    return {
        "schema_version": 1,
        "scope": "offline_decision_benchmark",
        "n": total,
        "offline_exact_action_agreement": _rate(exact_agreement, total),
        "macro_f1": _rate(sum(f1_values), len(f1_values)),
        "confusion_matrix": confusion,
        "per_action": per_action,
        "interpretation": (
            "Dataset-only metrics for the frozen policy/model run; "
            "not live effectiveness or external validation."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure frozen moderation decisions against a labelled CSV."
    )
    parser.add_argument(
        "--predictions",
        required=True,
        type=Path,
        help="CSV with id, expected_action, predicted_action columns",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="optional JSON report path (stdout is used when omitted)",
    )
    args = parser.parse_args()
    report = evaluate_rows(load_predictions(args.predictions))
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())