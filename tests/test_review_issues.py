from src.review.confidence_config import load_confidence_config
from src.review.field_quality import build_field_quality_rows_from_records
from src.review.review_issues import build_review_issue_rows


def _config():
    return load_confidence_config("config/confidence/scope2_confidence.yaml")


def test_review_issues_include_blocked_and_review_fields_only():
    config = _config()
    record = {"source_file": "sample.json"}
    for field in [*config.critical_fields, *config.optional_fields, *config.noncritical_fields]:
        record[field] = "value"
        record[f"{field}_confidence"] = 0.95
    record["account_number_confidence"] = 0.70
    record["quantity_1"] = ""
    record["quantity_1_confidence"] = ""
    record["invoice_date"] = ""
    record["invoice_date_confidence"] = 0.95

    field_rows = build_field_quality_rows_from_records([record], config)
    issue_rows = build_review_issue_rows(field_rows, config)

    assert [row["field_name"] for row in issue_rows] == ["account_number", "quantity_1"]
    assert [row["issue_type"] for row in issue_rows] == ["LOW_CONFIDENCE", "MISSING_REQUIRED"]
    assert all(row["resolved_flag"] is False for row in issue_rows)


def test_review_issues_include_ocr_value_without_suggestion():
    config = _config()
    field_rows = build_field_quality_rows_from_records(
        [{
            "source_file": "sample.json",
            "account_number": "12345",
            "account_number_confidence": 0.70,
        }],
        config,
    )

    issue_rows = build_review_issue_rows(field_rows, config)
    account_number_issue = next(row for row in issue_rows if row["field_name"] == "account_number")

    assert account_number_issue["ocr_value"] == "12345"
    assert "suggested_value" not in account_number_issue
    assert account_number_issue["severity"] == "HIGH"
