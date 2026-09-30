import pandas as pd

from src.review.confidence_config import ConfidenceConfig
from src.review.manual_data_entry import (
    append_manual_upload_queue_row,
    build_manual_data_entry_queue_rows,
    load_entity_hierarchy,
    MANUAL_ENTRY_SOURCE_UPLOAD,
    missing_manual_data_entry_fields,
    prune_manual_data_entry_decisions,
    write_manual_data_entry_queue,
    split_by_document_confidence,
)


def test_document_confidence_split_routes_low_confidence_rows_to_manual_entry():
    config = _confidence_config(document_threshold=0.60)
    bronze_df = pd.DataFrame([
        {"invoice_id": "trained.json", "line_id": "1", "document_confidence": "0.60"},
        {"invoice_id": "untrained.json", "line_id": "1", "document_confidence": "0.59"},
        {"invoice_id": "missing.json", "line_id": "1", "document_confidence": ""},
    ])

    review_df, manual_entry_df = split_by_document_confidence(bronze_df, config)

    assert review_df["invoice_id"].tolist() == ["trained.json", "missing.json"]
    assert manual_entry_df["invoice_id"].tolist() == ["untrained.json"]


def test_manual_data_entry_queue_rows_include_entry_fields_and_threshold():
    config = _confidence_config(document_threshold=0.60)
    bronze_df = pd.DataFrame([
        {
            "invoice_id": "untrained.json",
            "line_id": "1",
            "source_file": "untrained.json",
            "sharepoint_link": "https://example.test/invoice.pdf",
            "document_confidence": "0.42",
        },
    ])

    rows = build_manual_data_entry_queue_rows(bronze_df, config)

    assert rows[0]["invoice_id"] == "untrained.json"
    assert rows[0]["document_confidence_threshold"] == 0.60
    assert rows[0]["manual_entry_status"] == "OPEN"
    assert "amount_of_energy_consumed" in rows[0]
    assert "contractual_instrument_used" not in rows[0]


def test_missing_manual_data_entry_fields_lists_blank_required_fields():
    values = {
        "data_quality": "Actual",
        "division": "Tanker",
        "legal_entity_name": "Legal One",
        "unit": "",
        "consumption_start_date": "2025-06-01",
        "consumption_end_date": "2025-06-30",
        "transaction_date": "2025-07-20",
        "amount_of_energy_consumed": "300",
        "energy_unit": "   ",
    }

    assert missing_manual_data_entry_fields(values) == ["unit", "energy_unit"]


def test_load_entity_hierarchy_reads_shared_master_entity_csv(tmp_path):
    reference_dir = tmp_path / "reference"
    reference_dir.mkdir()
    entity_list = reference_dir / "master_entity_list.csv"
    entity_list.write_text(
        "\n".join([
            "active,division,legal_entity_name,unit",
            "Yes,Division A,Entity One,Unit 2",
            "Yes,Division A,Entity One,Unit 1",
            "No,Division A,Entity One,Inactive Unit",
            "Yes,Division A,Entity Two,Unit 3",
            "",
        ]),
        encoding="utf-8",
    )

    hierarchy = load_entity_hierarchy(tmp_path, {"validation": {}})

    assert hierarchy == {
        "Division A": {
            "Entity One": ["Unit 1", "Unit 2"],
            "Entity Two": ["Unit 3"],
        },
    }


def test_manual_upload_queue_rows_are_preserved_when_ocr_queue_is_rebuilt(tmp_path):
    config = _confidence_config(document_threshold=0.60)
    queue_file = tmp_path / "step_0_manual_data_entry_queue.csv"
    append_manual_upload_queue_row(
        queue_file,
        uploaded_file_name="unsupported.pdf",
        stored_file_path=tmp_path / "uploads" / "unsupported.pdf",
        uploaded_at="2026-06-23T00:00:00+00:00",
        sharepoint_link="https://tenant.sharepoint.com/Evidence/unsupported.pdf",
    )
    bronze_df = pd.DataFrame([
        {"invoice_id": "untrained.json", "line_id": "1", "document_confidence": "0.42"},
    ])

    write_manual_data_entry_queue(bronze_df, config, tmp_path)

    rows = pd.read_csv(queue_file, dtype=object, keep_default_na=False).to_dict("records")

    assert {row["invoice_id"] for row in rows} == {"untrained.json", "manual_upload_unsupported"}
    upload_row = next(row for row in rows if row["manual_entry_source"] == MANUAL_ENTRY_SOURCE_UPLOAD)
    assert upload_row["original_file_name"] == "unsupported.pdf"
    assert upload_row["sharepoint_link"] == "https://tenant.sharepoint.com/Evidence/unsupported.pdf"


def test_manual_data_entry_decisions_are_pruned_to_current_queue(tmp_path):
    queue_file = tmp_path / "step_0_manual_data_entry_queue.csv"
    decisions_file = tmp_path / "step_0_manual_data_entry_decisions_checkpoint.csv"
    pd.DataFrame([
        {
            "invoice_id": "current.json",
            "line_id": "1",
            "manual_entry_source": "OCR_LOW_DOCUMENT_CONFIDENCE",
        }
    ]).to_csv(queue_file, index=False)
    pd.DataFrame([
        {
            "invoice_id": "current.json",
            "line_id": "1",
            "manual_entry_status": "COMPLETED",
        },
        {
            "invoice_id": "deleted.json",
            "line_id": "1",
            "manual_entry_status": "COMPLETED",
        },
    ]).to_csv(decisions_file, index=False)

    prune_manual_data_entry_decisions(decisions_file, queue_file)

    rows = pd.read_csv(decisions_file, dtype=object, keep_default_na=False).to_dict("records")

    assert [row["invoice_id"] for row in rows] == ["current.json"]


def _confidence_config(document_threshold: float) -> ConfidenceConfig:
    return ConfidenceConfig(
        document_confidence_threshold=document_threshold,
        critical_threshold=0.80,
        optional_threshold=0.60,
        noncritical_threshold=0.30,
        blank_high_confidence_threshold=0.90,
        critical_fields=("legal_entity",),
        optional_fields=(),
        noncritical_fields=(),
        review_statuses={
            "auto_approved": "AUTO_APPROVED",
            "auto_resolved_with_warning": "AUTO_RESOLVED_WITH_WARNING",
            "optional_field_warning": "OPTIONAL_FIELD_WARNING",
            "review_required": "REVIEW_REQUIRED",
            "blocked": "BLOCKED",
        },
        field_statuses={
            "pass": "PASS",
            "review": "REVIEW",
            "warning": "WARNING",
            "blocked": "BLOCKED",
            "auto_resolved": "AUTO_RESOLVED",
        },
        field_tags={
            "pass": "PASS",
            "low_confidence": "LOW_CONFIDENCE",
            "missing_required": "MISSING_REQUIRED",
            "missing_optional": "MISSING_OPTIONAL",
            "blank_high_confidence": "BLANK_HIGH_CONFIDENCE",
            "invalid_format": "INVALID_FORMAT",
            "failed_business_rule": "FAILED_BUSINESS_RULE",
            "unmapped_value": "UNMAPPED_VALUE",
            "auto_resolved_by_mapping": "AUTO_RESOLVED_BY_MAPPING",
        },
        mapping_checks={"enabled": False, "fields": []},
    )
