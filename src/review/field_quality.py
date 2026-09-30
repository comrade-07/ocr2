from dataclasses import asdict, dataclass
from typing import Any, Mapping

from src.review.confidence_config import ConfidenceConfig

MAPPING_NOT_APPLICABLE = "NOT_APPLICABLE"
VALIDATION_NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class FieldQualityRow:
    invoice_id: str
    line_id: str
    canonical_field_name: str
    source_field_name: str
    cleaned_field_name: str
    raw_value: Any
    cleaned_value: Any
    confidence: float | None
    threshold: float
    criticality: str
    validation_status: str
    mapping_status: str
    field_status: str
    reason_code: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_field_quality_rows(
    record: Mapping[str, Any],
    config: ConfidenceConfig,
    invoice_id: str | None = None,
    line_id: str = "1",
) -> list[dict[str, Any]]:
    rows = []
    for field_name in _configured_fields(config):
        rows.append(
            evaluate_field_quality(
                record=record,
                field_name=field_name,
                config=config,
                invoice_id=invoice_id or _record_id(record),
                line_id=line_id,
            ).to_dict()
        )
    return rows


def build_field_quality_rows_from_records(
    records: list[Mapping[str, Any]],
    config: ConfidenceConfig,
) -> list[dict[str, Any]]:
    rows = []
    for index, record in enumerate(records, start=1):
        rows.extend(
            build_field_quality_rows(
                record=record,
                config=config,
                invoice_id=_record_id(record),
                line_id=str(record.get("line_id") or index),
            )
        )
    return rows


def evaluate_field_quality(
    record: Mapping[str, Any],
    field_name: str,
    config: ConfidenceConfig,
    invoice_id: str,
    line_id: str = "1",
) -> FieldQualityRow:
    criticality = _field_criticality(field_name, config)
    threshold = _field_threshold(criticality, config)
    raw_value = record.get(field_name)
    cleaned_field_name, cleaned_value = _cleaned_field(record, field_name, raw_value)
    confidence = _coerce_confidence(record.get(f"{field_name}_confidence"))
    status, reason = _tag_field(cleaned_value, confidence, threshold, criticality == "critical", config)

    return FieldQualityRow(
        invoice_id=invoice_id,
        line_id=line_id,
        canonical_field_name=field_name,
        source_field_name=field_name,
        cleaned_field_name=cleaned_field_name,
        raw_value=raw_value,
        cleaned_value=cleaned_value,
        confidence=confidence,
        threshold=threshold,
        criticality=criticality,
        validation_status=VALIDATION_NOT_APPLICABLE,
        mapping_status=MAPPING_NOT_APPLICABLE,
        field_status=status,
        reason_code=reason,
    )


def _tag_field(
    value: Any,
    confidence: float | None,
    threshold: float,
    critical: bool,
    config: ConfidenceConfig,
) -> tuple[str, str]:
    if _is_blank(value):
        if confidence is not None and confidence > config.blank_high_confidence_threshold:
            return config.field_statuses["auto_resolved"], config.field_tags["blank_high_confidence"]
        if critical:
            return config.field_statuses["blocked"], config.field_tags["missing_required"]
        return config.field_statuses["warning"], config.field_tags["missing_optional"]

    if confidence is not None and confidence < threshold:
        if critical:
            return config.field_statuses["review"], config.field_tags["low_confidence"]
        return config.field_statuses["warning"], config.field_tags["low_confidence"]

    return config.field_statuses["pass"], config.field_tags["pass"]


def _configured_fields(config: ConfidenceConfig) -> tuple[str, ...]:
    return tuple(dict.fromkeys([*config.critical_fields, *config.optional_fields, *config.noncritical_fields]))


def _field_criticality(field_name: str, config: ConfidenceConfig) -> str:
    if field_name in config.critical_fields:
        return "critical"
    if field_name in config.optional_fields:
        return "optional"
    return "noncritical"


def _field_threshold(criticality: str, config: ConfidenceConfig) -> float:
    if criticality == "critical":
        return config.critical_threshold
    if criticality == "optional":
        return config.optional_threshold
    return config.noncritical_threshold


def _coerce_confidence(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _cleaned_field(record: Mapping[str, Any], field_name: str, raw_value: Any) -> tuple[str, Any]:
    normalized_field_name = f"{field_name}_normalized"
    normalized_value = record.get(normalized_field_name)
    if _is_blank(normalized_value):
        return field_name, raw_value
    return normalized_field_name, normalized_value


def _is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _record_id(record: Mapping[str, Any]) -> str:
    return str(record.get("invoice_id") or record.get("source_file") or "")
