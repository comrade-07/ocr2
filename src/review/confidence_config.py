from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.config_loader import load_yaml


DEFAULT_REVIEW_STATUSES = {
    "auto_approved": "AUTO_APPROVED",
    "auto_resolved_with_warning": "AUTO_RESOLVED_WITH_WARNING",
    "optional_field_warning": "OPTIONAL_FIELD_WARNING",
    "review_required": "REVIEW_REQUIRED",
    "blocked": "BLOCKED",
}

DEFAULT_FIELD_TAGS = {
    "pass": "PASS",
    "low_confidence": "LOW_CONFIDENCE",
    "missing_required": "MISSING_REQUIRED",
    "missing_optional": "MISSING_OPTIONAL",
    "blank_high_confidence": "BLANK_HIGH_CONFIDENCE",
    "invalid_format": "INVALID_FORMAT",
    "failed_business_rule": "FAILED_BUSINESS_RULE",
    "unmapped_value": "UNMAPPED_VALUE",
    "auto_resolved_by_mapping": "AUTO_RESOLVED_BY_MAPPING",
}

DEFAULT_FIELD_STATUSES = {
    "pass": "PASS",
    "review": "REVIEW",
    "warning": "WARNING",
    "blocked": "BLOCKED",
    "auto_resolved": "AUTO_RESOLVED",
}


@dataclass(frozen=True)
class ConfidenceConfig:
    document_confidence_threshold: float
    critical_threshold: float
    optional_threshold: float
    noncritical_threshold: float
    blank_high_confidence_threshold: float
    critical_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]
    noncritical_fields: tuple[str, ...]
    review_statuses: dict[str, str]
    field_statuses: dict[str, str]
    field_tags: dict[str, str]
    mapping_checks: dict[str, Any]


def load_confidence_config(path: str | Path) -> ConfidenceConfig:
    config = load_yaml(path)
    thresholds = config.get("thresholds", {})

    return ConfidenceConfig(
        document_confidence_threshold=float(thresholds.get("document_confidence", 0.0)),
        critical_threshold=_required_float(thresholds, "critical"),
        optional_threshold=_required_float(thresholds, "optional"),
        noncritical_threshold=_required_float(thresholds, "noncritical"),
        blank_high_confidence_threshold=float(thresholds.get("blank_high_confidence", 0.90)),
        critical_fields=tuple(_required_list(config, "critical_fields")),
        optional_fields=tuple(config.get("optional_fields", [])),
        noncritical_fields=tuple(config.get("noncritical_fields", [])),
        review_statuses={**DEFAULT_REVIEW_STATUSES, **config.get("review_statuses", {})},
        field_statuses={**DEFAULT_FIELD_STATUSES, **config.get("field_statuses", {})},
        field_tags={**DEFAULT_FIELD_TAGS, **config.get("field_tags", {})},
        mapping_checks=config.get("mapping_checks", {"enabled": False, "fields": []}),
    )


def confidence_config_path(config_dir: str | Path, invoice_type: str) -> Path:
    return Path(config_dir) / "confidence" / f"{invoice_type}_confidence.yaml"


def _required_float(config: dict[str, Any], key: str) -> float:
    if key not in config:
        raise ValueError(f"Missing confidence threshold: {key}")
    try:
        return float(config[key])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Confidence threshold must be numeric: {key}") from exc


def _required_list(config: dict[str, Any], key: str) -> list[str]:
    value = config.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"Config value must be a non-empty list: {key}")
    return value
