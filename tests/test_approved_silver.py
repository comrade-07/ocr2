import pandas as pd

from src.review.approved_silver import build_approved_silver_rows


def test_approved_silver_excludes_review_required_rows_without_decisions():
    silver_df = pd.DataFrame([
        {"source_file": "one.json", "supplier": "ACME"},
        {"source_file": "two.json", "supplier": "Beta"},
    ])
    summaries = [
        {"invoice_id": "one.json", "line_id": "1", "review_required": "False", "review_issue_count": 0},
        {"invoice_id": "two.json", "line_id": "2", "review_required": "True", "review_issue_count": 1},
    ]

    rows = build_approved_silver_rows(silver_df, summaries, [])

    assert [row["source_file"] for row in rows] == ["one.json"]


def test_approved_silver_applies_corrected_manual_decision():
    silver_df = pd.DataFrame([
        {"source_file": "one.json", "total_amount": ""},
    ])
    summaries = [
        {"invoice_id": "one.json", "line_id": "1", "review_required": "True", "review_issue_count": 1},
    ]
    decisions = [
        {
            "invoice_id": "one.json",
            "line_id": "1",
            "field_name": "total_amount",
            "corrected_value": "123.45",
            "review_decision": "CORRECTED",
        }
    ]

    rows = build_approved_silver_rows(silver_df, summaries, decisions)

    assert rows[0]["total_amount"] == "123.45"
    assert rows[0]["total_amount_review_tag"] == "MANUALLY_REVIEWED"
    assert rows[0]["approval_status"] == "MANUALLY_APPROVED"


def test_approved_silver_applies_approved_manual_value_when_supplied():
    silver_df = pd.DataFrame([
        {"source_file": "one.json", "consumption_start_date_1": ""},
    ])
    summaries = [
        {"invoice_id": "one.json", "line_id": "1", "review_required": "True", "review_issue_count": 1},
    ]
    decisions = [
        {
            "invoice_id": "one.json",
            "line_id": "1",
            "field_name": "consumption_start_date_1",
            "corrected_value": "1/10/2025",
            "review_decision": "APPROVED",
        }
    ]

    rows = build_approved_silver_rows(silver_df, summaries, decisions)

    assert rows[0]["consumption_start_date_1"] == "1/10/2025"
    assert rows[0]["consumption_start_date_1_review_tag"] == "MANUALLY_REVIEWED"
    assert rows[0]["consumption_start_date_1_review_decision"] == "APPROVED"


def test_approved_silver_keeps_original_value_for_approved_decision_without_manual_value():
    silver_df = pd.DataFrame([
        {"source_file": "one.json", "supplier": "Original Supplier"},
    ])
    summaries = [
        {"invoice_id": "one.json", "line_id": "1", "review_required": "True", "review_issue_count": 1},
    ]
    decisions = [
        {
            "invoice_id": "one.json",
            "line_id": "1",
            "field_name": "supplier",
            "corrected_value": "",
            "review_decision": "APPROVED",
        }
    ]

    rows = build_approved_silver_rows(silver_df, summaries, decisions)

    assert rows[0]["supplier"] == "Original Supplier"
    assert rows[0]["supplier_review_decision"] == "APPROVED"


def test_approved_silver_applies_override_to_auto_approved_row():
    silver_df = pd.DataFrame([
        {"source_file": "one.json", "line_id": "1", "total_amount": "999.00"},
    ])
    summaries = [
        {"invoice_id": "one.json", "line_id": "1", "review_required": "False", "review_issue_count": 0},
    ]
    decisions = [
        {
            "invoice_id": "one.json",
            "line_id": "1",
            "field_name": "total_amount",
            "corrected_value": "",
            "review_decision": "CORRECTED",
        }
    ]

    rows = build_approved_silver_rows(silver_df, summaries, decisions)

    assert rows[0]["total_amount"] == ""
    assert rows[0]["approval_status"] == "MANUALLY_APPROVED"
    assert rows[0]["manual_review_tag"] == "MANUALLY_REVIEWED"
    assert rows[0]["manual_review_decision_count"] == 1


def test_approved_silver_includes_row_after_first_approved_decision():
    silver_df = pd.DataFrame([
        {"source_file": "one.json", "supplier": "Original Supplier", "total_amount": "100"},
    ])
    summaries = [
        {"invoice_id": "one.json", "line_id": "1", "review_required": "True", "review_issue_count": 2},
    ]
    decisions = [
        {
            "invoice_id": "one.json",
            "line_id": "1",
            "field_name": "supplier",
            "corrected_value": "",
            "review_decision": "APPROVED",
        }
    ]

    rows = build_approved_silver_rows(silver_df, summaries, decisions)

    assert len(rows) == 1
    assert rows[0]["approval_status"] == "MANUALLY_APPROVED"
    assert rows[0]["manual_review_decision_count"] == 1
    assert rows[0]["supplier_review_decision"] == "APPROVED"


def test_approved_silver_matches_trimmed_invoice_and_normalized_line_id():
    silver_df = pd.DataFrame([
        {"invoice_id": "one.json ", "line_id": "1.0", "supplier": "Original Supplier"},
    ])
    summaries = [
        {"invoice_id": " one.json", "line_id": "1", "review_required": "True", "review_issue_count": 1},
    ]
    decisions = [
        {
            "invoice_id": "one.json",
            "line_id": "1",
            "field_name": "supplier",
            "corrected_value": "",
            "review_decision": "APPROVED",
        }
    ]

    rows = build_approved_silver_rows(silver_df, summaries, decisions)

    assert len(rows) == 1
    assert rows[0]["approval_status"] == "MANUALLY_APPROVED"
    assert rows[0]["supplier_review_decision"] == "APPROVED"


def test_approved_silver_excludes_rows_without_review_summary():
    silver_df = pd.DataFrame([
        {"source_file": "trained.json", "line_id": "1", "supplier": "ACME"},
        {
            "source_file": "untrained.json",
            "line_id": "1",
            "supplier": "Beta",
            "manual_entry_source": "OCR_LOW_DOCUMENT_CONFIDENCE",
        },
    ])
    summaries = [
        {"invoice_id": "trained.json", "line_id": "1", "review_required": "False", "review_issue_count": 0},
    ]

    rows = build_approved_silver_rows(silver_df, summaries, [])

    assert [row["source_file"] for row in rows] == ["trained.json"]
