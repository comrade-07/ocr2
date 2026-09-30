from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from src.review.confidence_config import ConfidenceConfig


@dataclass(frozen=True)
class ReviewIssueRow:
    issue_id: str
    invoice_id: str
    line_id: str
    field_name: str
    issue_type: str
    severity: str
    ocr_value: Any
    confidence: float | None
    threshold: float
    criticality: str
    resolved_flag: bool
    resolution_action: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_review_issue_rows(
    field_quality_rows: Iterable[Mapping[str, Any]],
    config: ConfidenceConfig,
) -> list[dict[str, Any]]:
    issue_rows = []
    actionable_statuses = {
        config.field_statuses["blocked"],
        config.field_statuses["review"],
    }

    for row in field_quality_rows:
        if row.get("field_status") not in actionable_statuses:
            continue
        issue_rows.append(_build_issue(row).to_dict())

    return issue_rows


def _build_issue(row: Mapping[str, Any]) -> ReviewIssueRow:
    invoice_id = str(row.get("invoice_id", ""))
    line_id = str(row.get("line_id", ""))
    field_name = str(row.get("canonical_field_name", ""))
    issue_type = str(row.get("reason_code", ""))

    return ReviewIssueRow(
        issue_id=_issue_id(invoice_id, line_id, field_name, issue_type),
        invoice_id=invoice_id,
        line_id=line_id,
        field_name=field_name,
        issue_type=issue_type,
        severity=_severity(row),
        ocr_value=row.get("raw_value"),
        confidence=_coerce_confidence(row.get("confidence")),
        threshold=float(row.get("threshold")),
        criticality=str(row.get("criticality", "")),
        resolved_flag=False,
        resolution_action="",
    )


def _issue_id(invoice_id: str, line_id: str, field_name: str, issue_type: str) -> str:
    raw_id = f"{invoice_id}_{line_id}_{field_name}_{issue_type}"
    return "".join(char if char.isalnum() else "_" for char in raw_id).strip("_")


def _severity(row: Mapping[str, Any]) -> str:
    if row.get("field_status") == "BLOCKED":
        return "HIGH"
    if row.get("criticality") == "critical":
        return "HIGH"
    return "MEDIUM"


def _coerce_confidence(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)
