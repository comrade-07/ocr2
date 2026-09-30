from src.review.manual_decisions import (
    MANUALLY_REVIEWED_TAG,
    OPEN_REVIEW_TAG,
    build_manual_decision_rows,
    is_approved_decision,
    reopen_manual_decision_rows,
)


def test_manual_decision_rows_preserve_existing_edits_by_issue_id():
    issues = [
        {
            "issue_id": "issue_1",
            "invoice_id": "invoice.json",
            "line_id": "1",
            "field_name": "total_amount",
            "ocr_value": "",
        }
    ]
    existing = [
        {
            "issue_id": "issue_1",
            "corrected_value": "123.45",
            "review_decision": "CORRECTED",
            "review_tag": MANUALLY_REVIEWED_TAG,
            "reviewed_by": "reviewer",
            "reviewed_at": "2026-06-19T00:00:00+00:00",
            "review_comment": "Checked invoice.",
        }
    ]

    rows = build_manual_decision_rows(issues, existing)

    assert rows[0]["corrected_value"] == "123.45"
    assert rows[0]["review_decision"] == "CORRECTED"
    assert rows[0]["review_tag"] == MANUALLY_REVIEWED_TAG


def test_manual_decision_rows_preserve_existing_edits_when_line_id_changes():
    issues = [
        {
            "issue_id": "invoice_json_1_total_amount_LOW_CONFIDENCE",
            "invoice_id": "invoice.json",
            "line_id": "1",
            "field_name": "total_amount",
            "ocr_value": "120.00",
        }
    ]
    existing = [
        {
            "issue_id": "invoice_json_2_total_amount_LOW_CONFIDENCE",
            "invoice_id": "invoice.json",
            "line_id": "2",
            "field_name": "total_amount",
            "original_value": "120.00",
            "corrected_value": "123.45",
            "review_decision": "CORRECTED",
            "review_tag": MANUALLY_REVIEWED_TAG,
            "reviewed_by": "reviewer",
            "reviewed_at": "2026-06-19T00:00:00+00:00",
            "review_comment": "Checked invoice.",
        }
    ]

    rows = build_manual_decision_rows(issues, existing)

    assert rows[0]["corrected_value"] == "123.45"
    assert rows[0]["review_decision"] == "CORRECTED"
    assert rows[0]["review_tag"] == MANUALLY_REVIEWED_TAG


def test_manual_decision_rows_preserve_manual_override_rows_without_matching_issue():
    issues = [
        {
            "issue_id": "issue_1",
            "invoice_id": "invoice.json",
            "line_id": "1",
            "field_name": "supplier",
            "ocr_value": "",
        }
    ]
    existing = [
        {
            "decision_id": "decision_override_invoice_json_1_total_amount",
            "issue_id": "override_invoice_json_1_total_amount",
            "invoice_id": "invoice.json",
            "line_id": "1",
            "field_name": "total_amount",
            "original_value": "999.00",
            "corrected_value": "",
            "review_decision": "CORRECTED",
            "review_tag": MANUALLY_REVIEWED_TAG,
            "reviewed_by": "reviewer",
            "reviewed_at": "2026-06-19T00:00:00+00:00",
            "review_comment": "Layout drift picked up the wrong value.",
        }
    ]

    rows = build_manual_decision_rows(issues, existing)

    assert [row["issue_id"] for row in rows] == [
        "issue_1",
        "override_invoice_json_1_total_amount",
    ]
    assert rows[1]["field_name"] == "total_amount"
    assert rows[1]["corrected_value"] == ""
    assert rows[1]["review_decision"] == "CORRECTED"
    assert rows[1]["review_tag"] == MANUALLY_REVIEWED_TAG


def test_is_approved_decision_accepts_corrected_approved_and_not_applicable():
    assert is_approved_decision({"review_decision": "CORRECTED"}) is True
    assert is_approved_decision({"review_decision": "APPROVED"}) is True
    assert is_approved_decision({"review_decision": "NOT_APPLICABLE"}) is True
    assert is_approved_decision({"review_decision": "REJECTED"}) is False


def test_reopen_manual_decision_rows_clears_approval_fields():
    rows = reopen_manual_decision_rows(
        [
            {
                "issue_id": "issue_1",
                "corrected_value": "123.45",
                "review_decision": "CORRECTED",
                "review_tag": MANUALLY_REVIEWED_TAG,
                "reviewed_by": "reviewer",
                "reviewed_at": "2026-06-19T00:00:00+00:00",
                "review_comment": "Checked invoice.",
            },
            {
                "issue_id": "issue_2",
                "corrected_value": "99",
                "review_decision": "APPROVED",
                "review_tag": MANUALLY_REVIEWED_TAG,
            },
        ],
        ["issue_1"],
    )

    assert rows[0]["corrected_value"] == ""
    assert rows[0]["review_decision"] == ""
    assert rows[0]["review_tag"] == OPEN_REVIEW_TAG
    assert rows[0]["reviewed_by"] == ""
    assert rows[0]["reviewed_at"] == ""
    assert rows[0]["review_comment"] == ""
    assert rows[1]["review_decision"] == "APPROVED"
