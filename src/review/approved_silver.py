from pathlib import Path
from typing import Any, Mapping
import re

import pandas as pd

from src.review.manual_decisions import (
    MANUALLY_REVIEWED_TAG,
    is_approved_decision,
)


APPROVED_SILVER_FILENAME = "step_5_approved_silver_checkpoint.csv"


def build_approved_silver_rows(
    silver_df: pd.DataFrame,
    review_summary_rows: list[Mapping[str, Any]],
    decision_rows: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    summary_by_key = {
        _line_key(row): row
        for row in review_summary_rows
    }
    decisions_by_key = _approved_decisions_by_line(decision_rows)

    approved_rows = []
    for index, row in enumerate(silver_df.to_dict("records"), start=1):
        key = _line_key({
            "invoice_id": row.get("invoice_id") or row.get("source_file") or "",
            "line_id": row.get("line_id") or str(index),
        })
        summary = summary_by_key.get(key)
        if summary is None:
            continue
        review_required = str(summary.get("review_required", "")).lower() == "true"
        row_decisions = decisions_by_key.get(key, [])

        if review_required and not row_decisions:
            continue

        approved_row = dict(row)
        was_manually_touched = review_required or bool(row_decisions)
        approved_row["approval_status"] = "MANUALLY_APPROVED" if was_manually_touched else "AUTO_APPROVED"
        approved_row["manual_review_tag"] = MANUALLY_REVIEWED_TAG if was_manually_touched else ""
        approved_row["manual_review_decision_count"] = len(row_decisions)

        for decision in row_decisions:
            _apply_decision(approved_row, decision)

        approved_rows.append(approved_row)

    return approved_rows


def write_approved_silver_checkpoint(
    silver_df: pd.DataFrame,
    review_summary_rows: list[dict],
    decision_rows: list[dict],
    output_dir: str | Path,
    filename: str = APPROVED_SILVER_FILENAME,
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    target = output_path / filename

    approved_rows = build_approved_silver_rows(silver_df, review_summary_rows, decision_rows)
    columns = [
        *silver_df.columns,
        "approval_status",
        "manual_review_tag",
        "manual_review_decision_count",
    ]
    pd.DataFrame(approved_rows, columns=_ordered_columns(columns, approved_rows)).to_csv(
        target, index=False, encoding="utf-8-sig"
    )

    return target


def _approved_decisions_by_line(
    decision_rows: list[Mapping[str, Any]],
) -> dict[tuple[str, str], list[Mapping[str, Any]]]:
    decisions_by_key: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for decision in decision_rows:
        if not is_approved_decision(decision):
            continue
        decisions_by_key.setdefault(_line_key(decision), []).append(decision)
    return decisions_by_key


def _apply_decision(row: dict[str, Any], decision: Mapping[str, Any]) -> None:
    field_name = str(decision.get("field_name", ""))
    review_decision = str(decision.get("review_decision", "")).strip().upper()
    approved_value = _approved_field_value(decision)

    if approved_value is not None:
        row[field_name] = approved_value
    row[f"{field_name}_review_tag"] = MANUALLY_REVIEWED_TAG
    row[f"{field_name}_review_decision"] = review_decision


def _approved_field_value(decision: Mapping[str, Any]) -> Any | None:
    corrected_value = decision.get("corrected_value", "")
    if not _is_blank(corrected_value):
        return corrected_value

    review_decision = str(decision.get("review_decision", "")).strip().upper()
    if review_decision == "CORRECTED":
        return corrected_value
    return None


def _is_blank(value: Any) -> bool:
    return value is None or pd.isna(value) or str(value).strip() == ""


def _line_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return (_normalize_key_value(row.get("invoice_id", "")), _normalize_line_id(row.get("line_id", "")))


def _normalize_key_value(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _normalize_line_id(value: Any) -> str:
    normalized = _normalize_key_value(value)
    if re.fullmatch(r"\d+\.0+", normalized):
        return normalized.split(".", 1)[0]
    return normalized


def _ordered_columns(base_columns: list[str], rows: list[dict[str, Any]]) -> list[str]:
    columns = list(dict.fromkeys(base_columns))
    for row in rows:
        for column in row:
            if column not in columns:
                columns.append(column)
    return columns
