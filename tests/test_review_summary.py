from src.review.confidence_config import load_confidence_config
from src.review.field_quality import build_field_quality_rows_from_records
from src.review.review_summary import build_review_summary_rows


def _config():
    return load_confidence_config("config/confidence/scope2_confidence.yaml")


def test_review_summary_blocks_missing_critical_field():
    config = _config()
    field_rows = build_field_quality_rows_from_records(
        [{"source_file": "sample.json", "account_number": "", "account_number_confidence": ""}],
        config,
    )

    summary = build_review_summary_rows(field_rows, config)[0]

    assert summary["review_status"] == "BLOCKED"
    assert summary["review_required"] is True
    assert summary["review_severity"] == "HIGH"
    assert "account_number" in summary["missing_required_fields"]


def test_review_summary_requires_review_for_low_confidence_critical_field():
    config = _config()
    record = {"source_file": "sample.json"}
    for field in [*config.critical_fields, *config.optional_fields, *config.noncritical_fields]:
        record[field] = "value"
        record[f"{field}_confidence"] = 0.95
    record["account_number_confidence"] = 0.70

    field_rows = build_field_quality_rows_from_records([record], config)

    summary = build_review_summary_rows(field_rows, config)[0]

    assert summary["review_status"] == "REVIEW_REQUIRED"
    assert summary["review_required"] is True
    assert "account_number" in summary["low_confidence_fields"]


def test_review_summary_auto_approved_when_all_configured_fields_pass():
    config = _config()
    record = {"source_file": "sample.json"}
    for field in [*config.critical_fields, *config.optional_fields, *config.noncritical_fields]:
        record[field] = "value"
        record[f"{field}_confidence"] = 0.95

    field_rows = build_field_quality_rows_from_records([record], config)
    summary = build_review_summary_rows(field_rows, config)[0]

    assert summary["review_status"] == "AUTO_APPROVED"
    assert summary["review_required"] is False
    assert summary["review_issue_count"] == 0


def test_review_summary_auto_resolved_when_blank_field_has_high_confidence():
    config = _config()
    record = {"source_file": "sample.json"}
    for field in [*config.critical_fields, *config.optional_fields, *config.noncritical_fields]:
        record[field] = "value"
        record[f"{field}_confidence"] = 0.95
    record["account_number"] = ""

    field_rows = build_field_quality_rows_from_records([record], config)
    summary = build_review_summary_rows(field_rows, config)[0]

    assert summary["review_status"] == "AUTO_RESOLVED_WITH_WARNING"
    assert summary["review_required"] is False
    assert summary["auto_resolved_fields"] == "account_number"
    assert summary["review_issue_count"] == 0
