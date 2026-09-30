from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd


MANUAL_REVIEW_DECISIONS_FILENAME = "step_4_manual_review_decisions_checkpoint.csv"
MANUALLY_REVIEWED_TAG = "MANUALLY_REVIEWED"
OPEN_REVIEW_TAG = "PENDING_MANUAL_REVIEW"
MANUAL_OVERRIDE_ISSUE_PREFIX = "override_"
APPROVED_DECISIONS = {"APPROVED", "CORRECTED", "NOT_APPLICABLE"}

DECISION_COLUMNS = [
    "decision_id",
    "issue_id",
    "invoice_id",
    "line_id",
    "field_name",
    "original_value",
    "corrected_value",
    "review_decision",
    "review_tag",
    "reviewed_by",
    "reviewed_at",
    "review_comment",
]

EDITABLE_DECISION_COLUMNS = {
    "corrected_value",
    "review_decision",
    "review_tag",
    "reviewed_by",
    "reviewed_at",
    "review_comment",
}


def build_manual_decision_rows(
    issue_rows: list[Mapping[str, Any]],
    existing_decision_rows: list[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    existing_rows = existing_decision_rows or []
    existing_by_issue_id = {
        str(row.get("issue_id", "")): row
        for row in existing_rows
        if row.get("issue_id")
    }
    existing_by_stable_key = {
        _stable_decision_key(row): row
        for row in existing_rows
        if _stable_decision_key(row)
    }

    decision_rows = []
    for issue in issue_rows:
        issue_id = str(issue.get("issue_id", ""))
        base_row = _new_decision_row(issue)
        existing_row = existing_by_issue_id.get(issue_id) or existing_by_stable_key.get(_stable_issue_key(issue))
        if existing_row:
            base_row.update({
                column: existing_row.get(column, "")
                for column in EDITABLE_DECISION_COLUMNS
            })
        decision_rows.append(base_row)

    existing_issue_ids = {str(row.get("issue_id", "")) for row in decision_rows}
    for row in existing_rows:
        issue_id = str(row.get("issue_id", ""))
        if not issue_id.startswith(MANUAL_OVERRIDE_ISSUE_PREFIX) or issue_id in existing_issue_ids:
            continue
        decision_rows.append(_decision_row_with_default_columns(row))
        existing_issue_ids.add(issue_id)

    return decision_rows


def write_manual_decisions_checkpoint(
    issue_rows: list[dict],
    output_dir: str | Path,
    filename: str = MANUAL_REVIEW_DECISIONS_FILENAME,
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    target = output_path / filename

    existing_rows = _read_existing_decisions(target)
    decision_rows = build_manual_decision_rows(issue_rows, existing_rows)
    pd.DataFrame(decision_rows, columns=DECISION_COLUMNS).to_csv(target, index=False, encoding="utf-8-sig")

    return target


def load_manual_decision_rows(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    return pd.read_csv(path, dtype=object, keep_default_na=False, encoding="utf-8-sig").to_dict("records")


def is_approved_decision(row: Mapping[str, Any]) -> bool:
    return str(row.get("review_decision", "")).strip().upper() in APPROVED_DECISIONS


def reopen_manual_decision_rows(
    decision_rows: Iterable[Mapping[str, Any]],
    issue_ids: Iterable[str],
) -> list[dict[str, Any]]:
    reopened_issue_ids = {str(issue_id) for issue_id in issue_ids}
    rows = []
    for decision in decision_rows:
        row = dict(decision)
        if str(row.get("issue_id", "")) in reopened_issue_ids:
            row["corrected_value"] = ""
            row["review_decision"] = ""
            row["review_tag"] = OPEN_REVIEW_TAG
            row["reviewed_by"] = ""
            row["reviewed_at"] = ""
            row["review_comment"] = ""
        rows.append(row)
    return rows


def reviewed_at_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _new_decision_row(issue: Mapping[str, Any]) -> dict[str, Any]:
    issue_id = str(issue.get("issue_id", ""))
    return {
        "decision_id": f"decision_{issue_id}",
        "issue_id": issue_id,
        "invoice_id": issue.get("invoice_id", ""),
        "line_id": issue.get("line_id", ""),
        "field_name": issue.get("field_name", ""),
        "original_value": issue.get("ocr_value", ""),
        "corrected_value": "",
        "review_decision": "",
        "review_tag": OPEN_REVIEW_TAG,
        "reviewed_by": "",
        "reviewed_at": "",
        "review_comment": "",
    }


def _decision_row_with_default_columns(row: Mapping[str, Any]) -> dict[str, Any]:
    return {column: row.get(column, "") for column in DECISION_COLUMNS}


def _stable_issue_key(issue: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(issue.get("invoice_id", "")),
        str(issue.get("field_name", "")),
        str(issue.get("ocr_value", "")),
    )


def _stable_decision_key(decision: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(decision.get("invoice_id", "")),
        str(decision.get("field_name", "")),
        str(decision.get("original_value", "")),
    )


def _read_existing_decisions(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return pd.read_csv(path, dtype=object, keep_default_na=False, encoding="utf-8-sig").to_dict("records")
