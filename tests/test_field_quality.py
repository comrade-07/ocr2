from src.review.confidence_config import load_confidence_config
from src.review.field_quality import (
    build_field_quality_rows,
    build_field_quality_rows_from_records,
    evaluate_field_quality,
)


def _config():
    return load_confidence_config("config/confidence/scope2_confidence.yaml")


def test_evaluate_field_quality_blocks_missing_critical_field():
    row = evaluate_field_quality(
        record={"account_number": "", "account_number_confidence": ""},
        field_name="account_number",
        config=_config(),
        invoice_id="INV-001",
    )

    assert row.field_status == "BLOCKED"
    assert row.reason_code == "MISSING_REQUIRED"
    assert row.criticality == "critical"


def test_evaluate_field_quality_reviews_low_confidence_critical_field():
    row = evaluate_field_quality(
        record={"account_number": "12345", "account_number_confidence": 0.617},
        field_name="account_number",
        config=_config(),
        invoice_id="INV-001",
    )

    assert row.field_status == "REVIEW"
    assert row.reason_code == "LOW_CONFIDENCE"
    assert row.threshold == 0.80


def test_evaluate_field_quality_warns_low_confidence_optional_field():
    row = evaluate_field_quality(
        record={"legal_entity": "ACME Ltd", "legal_entity_confidence": 0.55},
        field_name="legal_entity",
        config=_config(),
        invoice_id="INV-001",
    )

    assert row.field_status == "WARNING"
    assert row.reason_code == "LOW_CONFIDENCE"
    assert row.threshold == 0.60
    assert row.criticality == "optional"


def test_evaluate_field_quality_warns_low_confidence_noncritical_field():
    row = evaluate_field_quality(
        record={"invoice_date": "2026-06-01", "invoice_date_confidence": 0.25},
        field_name="invoice_date",
        config=_config(),
        invoice_id="INV-001",
    )

    assert row.field_status == "WARNING"
    assert row.reason_code == "LOW_CONFIDENCE"
    assert row.threshold == 0.30


def test_evaluate_field_quality_auto_resolves_blank_high_confidence_field():
    row = evaluate_field_quality(
        record={"account_number": "", "account_number_confidence": 0.95},
        field_name="account_number",
        config=_config(),
        invoice_id="INV-001",
    )

    assert row.field_status == "AUTO_RESOLVED"
    assert row.reason_code == "BLANK_HIGH_CONFIDENCE"


def test_build_field_quality_rows_uses_all_configured_fields():
    rows = build_field_quality_rows(
        record={
            "source_file": "sample.json",
            "account_number": "12345",
            "account_number_confidence": 0.95,
        },
        config=_config(),
    )

    account_number_row = next(row for row in rows if row["canonical_field_name"] == "account_number")
    invoice_date_row = next(row for row in rows if row["canonical_field_name"] == "invoice_date")

    assert account_number_row["invoice_id"] == "sample.json"
    assert account_number_row["field_status"] == "PASS"
    assert account_number_row["reason_code"] == "PASS"
    assert invoice_date_row["field_status"] == "WARNING"
    assert invoice_date_row["reason_code"] == "MISSING_OPTIONAL"


def test_evaluate_field_quality_uses_normalized_value_as_cleaned_value():
    row = evaluate_field_quality(
        record={
            "invoice_date": "25 Jul 2025",
            "invoice_date_normalized": "2025-07-25",
            "invoice_date_confidence": 0.95,
        },
        field_name="invoice_date",
        config=_config(),
        invoice_id="INV-001",
    )

    assert row.raw_value == "25 Jul 2025"
    assert row.cleaned_field_name == "invoice_date_normalized"
    assert row.cleaned_value == "2025-07-25"


def test_build_field_quality_rows_from_records_uses_silver_records():
    rows = build_field_quality_rows_from_records(
        records=[
            {
                "source_file": "one.json",
                "account_number": "12345",
                "account_number_confidence": 0.95,
            },
            {
                "source_file": "two.json",
                "account_number": "",
                "account_number_confidence": "",
            },
        ],
        config=_config(),
    )

    account_number_rows = [row for row in rows if row["canonical_field_name"] == "account_number"]

    assert account_number_rows[0]["invoice_id"] == "one.json"
    assert account_number_rows[0]["line_id"] == "1"
    assert account_number_rows[0]["field_status"] == "PASS"
    assert account_number_rows[1]["invoice_id"] == "two.json"
    assert account_number_rows[1]["line_id"] == "2"
    assert account_number_rows[1]["field_status"] == "BLOCKED"
