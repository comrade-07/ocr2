from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from src.review.confidence_config import ConfidenceConfig


@dataclass(frozen=True)
class ReviewSummaryRow:
    invoice_id: str
    line_id: str
    review_status: str
    review_required: bool
    review_severity: str
    review_reason_codes: str
    failed_fields: str
    low_confidence_fields: str
    missing_required_fields: str
    auto_resolved_fields: str
    review_issue_count: int
    critical_issue_count: int
    min_critical_confidence: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_review_summary_rows(
    field_quality_rows: Iterable[Mapping[str, Any]],
    config: ConfidenceConfig,
) -> list[dict[str, Any]]:
    grouped_rows: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in field_quality_rows:
        key = (str(row.get("invoice_id", "")), str(row.get("line_id", "")))
        grouped_rows.setdefault(key, []).append(row)

    return [
        evaluate_review_summary(rows, config).to_dict()
        for rows in grouped_rows.values()
    ]


def evaluate_review_summary(
    field_quality_rows: list[Mapping[str, Any]],
    config: ConfidenceConfig,
) -> ReviewSummaryRow:
    if not field_quality_rows:
        raise ValueError("Cannot build review summary from an empty field-quality row list")

    invoice_id = str(field_quality_rows[0].get("invoice_id", ""))
    line_id = str(field_quality_rows[0].get("line_id", ""))

    blocking_rows = _rows_with_status(field_quality_rows, config.field_statuses["blocked"])
    review_rows = _rows_with_status(field_quality_rows, config.field_statuses["review"])
    warning_rows = _rows_with_status(field_quality_rows, config.field_statuses["warning"])
    auto_resolved_rows = _rows_with_status(field_quality_rows, config.field_statuses["auto_resolved"])

    critical_issue_rows = [
        row for row in [*blocking_rows, *review_rows, *warning_rows]
        if row.get("criticality") == "critical"
    ]

    if blocking_rows:
        review_status = config.review_statuses["blocked"]
        review_severity = "HIGH"
    elif review_rows:
        review_status = config.review_statuses["review_required"]
        review_severity = "HIGH" if critical_issue_rows else "MEDIUM"
    elif warning_rows:
        review_status = config.review_statuses["optional_field_warning"]
        review_severity = "LOW"
    elif auto_resolved_rows:
        review_status = config.review_statuses["auto_resolved_with_warning"]
        review_severity = "LOW"
    else:
        review_status = config.review_statuses["auto_approved"]
        review_severity = "NONE"

    issue_rows = [*blocking_rows, *review_rows, *warning_rows]
    reason_rows = [*issue_rows, *auto_resolved_rows]
    missing_required_rows = [
        row for row in blocking_rows
        if row.get("reason_code") == config.field_tags["missing_required"]
    ]
    low_confidence_rows = [
        row for row in issue_rows
        if row.get("reason_code") == config.field_tags["low_confidence"]
    ]

    return ReviewSummaryRow(
        invoice_id=invoice_id,
        line_id=line_id,
        review_status=review_status,
        review_required=review_status in {
            config.review_statuses["blocked"],
            config.review_statuses["review_required"],
        },
        review_severity=review_severity,
        review_reason_codes=_join_unique(row.get("reason_code") for row in reason_rows),
        failed_fields=_join_unique(row.get("canonical_field_name") for row in [*blocking_rows, *review_rows]),
        low_confidence_fields=_join_unique(row.get("canonical_field_name") for row in low_confidence_rows),
        missing_required_fields=_join_unique(row.get("canonical_field_name") for row in missing_required_rows),
        auto_resolved_fields=_join_unique(row.get("canonical_field_name") for row in auto_resolved_rows),
        review_issue_count=len(issue_rows),
        critical_issue_count=len(critical_issue_rows),
        min_critical_confidence=_min_critical_confidence(field_quality_rows),
    )


def _rows_with_status(rows: Iterable[Mapping[str, Any]], status: str) -> list[Mapping[str, Any]]:
    return [row for row in rows if row.get("field_status") == status]


def _join_unique(values: Iterable[Any]) -> str:
    unique_values = []
    for value in values:
        if value in (None, "") or value in unique_values:
            continue
        unique_values.append(str(value))
    return ";".join(unique_values)


def _min_critical_confidence(rows: Iterable[Mapping[str, Any]]) -> float | None:
    confidences = [
        float(row["confidence"])
        for row in rows
        if row.get("criticality") == "critical" and row.get("confidence") not in (None, "")
    ]
    return min(confidences) if confidences else None
